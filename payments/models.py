from django.db import models

class Payment(models.Model):
    patient = models.ForeignKey(
        "accounts.Patient",
        on_delete=models.CASCADE,
        related_name="payments"
    )

    booking = models.ForeignKey(
        "booking.Booking",
        on_delete=models.CASCADE,
        related_name="payments"
    )

    amount = models.PositiveIntegerField()

    # 🔥 add db_index here
    razorpay_order_id = models.CharField(
        max_length=200,
        unique=True,
        db_index=True
    )

    razorpay_payment_id = models.CharField(max_length=200, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=500, blank=True, null=True)

    # ⭐ optional future field for tracking payment status

    status = models.CharField(
        max_length=20,
        choices=[
            ("created", "Created"),
            ("paid", "Paid"),
            ("failed", "Failed"),
        ],
        default="created"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # ⭐ auto update field
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.patient} - {self.booking} - {self.status}"
