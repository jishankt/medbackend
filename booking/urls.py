"""
MedQueue Booking URL Configuration
"""

from django.urls import path
from .views import (
    # ── Public / Lookup ──
    district_list,
    hospital_list,
    department_list,
    opd_sessions,
    doctors_by_department,
    approved_doctors,
    fetch_tokens,
    queue_status,

    # ── Patient ──
    book_token,
    booking_history,
    cancel_booking,
    patient_token_status,
    patient_confirm_attendance,
    patient_reject_booking,

    # ── Doctor ──
    doctor_dashboard,
    start_opd,
    doctor_next_token,
    skip_token,
    end_opd,

    # ── Staff / Admin ──
    book_walkin_token,
    tokens_by_date,
    opd_dashboard,
    approve_booking,
    reject_booking,
    doctor_tokens_by_date,

    # ── Doctor Approvals (OPD Staff) ──
    pending_doctors,
    approve_doctor,
    reject_doctor,

    # ── Consultation History ──
    consultation_history,
    resend_opd_notification,
    staff_confirm_attendance,
    available_booking_dates
)

urlpatterns = [

    # ════════════════════════════════════════
    # PUBLIC / LOOKUP
    # ════════════════════════════════════════
    path("districts/",           district_list,         name="district-list"),
    path("hospitals/",           hospital_list,         name="hospital-list"),
    path("departments/",         department_list,       name="department-list"),
    path("opd-sessions/",        opd_sessions,          name="opd-sessions"),
    path("doctors/",             doctors_by_department, name="doctors-by-department"),
    path("doctors/all/",         approved_doctors,      name="approved-doctors"),
    path("tokens/availability/", fetch_tokens,          name="fetch-tokens"),
    path("queue/status/",        queue_status,          name="queue-status"),

    # ════════════════════════════════════════
    # PATIENT
    # ════════════════════════════════════════
    path("patient/book/",                        book_token,                 name="book-token"),
    path("patient/history/",                     booking_history,            name="booking-history"),
    path("patient/cancel/<int:booking_id>/",     cancel_booking,             name="cancel-booking"),
    path("patient/token-status/",                patient_token_status,       name="patient-token-status"),
    path("patient/confirm/<int:booking_id>/",    patient_confirm_attendance, name="patient-confirm"),
    path("patient/reject/<int:booking_id>/",     patient_reject_booking,     name="patient-reject"),

    # ════════════════════════════════════════
    # DOCTOR
    # ════════════════════════════════════════
    path("doctor/dashboard/",                    doctor_dashboard,  name="doctor-dashboard"),
    path("doctor/start-opd/",                    start_opd,         name="start-opd"),
    path("doctor/next-token/",                   doctor_next_token, name="doctor-next-token"),
    path("doctor/skip/<int:booking_id>/",        skip_token,        name="skip-token"),
    path("doctor/end-opd/",                      end_opd,           name="end-opd"),

    # ════════════════════════════════════════
    # STAFF / ADMIN
    # ════════════════════════════════════════
    path("staff/walkin/",                        book_walkin_token,     name="book-walkin"),
    path("staff/tokens/",                        tokens_by_date,        name="tokens-by-date"),
    path("staff/opd-dashboard/",                 opd_dashboard,         name="opd-dashboard"),
    path("staff/doctor-tokens/",                 doctor_tokens_by_date, name="doctor-tokens-by-date"),
    path("staff/approve/<int:booking_id>/",      approve_booking,       name="approve-booking"),
    path("staff/reject/<int:booking_id>/",       reject_booking,        name="reject-booking"),
    path("available-dates/", available_booking_dates),

    # Doctor registration approvals
    path("staff/pending-doctors/",               pending_doctors,  name="pending-doctors"),
    path("staff/approve-doctor/<int:doctor_id>/", approve_doctor,  name="approve-doctor"),
    path("staff/reject-doctor/<int:doctor_id>/",  reject_doctor,   name="reject-doctor"),

    # Consultation history
    path("staff/consultation-history/",          consultation_history, name="consultation-history"),
    path("staff/resend-notification/<int:booking_id>/", resend_opd_notification,  name="resend-notification"),
    path("staff/confirm-attendance/<int:booking_id>/",  staff_confirm_attendance,  name="staff-confirm-attendance"),
]