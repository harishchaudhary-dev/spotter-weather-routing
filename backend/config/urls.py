from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.urls import include, path, re_path


def spa_index(_request):
    """Serve the built React app for any non-API path (single-service deploy). When the frontend is
    hosted separately (e.g. its own Vercel project) this backend is API-only."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return JsonResponse(
            {"service": "Stormline API", "status": "ok", "endpoints": ["/api/health", "/api/geocode", "/api/plan", "/api/heatmap"]}
        )
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("api/", include("routing.api.urls")),
    re_path(r"^(?!api/|static/).*$", spa_index),
]
