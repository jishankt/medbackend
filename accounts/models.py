from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User


class BaseProfile(models.Model):
    """
    Abstract base model for common fields
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class OPDStaff(BaseProfile):
    """
    OPD staff who can approve doctors
    """

    hospital = models.ForeignKey(
        "booking.Hospital",
        on_delete=models.CASCADE,
        related_name="opd_staff"
    )

    def __str__(self):
        return f"{self.hospital.name} - OPD"


class Doctor(BaseProfile):
    """
    Doctor account, requires OPD approval
    """

    full_name = models.CharField(max_length=100)

    hospital = models.ForeignKey(
        "booking.Hospital",
        on_delete=models.CASCADE,
        related_name="doctors"
    )

    department = models.ForeignKey(
        "booking.Department",
        on_delete=models.CASCADE,
        related_name="doctors"
    )

    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name


class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    otp_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name