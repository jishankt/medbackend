"""
MedQueue Booking Serializers
"""

from rest_framework import serializers
from django.utils.timezone import now, localtime
from datetime import timedelta, time, datetime
from django.db import transaction

from .models import (
    District, Hospital, Department,
    Booking, OPDDay,
    OPDSession, BookingStatus, PaymentStatus,
    ONLINE_TOKEN_START, ONLINE_TOKEN_END, ONLINE_RANGE, WALKIN_RANGE,
    MAX_TOKENS_PER_SESSION,
)
from accounts.models import Patient, Doctor


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

SESSION_CUTOFF_HOURS = 2

SESSION_TIMES = {
    "morning": {"hour": 10, "minute": 0},
    "evening": {"hour": 15, "minute": 0},
}

# Time after which online booking is closed for each session.
# Freed online slots (ONLINE_RANGE) become available as walk-in tokens.
# Import this in views.py fetch_tokens to keep cutoff logic in sync.
ONLINE_BOOKING_CUTOFF = {
    "morning": time(8, 0),    # no new online bookings from 08:00 on booking day
    "evening": time(13, 0),   # no new online bookings from 13:00 on booking day
}


def _session_cutoff_passed(session: str) -> bool:
    info = SESSION_TIMES.get(session)
    if not info:
        return False
    local_now  = localtime(now())
    today      = local_now.date()
    session_dt = datetime(
        today.year, today.month, today.day,
        info["hour"], info["minute"],
        tzinfo=local_now.tzinfo,
    )
    cutoff = session_dt - timedelta(hours=SESSION_CUTOFF_HOURS)
    return local_now >= cutoff


# ─────────────────────────────────────────────
# SHARED HELPER — rolling weighted average
# ─────────────────────────────────────────────

def _compute_rolling_avg(doctor, booking_date, session=None, current_booking=None):
    """
    Computes a real-time rolling weighted average consultation time.
    - Last 3 completed consultations → 70% weight
    - Older consultations            → 30% weight
    - If current patient is running fast → nudges avg down slightly
    Falls back to OPDDay stored avg or 7 mins if no data.
    """
    qs = Booking.objects.filter(
        doctor=doctor,
        booking_date=booking_date,
        status=BookingStatus.DONE,
        consulting_started_at__isnull=False,
        consulting_ended_at__isnull=False,
    ).order_by("consulting_ended_at")

    if session:
        qs = qs.filter(session=session)

    durations = [
        b.consulting_duration_minutes
        for b in qs
        if b.consulting_duration_minutes is not None
        and b.consulting_duration_minutes > 0
    ]

    count = len(durations)

    if count == 0:
        try:
            opd_day = OPDDay.objects.get(doctor=doctor, date=booking_date)
            return float(opd_day.avg_consult_minutes or 7)
        except OPDDay.DoesNotExist:
            return 7.0

    if count == 1:
        weighted = durations[0]
    elif count == 2:
        weighted = sum(durations) / 2
    else:
        recent     = durations[-3:]
        older      = durations[:-3]
        recent_avg = sum(recent) / len(recent)
        if older:
            older_avg = sum(older) / len(older)
            weighted  = (recent_avg * 0.7) + (older_avg * 0.3)
        else:
            weighted = recent_avg

    # If current patient is running fast, nudge avg down
    if current_booking and current_booking.consulting_started_at:
        elapsed = (now() - current_booking.consulting_started_at).total_seconds() / 60
        if 0 < elapsed < weighted * 0.8:
            weighted = (weighted * 0.8) + (elapsed * 0.2)

    return round(max(1.0, weighted), 1)


# ─────────────────────────────────────────────
# LOCATION SERIALIZERS
# ─────────────────────────────────────────────

class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model  = District
        fields = ["id", "name"]


class HospitalSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source="district.name", read_only=True)

    class Meta:
        model  = Hospital
        fields = ["id", "name", "district", "district_name", "address"]


class DepartmentSerializer(serializers.ModelSerializer):
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)

    class Meta:
        model  = Department
        fields = ["id", "name", "hospital", "hospital_name"]


# ─────────────────────────────────────────────
# DOCTOR SERIALIZER
# ─────────────────────────────────────────────

class DoctorListSerializer(serializers.ModelSerializer):
    name          = serializers.SerializerMethodField()
    hospital      = serializers.CharField(source="hospital.name",    read_only=True)
    department    = serializers.CharField(source="department.name",  read_only=True)
    hospital_id   = serializers.IntegerField(source="hospital.id",   read_only=True)
    department_id = serializers.IntegerField(source="department.id", read_only=True)

    class Meta:
        model  = Doctor
        fields = ["id", "name", "hospital", "hospital_id", "department", "department_id", "is_approved"]

    def get_name(self, obj):
        return getattr(obj, "full_name", None) or obj.user.get_full_name() or obj.user.username


# ─────────────────────────────────────────────
# BOOKING CREATE SERIALIZER (Online)
# ─────────────────────────────────────────────

class BookingSerializer(serializers.ModelSerializer):
    doctor_id = serializers.PrimaryKeyRelatedField(
        queryset=Doctor.objects.filter(is_approved=True),
        source="doctor",
        write_only=True,
    )
    token_number    = serializers.IntegerField(read_only=True)
    payment_status  = serializers.CharField(read_only=True)
    status          = serializers.CharField(read_only=True)
    created_at      = serializers.DateTimeField(read_only=True)
    doctor_name     = serializers.SerializerMethodField()
    hospital_name   = serializers.CharField(source="doctor.hospital.name",   read_only=True)
    department_name = serializers.CharField(source="doctor.department.name", read_only=True)

    class Meta:
        model  = Booking
        fields = [
            "id", "doctor_id", "doctor_name", "hospital_name", "department_name",
            "session", "booking_date",
            "token_number", "payment_status", "status", "created_at",
        ]

    def get_doctor_name(self, obj):
        return getattr(obj.doctor, "full_name", None) or obj.doctor.user.username

    def validate(self, data):
        booking_date = data.get("booking_date")
        session      = data.get("session")
        doctor       = data.get("doctor")
        today        = now().date()

        # ── Date range checks ────────────────────────────────
        if booking_date < today:
            raise serializers.ValidationError("Cannot book past dates.")
        if booking_date > today + timedelta(days=7):
            raise serializers.ValidationError("Booking allowed only within the next 7 days.")

        # ── Online booking cutoff check ──────────────────────
        # If booking is for today and the session cutoff has passed,
        # online booking is closed — those slots have been freed to walk-in.
        if booking_date == today:
            cutoff       = ONLINE_BOOKING_CUTOFF.get(session)
            current_time = localtime(now()).time()
            if cutoff and current_time >= cutoff:
                raise serializers.ValidationError(
                    f"Online booking for the {session} session has closed. "
                    f"Walk-in tokens are available at the counter."
                )

        # ── Auth + patient checks ────────────────────────────
        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            raise serializers.ValidationError("Authentication required for online booking.")

        try:
            patient = Patient.objects.get(user=request.user)
        except Patient.DoesNotExist:
            raise serializers.ValidationError("Only patient accounts can book tokens.")

        # ── Duplicate booking check ──────────────────────────
        if Booking.objects.filter(
            patient=patient,
            booking_date=booking_date,
            doctor=doctor,
            session=session,
        ).exists():
            raise serializers.ValidationError(
                "You already have a booking with this doctor for this session today."
            )

        data["_patient"] = patient
        return data

    @transaction.atomic
    def create(self, validated_data):
        doctor       = validated_data["doctor"]
        session      = validated_data["session"]
        booking_date = validated_data["booking_date"]
        patient      = validated_data.pop("_patient")

        existing_count = Booking.objects.select_for_update().filter(
            doctor=doctor,
            session=session,
            booking_date=booking_date,
            token_number__gte=ONLINE_TOKEN_START,
            token_number__lte=ONLINE_TOKEN_END,
        ).count()

        online_capacity = ONLINE_TOKEN_END - ONLINE_TOKEN_START + 1
        if existing_count >= online_capacity:
            raise serializers.ValidationError(
                f"Online session full. Maximum {online_capacity} tokens per session."
            )

        token_number = ONLINE_TOKEN_START + existing_count

        return Booking.objects.create(
            patient=patient,
            doctor=doctor,
            session=session,
            booking_date=booking_date,
            token_number=token_number,
            payment_status=PaymentStatus.PENDING,
            status=BookingStatus.PENDING,
            is_confirmed=False,
        )


# ─────────────────────────────────────────────
# WALK-IN BOOKING SERIALIZER
# ─────────────────────────────────────────────

class WalkinBookingSerializer(serializers.Serializer):
    doctor_id    = serializers.IntegerField()
    session      = serializers.ChoiceField(choices=OPDSession.choices)
    booking_date = serializers.DateField()
    token_number = serializers.IntegerField()
    patient_name = serializers.CharField(max_length=100)

    def validate_token_number(self, value):
        """
        Accept tokens from WALKIN_RANGE, and also freed online tokens
        when online booking is closed for today.
        Freed online slots = ONLINE_RANGE tokens with no existing booking,
        available at the counter after the session cutoff.
        """
        if value in WALKIN_RANGE:
            return value

        # Check if this is a freed online token (cutoff passed for today)
        if value in ONLINE_RANGE:
            # We validate the cutoff in validate() where we have full data;
            # at this point just allow ONLINE_RANGE tokens through so the
            # cross-field validate() can make the final call.
            return value

        raise serializers.ValidationError(
            f"Token #{value} is not a valid walk-in or freed online token."
        )

    def validate(self, data):
        try:
            doctor = Doctor.objects.get(id=data["doctor_id"], is_approved=True)
        except Doctor.DoesNotExist:
            raise serializers.ValidationError("Doctor not found or not approved.")
        data["doctor"] = doctor

        token_number = data["token_number"]
        session      = data["session"]
        booking_date = data["booking_date"]
        today        = now().date()

        # ── If token is from ONLINE_RANGE, only allow it as walk-in
        # ── when online booking is closed for today's session ────────
        if token_number in ONLINE_RANGE:
            if booking_date != today:
                raise serializers.ValidationError(
                    f"Token #{token_number} is an online token and cannot be used "
                    f"as walk-in for future dates."
                )
            cutoff       = ONLINE_BOOKING_CUTOFF.get(session)
            current_time = localtime(now()).time()
            if not cutoff or current_time < cutoff:
                raise serializers.ValidationError(
                    f"Token #{token_number} is an online token. "
                    f"Online booking is still open for the {session} session."
                )
            # At this point: today, cutoff passed — token is a freed online slot.
            # Fall through to the duplicate check below.

        # ── Duplicate check (applies to both walkin and freed online) ─
        if Booking.objects.filter(
            doctor=doctor,
            session=session,
            booking_date=booking_date,
            token_number=token_number,
        ).exists():
            raise serializers.ValidationError(
                f"Token #{token_number} is already booked for this session."
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        return Booking.objects.create(
            doctor=validated_data["doctor"],
            session=validated_data["session"],
            booking_date=validated_data["booking_date"],
            token_number=validated_data["token_number"],
            walkin_name=validated_data["patient_name"],
            payment_status=PaymentStatus.OFFLINE,
            status=BookingStatus.WAITING,
            is_confirmed=True,
            confirmation_time=now(),
            queue_insert_time=now(),
            patient=None,
        )


# ─────────────────────────────────────────────
# BOOKING DETAIL SERIALIZER
# ─────────────────────────────────────────────

class BookingDetailSerializer(serializers.ModelSerializer):
    patient_name                = serializers.SerializerMethodField()
    doctor_name                 = serializers.SerializerMethodField()
    hospital_name               = serializers.CharField(source="doctor.hospital.name",   read_only=True)
    department_name             = serializers.CharField(source="doctor.department.name", read_only=True)
    is_online                   = serializers.BooleanField(read_only=True)
    is_walkin                   = serializers.BooleanField(read_only=True)
    consulting_duration_minutes = serializers.FloatField(read_only=True)

    class Meta:
        model  = Booking
        fields = [
            "id", "token_number", "session", "booking_date",
            "patient_name", "doctor_name", "hospital_name", "department_name",
            "payment_status", "status",
            "is_confirmed", "confirmation_time",
            "queue_insert_time",
            "consulting_started_at", "consulting_ended_at",
            "consulting_duration_minutes",
            "is_online", "is_walkin",
            "created_at",
        ]

    def get_patient_name(self, obj):
        return obj.display_name

    def get_doctor_name(self, obj):
        return getattr(obj.doctor, "full_name", None) or obj.doctor.user.username


# ─────────────────────────────────────────────
# BOOKING HISTORY SERIALIZER
# ─────────────────────────────────────────────

class BookingHistorySerializer(serializers.ModelSerializer):
    hospital        = serializers.CharField(source="doctor.hospital.name",   read_only=True)
    department      = serializers.CharField(source="doctor.department.name", read_only=True)
    doctor_name     = serializers.SerializerMethodField()
    session_display = serializers.CharField(source="get_session_display",    read_only=True)

    class Meta:
        model  = Booking
        fields = [
            "id", "hospital", "department", "doctor_name",
            "session", "session_display", "booking_date",
            "token_number", "payment_status", "status",
            "is_confirmed", "created_at",
        ]

    def get_doctor_name(self, obj):
        return getattr(obj.doctor, "full_name", None) or obj.doctor.user.username


# ─────────────────────────────────────────────
# PATIENT TOKEN STATUS SERIALIZER
# ─────────────────────────────────────────────

class PatientTokenStatusSerializer(serializers.ModelSerializer):
    tokens_ahead           = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    current_token          = serializers.SerializerMethodField()
    avg_consult_minutes    = serializers.SerializerMethodField()
    doctor_name            = serializers.SerializerMethodField()
    hospital               = serializers.CharField(source="doctor.hospital.name",   read_only=True)
    department             = serializers.CharField(source="doctor.department.name", read_only=True)

    class Meta:
        model  = Booking
        fields = [
            "id", "token_number", "session", "booking_date",
            "status", "is_confirmed",
            "current_token", "tokens_ahead",
            "estimated_wait_minutes", "avg_consult_minutes",
            "consulting_started_at",
            "doctor_name", "hospital", "department",
        ]

    def _get_opd_day(self, obj):
        """Cached OPDDay lookup — avoids repeated DB hits within one serialization."""
        if not hasattr(self, "_opd_day_cache"):
            try:
                self._opd_day_cache = OPDDay.objects.get(
                    doctor=obj.doctor, date=obj.booking_date
                )
            except OPDDay.DoesNotExist:
                self._opd_day_cache = None
        return self._opd_day_cache

    def _get_current_consulting(self, obj):
        """Get the patient currently being consulted."""
        if not hasattr(self, "_current_consulting_cache"):
            self._current_consulting_cache = Booking.objects.filter(
                doctor=obj.doctor,
                booking_date=obj.booking_date,
                session=obj.session,
                status=BookingStatus.CONSULTING,
                consulting_started_at__isnull=False,
            ).first()
        return self._current_consulting_cache

    def get_doctor_name(self, obj):
        return getattr(obj.doctor, "full_name", None) or obj.doctor.user.username

    def get_current_token(self, obj):
        current = self._get_current_consulting(obj)
        return current.token_number if current else 0

    def get_tokens_ahead(self, obj):
        """
        Returns how many confirmed patients are ahead in the queue.
        Returns None if patient has not confirmed yet (not in queue).
        """
        if not obj.is_confirmed:
            return None

        if not obj.queue_insert_time:
            # Confirmed but no insert time recorded — count all confirmed waiting
            return Booking.objects.filter(
                doctor=obj.doctor,
                booking_date=obj.booking_date,
                session=obj.session,
                status__in=[BookingStatus.WAITING, BookingStatus.CONSULTING],
                is_confirmed=True,
            ).count()

        return Booking.objects.filter(
            doctor=obj.doctor,
            booking_date=obj.booking_date,
            session=obj.session,
            status__in=[BookingStatus.WAITING, BookingStatus.CONSULTING],
            is_confirmed=True,
            queue_insert_time__lt=obj.queue_insert_time,
        ).count()

    def get_avg_consult_minutes(self, obj):
        """
        Real-time rolling weighted average.
        Returns None if OPD has not started yet so the frontend
        can show 'OPD not started' instead of a number.
        """
        opd_day = self._get_opd_day(obj)
        if not opd_day or not opd_day.is_active:
            return None

        current = self._get_current_consulting(obj)
        return _compute_rolling_avg(
            doctor=obj.doctor,
            booking_date=obj.booking_date,
            session=obj.session,
            current_booking=current,
        )

    def get_estimated_wait_minutes(self, obj):
        """
        Real-time estimate: (tokens_ahead × rolling_avg) + remaining time for current patient.
        Returns None if not confirmed or OPD not started.
        Never returns negative.
        """
        if not obj.is_confirmed:
            return None

        avg = self.get_avg_consult_minutes(obj)
        if avg is None:
            return None

        ahead = self.get_tokens_ahead(obj)
        if ahead is None:
            return None

        current = self._get_current_consulting(obj)
        remaining_for_current = 0
        if current and current.consulting_started_at:
            elapsed = (now() - current.consulting_started_at).total_seconds() / 60
            remaining_for_current = max(0, avg - elapsed)

        total = (ahead * avg) + remaining_for_current
        return round(max(0, total), 1)
