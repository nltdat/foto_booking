from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from user.models import PhotographerProfile
from user.permissions import IsPhotographer

from .models import Location
from .serializers import LocationSerializer, PhotographerLocationSyncSerializer


class LocationListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LocationSerializer
    queryset = Location.objects.all().order_by("city_province", "district")

    @extend_schema(
        tags=["Locations"],
        summary="Danh sach tinh/thanh va quan/huyen",
        responses={200: LocationSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PhotographerLocationSyncAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPhotographer]

    def _get_profile(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.request.user)
        return profile

    @extend_schema(
        tags=["Photographer Locations"],
        summary="Lay danh sach khu vuc hoat dong cua NAG hien tai",
        responses={200: LocationSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        profile = self._get_profile()
        locations = profile.active_locations.all().order_by("city_province", "district")
        data = LocationSerializer(locations, many=True).data
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Photographer Locations"],
        summary="Dong bo khu vuc hoat dong cho NAG",
        request=PhotographerLocationSyncSerializer,
        responses={200: LocationSerializer(many=True)},
    )
    def put(self, request, *args, **kwargs):
        profile = self._get_profile()
        serializer = PhotographerLocationSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        location_ids = serializer.validated_data["location_ids"]
        locations = list(Location.objects.filter(id__in=location_ids))
        profile.active_locations.set(locations)

        output = LocationSerializer(
            profile.active_locations.all().order_by("city_province", "district"),
            many=True,
        )
        return Response(output.data, status=status.HTTP_200_OK)
