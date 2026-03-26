"""
MedQueue Celery Tasks
=====================

Email Flow for each patient:
─────────────────────────────────────────────────────────────────────
  9:30 AM  → send_session_reminders("morning")
             Sends TWO emails at once:
               Email 1: "OPD starts in 30 minutes"
               Email 2: "Confirm your attendance now (before OPD starts)"
             Patient can pre-confirm via MedQueue app right away.

  1:30 PM  → send_session_reminders("evening")
             Same — both emails sent 30 min before 2 PM OPD.

  Every 2 min → send_confirmation_prompts()
             10 minutes AFTER OPD starts:
             Sends a SECOND confirmation prompt to anyone still unconfirmed.
             "OPD has started — confirm NOW or lose your position."

  Every 2 min → notify_patients_two_tokens_away()
             Email/SMS when patient is 2 slots away from being called.

  On booking  → send_ticket_email_task(booking_id)
─────────────────────────────────────────────────────────────────────

Add to settings.py CELERY_BEAT_SCHEDULE:

    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE = {
        "send-morning-reminders": {
            "task": "booking.tasks.send_session_reminders",
            "schedule": crontab(hour=9, minute=30),
            "args": ["morning"],
        },
        "send-evening-reminders": {
            "task": "booking.tasks.send_session_reminders",
            "schedule": crontab(hour=13, minute=30),
            "args": ["evening"],
        },
        "send-confirmation-prompts": {
            "task": "booking.tasks.send_confirmation_prompts",
            "schedule": crontab(minute="*/2"),
        },
        "notify-two-tokens-away": {
            "task": "booking.tasks.notify_patients_two_tokens_away",
            "schedule": crontab(minute="*/2", hour="9-17"),
        },
    }
"""

from celery import shared_task
from django.utils.timezone import now
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 1. TICKET EMAIL  (triggered on booking creation)
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_ticket_email_task(self, booking_id):
    """Send OPD ticket to patient immediately after booking."""
    from .models import Booking
    from .utils import send_opd_ticket_email

    try:
        booking = Booking.objects.get(id=booking_id)
        if booking.ticket_sent:
            logger.info(f"Ticket already sent for booking {booking_id}. Skipping.")
            return
        success = send_opd_ticket_email(booking)
        if success:
            logger.info(f"OPD ticket sent for booking {booking_id}")
        else:
            logger.warning(f"Could not send ticket for booking {booking_id} (no email?)")
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found.")
    except Exception as exc:
        logger.error(f"Error sending ticket for booking {booking_id}: {exc}")
        raise self.retry(exc=exc)


# ═══════════════════════════════════════════════════════════════════════════
# 2. PRE-OPD REMINDER + CONFIRMATION PROMPT  — 30 minutes before OPD
#
#    Scheduled: 9:30 AM for morning OPD (10:00 AM)
#               1:30 PM for evening OPD  (2:00 PM)
#
#    Sends TWO emails to each patient in ONE task:
#      Email 1 — Reminder     : "OPD starts in 30 minutes"
#      Email 2 — Confirm NOW  : "Please confirm your attendance right now"
#
#    Patient can open MedQueue and confirm before the OPD even starts.
#    This means when the doctor clicks Start OPD, most patients are
#    already confirmed and immediately in the active queue.
#
#    Uses `reminder_sent` flag on Booking to never double-send.
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=2)
def send_session_reminders(self, session):
    """
    30 minutes before OPD — send reminder + confirmation request.

    Both emails are sent in one pass per patient so they arrive together.
    The confirmation email tells patients to open MedQueue and confirm NOW,
    before the OPD starts, so their token is ready the moment OPD begins.
    """
    from .models import Booking, PaymentStatus

    today = now().date()

    session_time = {
        "morning": "10:00 AM",
        "evening": "2:00 PM",
    }
    start_time = session_time.get(session, "soon")

    bookings = Booking.objects.filter(
        booking_date=today,
        session=session,
        payment_status=PaymentStatus.PAID,
        reminder_sent=False,
        patient__isnull=False,
    ).select_related("patient__user", "doctor__hospital", "doctor__department")

    sent_count = 0

    for booking in bookings:
        email = booking.patient.user.email if booking.patient else ""
        if not email:
            continue

        # ── Email 1: Reminder ────────────────────────────────────────────
        try:
            send_mail(
                subject=(
                    f"[MedQueue] OPD Starts in 30 Minutes – "
                    f"Token #{booking.token_number} | Dr. {booking.doctor.full_name}"
                ),
                message=(
                    f"Dear {booking.display_name},\n\n"
                    f"Dr. {booking.doctor.full_name}'s {session.capitalize()} OPD "
                    f"is starting at {start_time} — just 30 minutes from now.\n\n"
                    f"Your Appointment:\n"
                    f"  Token Number : #{booking.token_number}\n"
                    f"  Session      : {session.capitalize()} ({start_time})\n"
                    f"  Date         : {today}\n"
                    f"  Hospital     : {booking.doctor.hospital.name}\n"
                    f"  Department   : {booking.doctor.department.name}\n\n"
                    "Please make sure you are at the hospital and ready.\n"
                    "You will receive a second email right now asking you to\n"
                    "confirm your attendance — please do that immediately.\n\n"
                    "– MedQueue Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info(
                f"30-min reminder → {email} | Token #{booking.token_number} | "
                f"{session} | {today}"
            )
        except Exception as e:
            logger.error(f"Reminder email failed for booking {booking.id}: {e}")
            continue   # skip confirmation email too if reminder failed

        # ── Email 2: Confirmation request (sent immediately after) ───────
        try:
            send_mail(
                subject=(
                    f"[MedQueue] ⚠️ Confirm Your Attendance NOW – "
                    f"Token #{booking.token_number} | Dr. {booking.doctor.full_name}"
                ),
                message=(
                    f"Dear {booking.display_name},\n\n"
                    f"Dr. {booking.doctor.full_name}'s {session.capitalize()} OPD "
                    f"starts at {start_time} (in 30 minutes).\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "ACTION REQUIRED: CONFIRM YOUR ATTENDANCE\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Please open the MedQueue app right now and tap\n"
                    "CONFIRM ATTENDANCE to secure your queue position.\n\n"
                    f"  Token Number : #{booking.token_number}\n"
                    f"  Session      : {session.capitalize()} ({start_time})\n"
                    f"  Date         : {today}\n\n"
                    "What happens based on when you confirm:\n\n"
                    f"  ✅ Confirm NOW (before or within 10 min of {start_time})\n"
                    f"     → You keep Token #{booking.token_number} — your original\n"
                    "        position in the queue.\n\n"
                    f"  ⚠️  Confirm LATE (more than 10 min after {start_time})\n"
                    "     → You are placed after the 5th patient in the\n"
                    "        remaining queue.\n\n"
                    "  ❌ Do not confirm\n"
                    "     → Your token stays unconfirmed. Staff will\n"
                    "        handle it manually.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "👉 Open MedQueue and tap CONFIRM ATTENDANCE now.\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "– MedQueue Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info(
                f"Pre-OPD confirm prompt → {email} | Token #{booking.token_number} | "
                f"{session} | {today}"
            )
        except Exception as e:
            logger.error(f"Confirmation email failed for booking {booking.id}: {e}")

        # Mark reminder sent after both emails — never re-send
        Booking.objects.filter(id=booking.id).update(reminder_sent=True)
        sent_count += 1

    logger.info(
        f"[send_session_reminders] {session} | {today} | "
        f"Processed {sent_count} patient(s)."
    )
    return sent_count


# ═══════════════════════════════════════════════════════════════════════════
# 3. POST-START CONFIRMATION PROMPT — 10 minutes AFTER OPD starts
#
#    Runs every 2 minutes via Celery Beat.
#
#    Purpose: catch patients who didn't respond to the 30-min emails.
#    Detects sessions where started_at is between 10 and 12 minutes ago
#    and confirmation_prompt_sent = False (new OPDDay field).
#
#    Sends a FINAL "OPD has started — last chance to confirm" email
#    to anyone still unconfirmed.
#
#    REQUIRES: OPDDay.confirmation_prompt_sent = BooleanField(default=False)
# ═══════════════════════════════════════════════════════════════════════════

@shared_task
def send_confirmation_prompts():
    """
    Runs every 2 minutes.
    Sends final confirmation prompt to unconfirmed patients 10 min after OPD starts.
    This catches patients who ignored the 30-min emails.
    """
    from .models import Booking, OPDDay, BookingStatus, PaymentStatus

    current_time = now()
    window_start = current_time - timedelta(minutes=12)
    window_end   = current_time - timedelta(minutes=10)

    # Sessions that crossed the 10-minute mark in this beat window
    due_sessions = OPDDay.objects.filter(
        is_active=True,
        started_at__gte=window_start,
        started_at__lte=window_end,
        confirmation_prompt_sent=False,       # ← new OPDDay field
    ).select_related("doctor__hospital", "doctor__department")

    for opd_day in due_sessions:
        doctor  = opd_day.doctor
        session = opd_day.session
        today   = opd_day.date

        session_time = {"morning": "10:00 AM", "evening": "2:00 PM"}
        start_time   = session_time.get(session, "—")

        # Only patients still unconfirmed after the 30-min emails
        unconfirmed = Booking.objects.filter(
            doctor=doctor,
            booking_date=today,
            session=session,
            payment_status=PaymentStatus.PAID,
            is_confirmed=False,
            status=BookingStatus.WAITING,
            patient__isnull=False,
        ).select_related("patient__user")

        sent_count = 0
        for booking in unconfirmed:
            email = booking.patient.user.email if booking.patient else ""
            if not email:
                continue

            try:
                send_mail(
                    subject=(
                        f"[MedQueue] FINAL REMINDER — Confirm NOW | "
                        f"Token #{booking.token_number} | Dr. {doctor.full_name}"
                    ),
                    message=(
                        f"Dear {booking.display_name},\n\n"
                        f"Dr. {doctor.full_name}'s {session.capitalize()} OPD "
                        f"started at {start_time} and is now 10 minutes in.\n\n"
                        f"  Token Number : #{booking.token_number}\n"
                        f"  Session      : {session.capitalize()} ({start_time})\n"
                        f"  Date         : {today}\n"
                        f"  Hospital     : {doctor.hospital.name}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⚠️  YOU HAVE NOT CONFIRMED YET\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "The 10-minute on-time window has passed.\n\n"
                        "If you confirm NOW:\n"
                        "  → You will be placed after the 5th patient\n"
                        "     in the remaining queue (grace position).\n\n"
                        "If you do not confirm:\n"
                        "  → Your token stays unconfirmed and staff\n"
                        "     will handle it manually.\n\n"
                        "👉 Open MedQueue and tap CONFIRM ATTENDANCE now.\n\n"
                        "– MedQueue Team"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                sent_count += 1
                logger.info(
                    f"Post-start confirm prompt → {email} | "
                    f"Token #{booking.token_number} | {session} | {today}"
                )
            except Exception as e:
                logger.error(
                    f"Post-start confirm prompt failed for booking {booking.id}: {e}"
                )

        # Mark so this session is never prompted again
        OPDDay.objects.filter(id=opd_day.id).update(confirmation_prompt_sent=True)

        logger.info(
            f"[send_confirmation_prompts] Dr. {doctor.full_name} | "
            f"{session} | {today} | Sent {sent_count} final prompt(s)."
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. UNCONFIRMED PATIENTS LOG
# ═══════════════════════════════════════════════════════════════════════════

@shared_task
def auto_handle_unconfirmed_patients():
    from .models import Booking, BookingStatus, OPDDay

    today       = now().date()
    active_days = OPDDay.objects.filter(date=today, is_active=True)

    for opd_day in active_days:
        unconfirmed = Booking.objects.filter(
            doctor=opd_day.doctor,
            booking_date=today,
            session=opd_day.session,
            is_confirmed=False,
            status=BookingStatus.WAITING,
        ).count()
        logger.info(
            f"Dr. {opd_day.doctor.full_name} | {opd_day.session} | "
            f"{today} | {unconfirmed} unconfirmed."
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. RECALCULATE AVG CONSULT TIMES
# ═══════════════════════════════════════════════════════════════════════════

@shared_task
def recalculate_avg_consult_times():
    from .models import Booking, BookingStatus, OPDDay

    today       = now().date()
    active_days = OPDDay.objects.filter(date=today, is_active=True)

    for opd_day in active_days:
        done = Booking.objects.filter(
            doctor=opd_day.doctor,
            booking_date=today,
            session=opd_day.session,
            status=BookingStatus.DONE,
            consulting_started_at__isnull=False,
            consulting_ended_at__isnull=False,
        )
        if done.count() < 3:
            continue

        total   = sum(b.consulting_duration_minutes for b in done if b.consulting_duration_minutes)
        new_avg = max(1, round(total / done.count()))

        if opd_day.avg_consult_minutes != new_avg:
            OPDDay.objects.filter(id=opd_day.id).update(avg_consult_minutes=new_avg)
            logger.info(
                f"Avg updated: Dr. {opd_day.doctor.full_name} | "
                f"{opd_day.session} | {new_avg} min"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. NOTIFY PATIENTS 2 TOKENS AWAY
# ═══════════════════════════════════════════════════════════════════════════

def _build_queue_order(waiting_qs, late_cutoff):
    from django.db.models import Q
    from .models import WALKIN_RANGE, ONLINE_TOKEN_START, ONLINE_TOKEN_END

    GRACE_POSITION = 5

    main_list = list(
        waiting_qs.filter(
            Q(token_number__in=WALKIN_RANGE) |
            Q(
                token_number__range=(ONLINE_TOKEN_START, ONLINE_TOKEN_END),
                is_confirmed=True,
                confirmation_time__lte=late_cutoff,
            )
        ).order_by("token_number")
    )

    late_missed = list(
        waiting_qs.filter(
            token_number__range=(ONLINE_TOKEN_START, ONLINE_TOKEN_END),
            is_confirmed=True,
            confirmation_time__gt=late_cutoff,
        ).order_by("token_number")
    )

    insert_at = min(GRACE_POSITION, len(main_list))
    for i, late in enumerate(late_missed):
        main_list.insert(insert_at + i, late)

    return main_list


@shared_task
def notify_patients_two_tokens_away():
    from .models import Booking, BookingStatus, OPDDay

    today       = now().date()
    active_days = OPDDay.objects.filter(
        date=today, is_active=True
    ).select_related("doctor")

    for opd_day in active_days:
        doctor      = opd_day.doctor
        late_cutoff = opd_day.started_at + timedelta(minutes=10)

        waiting_qs = Booking.objects.filter(
            doctor=doctor,
            booking_date=today,
            session=opd_day.session,
            status=BookingStatus.WAITING,
            is_confirmed=True,
        ).select_related("patient__user")

        ordered = _build_queue_order(waiting_qs, late_cutoff)

        if len(ordered) < 3:
            continue

        target = ordered[2]

        if target.is_walkin or target.near_queue_notified or not target.patient:
            continue

        email = target.patient.user.email or ""
        phone = (
            getattr(target.patient, "phone", "")
            or getattr(target.patient.user, "phone", "")
            or ""
        )
        notified = False

        if email:
            try:
                send_mail(
                    subject=(
                        f"[MedQueue] Get Ready – Token #{target.token_number} | "
                        f"Dr. {doctor.full_name}"
                    ),
                    message=(
                        f"Dear {target.display_name},\n\n"
                        f"You are 2 patients away from being called by "
                        f"Dr. {doctor.full_name}.\n\n"
                        f"  Token Number : #{target.token_number}\n"
                        f"  Date         : {today}\n\n"
                        "Please make sure you are near the OPD counter and ready.\n\n"
                        "– MedQueue Team"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                notified = True
                logger.info(f"2-token email → {email} (Token #{target.token_number})")
            except Exception as e:
                logger.error(f"2-token email failed for booking {target.id}: {e}")

        if phone:
            try:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                client.messages.create(
                    body=(
                        f"[MedQueue] Hi {target.display_name}, you are 2 patients away "
                        f"from Dr. {doctor.full_name}. Token #{target.token_number}. "
                        "Please be ready at the OPD counter."
                    ),
                    from_=settings.TWILIO_PHONE_NUMBER,
                    to=phone,
                )
                notified = True
                logger.info(f"2-token SMS → {phone} (Token #{target.token_number})")
            except Exception as e:
                logger.error(f"2-token SMS failed for booking {target.id}: {e}")

        if notified:
            Booking.objects.filter(id=target.id).update(near_queue_notified=True)


# ═══════════════════════════════════════════════════════════════════════════
# MIGRATION REQUIRED
# Add to OPDDay in models.py then run makemigrations + migrate:
#
#     confirmation_prompt_sent = models.BooleanField(default=False)
# ═══════════════════════════════════════════════════════════════════════════
