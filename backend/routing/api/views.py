from rest_framework.response import Response
from rest_framework.views import APIView

from ..providers import geocoding
from ..services.heatmap import corridor_heatmap
from ..services.planner import TripRequest, plan_trip
from .presenters import present_heatmap, present_plan
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer


class HealthView(APIView):
    throttle_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class GeocodeView(APIView):
    def get(self, request):
        query = request.query_params.get("q", "")
        return Response({"results": [{"label": p.label, "lat": p.lat, "lon": p.lon} for p in geocoding.search(query)]})


class PlanView(APIView):
    def post(self, request):
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = plan_trip(
            TripRequest(
                origin=data["origin"],
                destination=data["destination"],
                departure=data["departure"],
                load_lbs=data["load_weight_lbs"],
                interval_mi=int(data["interval_miles"]),
            )
        )
        return Response(present_plan(plan))


class HeatmapView(APIView):
    def post(self, request):
        serializer = HeatmapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        heatmap = corridor_heatmap(data["corridor"], data["departure"], data["load_weight_lbs"], data["hours"])
        return Response(present_heatmap(heatmap))
