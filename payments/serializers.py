from rest_framework import serializers
from booking.models import Booking
from .models import Payment


# ======================================
# CREATE ORDER SERIALIZER
# ======================================
class CreateOrderSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()

    def validate_booking_id(self, value):
        request = self.context["request"]

        try:
            booking = Booking.objects.get(
                id=value,
                patient=request.user.patient
            )
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Invalid booking")

        if booking.payment_status == "paid":
            raise serializers.ValidationError("Booking already paid")

        return value


# ======================================
# VERIFY PAYMENT SERIALIZER
# ======================================
class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


# ======================================
# OPTIONAL: PAYMENT RESPONSE SERIALIZER
# ======================================
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"
