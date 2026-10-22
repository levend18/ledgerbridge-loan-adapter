import os
from urllib.parse import urlparse

SECRET_KEY = os.environ.get("JWT_SIGNING_KEY", "local-demo-only-not-for-deployment")
INSTALLED_APPS = ["api.storage"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
db = urlparse(os.environ["DATABASE_URL"])
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
