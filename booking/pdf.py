"""
booking/utils/pdf.py
====================
Generates an OPD ticket PDF for a booking using ReportLab.
Install: pip install reportlab

Returns: bytes (PDF content)
"""

import io
import qrcode
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import Image as RLImage


# ─────────────────────────────────────────────
# BRAND COLOURS
# ─────────────────────────────────────────────
PRIMARY   = HexColor("#1A5276")   # deep blue
SECONDARY = HexColor("#2E86C1")   # mid blue
ACCENT    = HexColor("#AED6F1")   # light blue
SUCCESS   = HexColor("#1E8449")   # green
LIGHT_BG  = HexColor("#EBF5FB")
BORDER    = HexColor("#2E86C1")


def _qr_image(data: str, size_mm: float = 30) -> RLImage:
    """Generate a QR code image as a ReportLab Image."""
    qr = qrcode.QRCode(box_size=5, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    size = size_mm * mm
    return RLImage(buf, width=size, height=size)


def generate_ticket_pdf(booking) -> bytes:
    """
    Generate an OPD ticket PDF for a Booking instance.

    Parameters
    ----------
    booking : Booking
        Must have select_related("patient__user", "doctor__hospital", "doctor__department")

    Returns
    -------
    bytes
        Raw PDF bytes ready for email attachment or HTTP response.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A5,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "TicketTitle",
        parent=styles["Normal"],
        fontSize=18,
        textColor=white,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "TicketSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=ACCENT,
        alignment=TA_CENTER,
        fontName="Helvetica",
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=8,
        textColor=SECONDARY,
        fontName="Helvetica-Bold",
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=10,
        textColor=black,
        fontName="Helvetica",
    )
    token_style = ParagraphStyle(
        "Token",
        parent=styles["Normal"],
        fontSize=48,
        textColor=PRIMARY,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    token_label_style = ParagraphStyle(
        "TokenLabel",
        parent=styles["Normal"],
        fontSize=10,
        textColor=SECONDARY,
        alignment=TA_CENTER,
        fontName="Helvetica",
    )
    note_style = ParagraphStyle(
        "Note",
        parent=styles["Normal"],
        fontSize=7.5,
        textColor=HexColor("#555555"),
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=7,
        textColor=HexColor("#888888"),
        alignment=TA_CENTER,
        fontName="Helvetica",
    )

    # ── Helper: header banner (drawn as a coloured table row) ──────────
    header_data = [[
        Paragraph("🏥  MedQueue", title_style),
    ]]
    header_table = Table(header_data, colWidths=[doc.width])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [5, 5, 0, 0]),
    ]))

    sub_data = [[Paragraph("Official OPD Appointment Ticket", subtitle_style)]]
    sub_table = Table(sub_data, colWidths=[doc.width])
    sub_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SECONDARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROUNDEDCORNERS", [0, 0, 0, 0]),
    ]))

    # ── Token number ───────────────────────────────────────────────────
    token_data = [[
        Paragraph("TOKEN NUMBER", token_label_style),
    ], [
        Paragraph(f"#{booking.token_number:02d}", token_style),
    ]]
    token_table = Table(token_data, colWidths=[doc.width])
    token_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))

    # ── Info rows ─────────────────────────────────────────────────────
    def info_row(label, value):
        return [
            Paragraph(label, label_style),
            Paragraph(str(value), value_style),
        ]

    info_data = [
        info_row("PATIENT",   booking.patient_display_name),
        info_row("DATE",      booking.booking_date.strftime("%d %B %Y")),
        info_row("SESSION",   booking.get_session_display()),
        info_row("DOCTOR",    f"Dr. {booking.doctor.full_name}"),
        info_row("HOSPITAL",  booking.doctor.hospital.name),
        info_row("DEPT",      booking.doctor.department.name),
        info_row("BOOKING ID", f"MQ-{booking.id:06d}"),
    ]
    col_w = doc.width
    info_table = Table(info_data, colWidths=[col_w * 0.32, col_w * 0.68])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), LIGHT_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, ACCENT),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # ── QR code ────────────────────────────────────────────────────────
    qr_data = f"MQ-{booking.id:06d}|TOKEN:{booking.token_number}|DATE:{booking.booking_date}"
    qr_img  = _qr_image(qr_data, size_mm=28)

    qr_data_row = [[
        qr_img,
        Paragraph(
            f"<b>Scan to verify</b><br/>Booking ID: MQ-{booking.id:06d}",
            ParagraphStyle(
                "QRText", parent=styles["Normal"],
                fontSize=8, textColor=HexColor("#333333"),
                fontName="Helvetica", leftIndent=6,
            )
        )
    ]]
    qr_table = Table(qr_data_row, colWidths=[32 * mm, doc.width - 32 * mm])
    qr_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))

    # ── Assemble story ────────────────────────────────────────────────
    story = [
        header_table,
        sub_table,
        Spacer(1, 3 * mm),
        token_table,
        Spacer(1, 2 * mm),
        info_table,
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", thickness=0.5, color=ACCENT),
        Spacer(1, 2 * mm),
        qr_table,
        HRFlowable(width="100%", thickness=0.5, color=ACCENT),
        Spacer(1, 2 * mm),
        Paragraph(
            "Please arrive 15 minutes before your session. Confirm your token in the MedQueue app "
            "within 30 minutes of OPD start to secure your queue position.",
            note_style,
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "This is a computer-generated ticket. No signature required. | medqueue.com",
            footer_style,
        ),
    ]

    doc.build(story)
    return buf.getvalue()
