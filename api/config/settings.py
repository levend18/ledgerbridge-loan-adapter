import os
from datetime import timedelta
from urllib.parse import urlparse

SECRET_KEY = os.environ.get("JWT_SIGNING_KEY", "local-demo-only-not-for-deployment")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "api.storage",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
db = urlparse(
    os.environ.get(
        "DATABASE_URL",
        os.environ.get(
            "DATABASE_URL_DJANGO",
            "postgresql://app_django:local-demo-role-password@postgres/adapter",
        ),
    )
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db.path.lstrip("/"),
        "USER": db.username,
        "PASSWORD": db.password,
        "HOST": db.hostname,
        "PORT": db.port or 5432,
    }
}

ROOT_URLCONF = "api.config.urls"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "api", "testserver"]
MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware"]
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "api.views.problem_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Loan Adapter",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
}
