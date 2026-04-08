from rest_framework.routers import DefaultRouter

from .views import BookingBidViewSet, BookingViewSet

router = DefaultRouter()
router.register("bookings", BookingViewSet, basename="bookings")
router.register("booking-bids", BookingBidViewSet, basename="booking-bids")

urlpatterns = router.urls
