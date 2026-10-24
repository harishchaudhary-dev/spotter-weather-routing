from django.conf import settings
from django.http import FileResponse, HttpResponseNotFound
from django.urls import include, path, re_path


def spa_index(_request):
    """Serve the built React app for any non-API path (production single-service deploy)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponseNotFound("Frontend not built. Run `npm run build` in frontend/ or use the Vite dev server.")
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("api/", include("routing.api.urls")),
    re_path(r"^(?!api/|static/).*$", spa_index),
]
