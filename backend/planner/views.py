from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import planning
from .serializers import PlanSerializer, TripSerializer
from .services import mapbox
from .services.errors import NotFoundError, UpstreamError


def _error(message: str, code: int) -> Response:
    return Response({"detail": message}, status=code)


def _run(fn, *args):
    """Call a use case, translating upstream failures into clean API errors."""
    try:
        return Response(fn(*args))
    except NotFoundError as exc:
        return _error(str(exc), status.HTTP_404_NOT_FOUND)
    except UpstreamError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def config(request):
    """Browser-side map settings. Only a public (pk.) Mapbox token is ever exposed."""
    token = settings.MAPBOX_TOKEN
    return Response({"mapbox_token": token if token.startswith("pk.") else "", "map_style": settings.MAP_STYLE})


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "").strip()
    if len(query) < 2:
        return Response({"results": []})
    try:
        places = mapbox.geocode(query[:200])
    except UpstreamError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)
    return Response({"results": [{"name": p.name, "lon": p.lon, "lat": p.lat} for p in places]})


@api_view(["POST"])
def plan(request):
    data = PlanSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    return _run(
        planning.plan_trip, v["origin"], v["destination"], v["departure_time"], v["load_weight_lb"], v["interval_miles"]
    )


@api_view(["POST"])
def heatmap(request):
    data = TripSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    return _run(planning.build_heatmap, v["origin"], v["destination"], v["load_weight_lb"])
