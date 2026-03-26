from django.contrib import admin

# Register your models here.
from .models import District, Hospital, Department,  Booking
admin.site.register(District)
admin.site.register(Hospital)
admin.site.register(Department)
admin.site.register(Booking)
