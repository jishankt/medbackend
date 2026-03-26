"""
MedQueue Booking Utilities
==========================
Shared helper functions used across views, tasks, and serializers.
"""

from django.core.mail import EmailMessage
from django.utils.timezone import now
from rest_framework.response import Response
from rest_framework import status

from accounts.models import Patient, Doctor
from .models import Booking, OPDDay, BookingStatus


# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

def get_patient_or_403(user):
    """
    Returns (patient, None) on success.
    Returns (None, Response 403) if user is not a patient.
    """
    try:
        return Patient.objects.get(user=user), None
    except Patient.DoesNotExist:
        return None, Response({"error": "Only patient accounts can perform this action."}, status=403)


def get_doctor_or_403(user):
    """
    Returns (doctor, None) on success.
    Returns (None, Response 403) if user is not a doctor.
    """
    try:
        return Doctor.objects.get(user=user), None
    except Doctor.DoesNotExist:
        return None, Response({"error": "Only doctor accounts can perform this action."}, status=403)


# ─────────────────────────────────────────────
# QUEUE POSITION
# ─────────────────────────────────────────────

def compute_queue_position(booking):
    """
    When a patient confirms attendance, they are inserted into the queue
    5 positions ahead of the current last confirmed patient.

    Returns a dict with:
    - position: absolute position in queue
    - tokens_ahead: number of confirmed/waiting tokens before this one
    - estimated_wait_minutes: estimated waiting time
    """
    tokens_ahead = Booking.objects.filter(
        doctor=booking.doctor,
        booking_date=booking.booking_date,
        session=booking.session,
        status__in=[BookingStatus.WAITING, BookingStatus.CONSULTING],
        is_confirmed=True,
        queue_insert_time__lt=now(),
    ).count()

    try:
        opd_day = OPDDay.objects.get(doctor=booking.doctor, date=booking.booking_date)
        avg = opd_day.avg_consult_minutes
    except OPDDay.DoesNotExist:
        avg = 7

    return {
        "position"              : tokens_ahead + 1,
        "tokens_ahead"          : tokens_ahead,
        "estimated_wait_minutes": tokens_ahead * avg,
    }


# ─────────────────────────────────────────────
# EMAIL HELPERS
# ─────────────────────────────────────────────

def send_opd_ticket_email(booking):
    """
    Send the OPD ticket as a PDF attachment to the patient's email.
    PDF generation is handled by generate_ticket_pdf().
    """
    if not booking.patient or not booking.patient.user.email:
        return False

    try:
        pdf_bytes = generate_ticket_pdf(booking)
        email = EmailMessage(
            subject=f"[MedQueue] Your OPD Ticket – Token #{booking.token_number}",
            body=(
                f"Dear {booking.display_name},\n\n"
                f"Your OPD token has been booked successfully.\n\n"
                f"Doctor   : Dr. {booking.doctor.full_name}\n"
                f"Hospital : {booking.doctor.hospital.name}\n"
                f"Dept     : {booking.doctor.department.name}\n"
                f"Date     : {booking.booking_date}\n"
                f"Session  : {booking.get_session_display()}\n"
                f"Token #  : {booking.token_number}\n\n"
                "Please find your OPD ticket attached.\n\n"
                "Important: You must confirm your attendance once the OPD starts.\n\n"
                "– MedQueue Team"
            ),
            from_email="no-reply@medqueue.com",
            to=[booking.patient.user.email],
        )
        email.attach(
            filename=f"OPD_Ticket_{booking.token_number}.pdf",
            content=pdf_bytes,
            mimetype="application/pdf",
        )
        email.send(fail_silently=True)
        booking.ticket_sent = True
        booking.save(update_fields=["ticket_sent"])
        return True
    except Exception:
        return False


def send_reminder_email(booking):
    """
    Send 30-minute reminder email asking the patient to confirm attendance.
    """
    if not booking.patient or not booking.patient.user.email:
        return False

    send_mail_safe(
        subject=f"[MedQueue] Action Required – Confirm Your Token #{booking.token_number}",
        message=(
            f"Dear {booking.display_name},\n\n"
            f"Dr. {booking.doctor.full_name}'s OPD session will start in 30 minutes.\n\n"
            f"Token #  : {booking.token_number}\n"
            f"Date     : {booking.booking_date}\n"
            f"Session  : {booking.get_session_display()}\n\n"
            "⚠️  Please log in to MedQueue and confirm your attendance.\n"
            "If you do not confirm, you will be placed in the unconfirmed queue "
            "and may miss your turn.\n\n"
            "– MedQueue Team"
        ),
        to=[booking.patient.user.email],
    )
    booking.reminder_sent = True
    booking.save(update_fields=["reminder_sent"])
    return True


def send_mail_safe(subject, message, to, from_email="no-reply@medqueue.com"):
    """Wrapper for send_mail with fail_silently."""
    from django.core.mail import send_mail
    send_mail(subject=subject, message=message, from_email=from_email,
              recipient_list=to, fail_silently=True)


# ─────────────────────────────────────────────
# PDF TICKET GENERATION
# ─────────────────────────────────────────────

def generate_ticket_pdf(booking):
    from io import BytesIO
    from reportlab.lib.pagesizes import A6
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    buffer = BytesIO()
    PAGE_W, PAGE_H = A6

    c = canvas.Canvas(buffer, pagesize=A6)

    BLUE        = colors.HexColor("#1a73e8")
    DARK_BLUE   = colors.HexColor("#1565c0")
    WHITE       = colors.white
    MUTED       = colors.HexColor("#5f6368")
    ROW_ALT     = colors.HexColor("#f8f9fa")
    BORDER      = colors.HexColor("#e0e0e0")
    WARN_BG     = colors.HexColor("#fff8e1")
    WARN_BORDER = colors.HexColor("#ffe082")
    WARN_TEXT   = colors.HexColor("#e65100")
    TEXT_DARK   = colors.HexColor("#202124")

    # Header
    header_h = 28 * mm
    c.setFillColor(BLUE)
    c.rect(0, PAGE_H - header_h, PAGE_W, header_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 14 * mm, "MedQueue")
    c.setFillColor(colors.HexColor("#bbdefb"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 21 * mm, "OPD Appointment Ticket")

    # Token block
    token_top = PAGE_H - header_h
    token_h = 26 * mm
    c.setFillColor(DARK_BLUE)
    c.rect(0, token_top - token_h, PAGE_W, token_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#90caf9"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(PAGE_W / 2, token_top - 8 * mm, "TOKEN  NUMBER")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 38)
    c.drawCentredString(PAGE_W / 2, token_top - 20 * mm, f"#{booking.token_number}")

    # Info rows
    info_top = token_top - token_h - 3 * mm
    row_h = 8.5 * mm
    label_x = 8 * mm
    value_x = 38 * mm
    right_x = PAGE_W - 6 * mm

    fields = [
        ("PATIENT",    booking.display_name),
        ("DOCTOR",     f"Dr. {booking.doctor.full_name}"),
        ("HOSPITAL",   booking.doctor.hospital.name),
        ("DEPARTMENT", booking.doctor.department.name),
        ("DATE",       str(booking.booking_date)),
        ("SESSION",    booking.get_session_display()),
        ("BOOKED AT",  booking.created_at.strftime("%d %b %Y  %H:%M")),
    ]

    for i, (label, value) in enumerate(fields):
        y_top    = info_top - i * row_h
        y_bottom = y_top - row_h
        if i % 2 == 1:
            c.setFillColor(ROW_ALT)
            c.rect(0, y_bottom, PAGE_W, row_h, fill=1, stroke=0)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.line(label_x, y_bottom, right_x, y_bottom)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6.5)
        c.drawString(label_x, y_bottom + 5.5, label)
        c.setFillColor(TEXT_DARK)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(value_x, y_bottom + 5.5, value)

    # Warning box
    warn_top = info_top - len(fields) * row_h - 4 * mm
    warn_h   = 10 * mm
    margin   = 7 * mm
    c.setFillColor(WARN_BG)
    c.setStrokeColor(WARN_BORDER)
    c.setLineWidth(0.5)
    c.roundRect(margin, warn_top - warn_h, PAGE_W - 2 * margin, warn_h, 2 * mm, fill=1, stroke=1)
    c.setFillColor(WARN_TEXT)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(PAGE_W / 2, warn_top - 4.5 * mm,
                        "! Confirm your attendance once the OPD session starts.")

    c.save()
    return buffer.getvalue()