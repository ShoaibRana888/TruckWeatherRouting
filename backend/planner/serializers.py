from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .domain.sampling import haversine_miles

MAX_LOAD_LB = 80_000  # US gross vehicle weight limit
INTERVAL_CHOICES = (10, 25, 50)
MAX_DEPARTURE_AHEAD = timedelta(hours=72)
MAX_DEPARTURE_PAST = timedelta(hours=2)
MIN_TRIP_MILES = 1.0


class LocationSerializer(serializers.Serializer):
    lon = serializers.FloatField(min_value=-180, max_value=180)
    lat = serializers.FloatField(min_value=-90, max_value=90)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        return (values["lon"], values["lat"])


class TripSerializer(serializers.Serializer):
    origin = LocationSerializer()
    destination = LocationSerializer()
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)

    def validate(self, attrs):
        if haversine_miles(attrs["origin"], attrs["destination"]) < MIN_TRIP_MILES:
            raise serializers.ValidationError("Origin and destination are too close together.")
        return attrs


class PlanSerializer(TripSerializer):
    departure_time = serializers.DateTimeField()
    interval_miles = serializers.ChoiceField(choices=INTERVAL_CHOICES)

    def validate_departure_time(self, value):
        now = timezone.now()
        if value < now - MAX_DEPARTURE_PAST:
            raise serializers.ValidationError("Departure time is in the past.")
        if value > now + MAX_DEPARTURE_AHEAD:
            raise serializers.ValidationError("Departure must be within the next 72 hours (the forecast window).")
        return value

    def validate_interval_miles(self, value):
        return int(value)
