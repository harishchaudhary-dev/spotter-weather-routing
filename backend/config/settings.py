"""Django settings. Everything deploy-specific comes from environment variables (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# Never default to debug on a hosting platform (Vercel and Render both set these variables).
ON_PLATFORM = bool(os.getenv("VERCEL") or os.getenv("RENDER"))
DEBUG = env_bool("DJANGO_DEBUG", not ON_PLATFORM)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key")
if not DEBUG and SECRET_KEY == "dev-only-insecure-key":
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com,.vercel.app")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# The API is stateless JSON with no cookies, sessions or auth, so there is no CSRF surface.
SILENCED_SYSTEM_CHECKS = ["security.W003"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# The app is stateless (no models), so no database is configured.
DATABASES = {}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": False,
        "OPTIONS": {},
    }
]

# --- Static files: in production Django also serves the built React app (single deploy unit).
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"))
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --- CORS (only needed when the frontend is hosted on a different origin).
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
# The API is public, read-only and cookie-less, so any Vercel-hosted frontend may call it by default.
CORS_ALLOWED_ORIGIN_REGEXES = env_list("CORS_ALLOWED_ORIGIN_REGEXES", r"^https://[a-z0-9-]+\.vercel\.app$")

# --- Cache: Redis when available (shared across gunicorn workers), otherwise in-process memory.
REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"IGNORE_EXCEPTIONS": True},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "OPTIONS": {"MAX_ENTRIES": 50_000},
        }
    }

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": os.getenv("API_RATE_LIMIT", "120/min")},
    "EXCEPTION_HANDLER": "routing.api.exceptions.api_exception_handler",
}

# --- Third-party providers (all keyless by default).
HTTP_USER_AGENT = os.getenv("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0 (assessment project)")
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "20"))
OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")
PHOTON_URL = os.getenv("PHOTON_URL", "https://photon.komoot.io")
OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
# Optional commercial key (use with OPEN_METEO_URL=https://customer-api.open-meteo.com/v1/forecast).
OPEN_METEO_API_KEY = os.getenv("OPEN_METEO_API_KEY", "")

# --- Domain tuning.
# OSRM's public server only has a car profile; per-segment speeds are capped to a truck's
# realistic cruising speed so checkpoint ETAs (and therefore the weather we look up) are honest.
TRUCK_MAX_SPEED_MPH = float(os.getenv("TRUCK_MAX_SPEED_MPH", "65"))
WEATHER_CACHE_TTL_S = int(os.getenv("WEATHER_CACHE_TTL_S", str(30 * 60)))
# Forecast sampling cell (degrees). Checkpoints/heatmap points in one cell share a forecast. 0.2° (~13 mi)
# is close to the forecast models' effective resolution and keeps a coast-to-coast trip inside
# Open-Meteo's free tier (600 locations/min). Use 0.1 with a commercial key.
WEATHER_CELL_DEG = float(os.getenv("WEATHER_CELL_DEG", "0.2"))
ROUTE_CACHE_TTL_S = int(os.getenv("ROUTE_CACHE_TTL_S", str(6 * 60 * 60)))
MAX_DEPARTURE_DAYS_AHEAD = int(os.getenv("MAX_DEPARTURE_DAYS_AHEAD", "7"))

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^api/health$"]  # platform health checks hit the container over plain HTTP
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
