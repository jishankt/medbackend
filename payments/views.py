import razorpay
import hmac
import hashlib

from django.conf import settings
from django.db import transaction

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from booking.models import Booking
from .models import Payment
from .serializers import CreateOrderSerializer, VerifyPaymentSerializer


# ======================================
# CREATE RAZORPAY ORDER
# ======================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_order(request):

    # ✅ Use serializer HERE (inside view)
    serializer = CreateOrderSerializer(
        data=request.data,
        context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    booking_id = serializer.validated_data["booking_id"]

    booking = Booking.objects.get(
        id=booking_id,
        patient=request.user.patient
    )

    # Reuse existing pending payment
    existing_payment = Payment.objects.filter(
        booking=booking,
        status="created"
    ).first()

    if existing_payment:
        return Response({
            "order_id": existing_payment.razorpay_order_id,
            "amount": existing_payment.amount,
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "message": "Existing order reused"
        })

    amount = 10

    client = razorpay.Client(auth=(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET
    ))

    order = client.order.create({
        "amount": amount * 100,  # convert to paise
        "currency": "INR",
        "payment_capture": 1
    })

    Payment.objects.create(
        patient=request.user.patient,
        booking=booking,
        amount=amount,
        razorpay_order_id=order["id"]
    )

    return Response({
        "order_id": order["id"],
        "amount": amount,
        "razorpay_key": settings.RAZORPAY_KEY_ID
    })


# ======================================
# VERIFY PAYMENT
# ======================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment(request):

    # ✅ Use serializer here too
    serializer = VerifyPaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data
    order_id = data["razorpay_order_id"]
    payment_id = data["razorpay_payment_id"]
    signature = data["razorpay_signature"]

    try:
        payment = Payment.objects.get(razorpay_order_id=order_id)
    except Payment.DoesNotExist:
        return Response({"error": "Invalid order"}, status=404)

    if payment.status == "paid":
        return Response({"message": "Already verified"})

    generated_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256
    ).hexdigest()

    if generated_signature == signature:
        with transaction.atomic():
            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            payment.status = "paid"
            payment.save()

            booking = payment.booking
            booking.payment_status = "paid"
            booking.save()

        return Response({"message": "Payment verified"})

    else:
        payment.status = "failed"
        payment.save()

        payment.booking.payment_status = "failed"
        payment.booking.save()

        return Response({"error": "Payment failed"}, status=400)
