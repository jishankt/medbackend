from django.contrib import admin
from .models import Doctor,OPDStaff,Patient

# Register your models here.
admin.site.register(Patient)
admin.site.register(OPDStaff)
admin.site.register(Doctor)

