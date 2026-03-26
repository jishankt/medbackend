from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from rest_framework.routers import DefaultRouter
from rest_framework.authtoken import views as authview

from accounts import views


router = DefaultRouter()
router.register(r'doctors', views.DoctorView, basename='doctor')
router.register(r'patients', views.PatientView, basename='patient')
router.register(r'opdstaff', views.OPDStaffView, basename='opdstaff')

# Add these for frontend dropdowns


urlpatterns = [
    path('admin/', admin.site.urls),

    # Token authentication (optional, you already have custom logins)
    path('api/token/', authview.obtain_auth_token),

    # API routes
    path('api/', include(router.urls)),
    path('api/booking/', include('booking.urls')),

    # main urls.py
    path('api/payments/', include('payments.urls')),

]

# Media files
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )