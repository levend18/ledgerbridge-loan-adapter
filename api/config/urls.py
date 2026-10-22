from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from api import views

urlpatterns = [
    path("api/health", views.Health.as_view()),
    path("api/auth/token", views.TokenView.as_view()),
    path("api/auth/token/refresh", TokenRefreshView.as_view()),
    path("api/sync", views.Sync.as_view()),
    path("api/sync/<uuid:run_id>", views.RunDetail.as_view()),
    path("api/runs", views.Runs.as_view()),
    path("api/data", views.Data.as_view()),
    path("api/profiling", views.Profiling.as_view()),
    path("api/validation-issues", views.Issues.as_view()),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
]
