import os
from uuid import UUID, uuid4

import psycopg
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from adapter.shared import DatasetKind, LoanType, Severity, TenantId, Unit
from adapter.warehouse.infrastructure.queries import ReaderQueries
from api.storage.models import Membership
from workers.celery_app import app


def problem_handler(exc, context):
    if isinstance(exc, (ValueError, TypeError)):
        exc = ValidationError(str(exc))
    if isinstance(exc, LookupError):
        from rest_framework.exceptions import NotFound

        exc = NotFound(str(exc))
    response = exception_handler(exc, context)
    if response is not None:
        detail = (
            response.data.get("detail", response.data)
            if isinstance(response.data, dict)
            else response.data
        )
        response.data = {
            "type": f"urn:ledgerbridge:{getattr(detail, 'code', 'request-error')}",
            "title": str(detail),
            "status": response.status_code,
            "detail": str(detail),
        }
        response.content_type = "application/problem+json"
    return response


class TokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        try:
            membership = Membership.objects.get(user=user)
        except Membership.DoesNotExist as exc:
            raise AuthenticationFailed("Account has no tenant") from exc
        token["tenant_id"], token["role"], token["sub"] = (
            membership.tenant_id,
            "bank_user",
            str(user.pk),
        )
        return token


class TokenView(TokenObtainPairView):
    serializer_class = TokenSerializer


def queries():
    return ReaderQueries(
        os.environ.get(
            "DATABASE_URL_READER",
            "postgresql://app_reader:local-demo-role-password@postgres/adapter",
        )
    )


def identity(request):
    try:
        tenant = TenantId(request.auth["tenant_id"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationFailed("Invalid tenant claim") from exc
    supplied = (
        request.data.get("tenant_id")
        if request.method == "POST"
        else request.query_params.get("tenant_id")
    )
    if supplied is not None and supplied != tenant:
        raise PermissionDenied("tenant-mismatch", code="tenant-mismatch")
    return tenant


def unit(request):
    tenant = identity(request)
    data = request.data if request.method == "POST" else request.query_params
    return Unit(tenant, LoanType(data.get("loan_type", "RETAIL")))


def page_limit(request):
    limit = int(request.query_params.get("limit", 100))
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    return limit


class Health(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"status": "ok"})


class SyncBody(serializers.Serializer):
    tenant_id = serializers.ChoiceField(choices=list(TenantId), required=False)
    loan_type = serializers.ChoiceField(choices=list(LoanType))
    force = serializers.BooleanField(default=False)


class Sync(APIView):
    @extend_schema(request=SyncBody, responses={202: OpenApiTypes.OBJECT})
    def post(self, request):
        target = unit(request)
        body = SyncBody(data=request.data)
        body.is_valid(raise_exception=True)
        run_id = str(uuid4())
        dsn = os.environ.get(
            "DATABASE_URL_DJANGO",
            "postgresql://app_django:local-demo-role-password@postgres/adapter",
        )
        try:
            with psycopg.connect(dsn) as conn:
                conn.execute("SELECT set_config('app.tenant_id',%s,true)", (target.tenant,))
                conn.execute(
                    "INSERT INTO ops.sync_run(id,tenant_id,loan_type,trigger,force,status) VALUES(%s,%s,%s,'MANUAL',%s,'PENDING')",
                    (run_id, target.tenant, target.loan_type, body.validated_data["force"]),
                )
        except psycopg.errors.UniqueViolation:
            with psycopg.connect(dsn) as conn:
                conn.execute("SELECT set_config('app.tenant_id',%s,true)", (target.tenant,))
                existing = conn.execute(
                    "SELECT id FROM ops.sync_run WHERE loan_type=%s AND status IN ('PENDING','FETCHING','PROCESSING','VALIDATING','PUBLISHING')",
                    (target.loan_type,),
                ).fetchone()
            return Response(
                {
                    "type": "urn:ledgerbridge:unit-busy",
                    "title": "Unit busy",
                    "status": 409,
                    "sync_run_id": str(existing[0]) if existing else None,
                },
                status=409,
                content_type="application/problem+json",
            )
        try:
            app.send_task("workers.tasks.sync", args=[run_id])
        except Exception as exc:
            with psycopg.connect(dsn) as conn:
                conn.execute("SELECT set_config('app.tenant_id',%s,true)", (target.tenant,))
                conn.execute(
                    "UPDATE ops.sync_run SET status='FAILED',error='Queue unavailable' WHERE id=%s",
                    (run_id,),
                )
            error = APIException("Queue unavailable; retry later")
            error.status_code = 503
            raise error from exc
        return Response({"sync_run_id": run_id, "status": "PENDING"}, status=202)


class RunDetail(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, run_id):
        return Response(queries().runs(identity(request), run_id=str(run_id)))


class Runs(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        tenant = identity(request)
        kind = request.query_params.get("loan_type")
        if kind:
            kind = LoanType(kind)
        result = queries().runs(tenant, kind)
        from adapter.ingestion.infrastructure.bank import HttpBankGateway
        from adapter.shared import BankUnavailable

        bank = HttpBankGateway(
            os.environ.get("BANK_BASE_URL", "http://bank:8001"),
            {tenant: os.environ.get(f"BANK_KEY_{tenant}", f"demo-{tenant.lower()}-key")},
        )
        versions = {}
        for loan in [kind] if kind else list(LoanType):
            try:
                versions[loan] = bank.get_meta(Unit(tenant, LoanType(loan))).version
            except BankUnavailable:
                versions[loan] = None
        result["source_versions"] = versions
        return Response(result)


class Data(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            queries().data(
                unit(request),
                DatasetKind(request.query_params.get("dataset", "credit")),
                request.query_params.get("cursor", ""),
                page_limit(request),
            )
        )


class Issues(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        tenant = identity(request)
        run_id = str(UUID(request.query_params.get("sync_run_id", "")))
        severity = request.query_params.get("severity")
        if severity:
            severity = Severity(severity)
        cursor = int(request.query_params.get("cursor", 0))
        return Response(queries().issues(tenant, run_id, severity, cursor, page_limit(request)))


class Profiling(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from adapter.profiling.infrastructure.queries import ProfileQueries

        return Response(
            ProfileQueries(
                os.environ.get(
                    "DATABASE_URL_READER",
                    "postgresql://app_reader:local-demo-role-password@postgres/adapter",
                )
            ).current(unit(request))
        )
