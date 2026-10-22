from django.conf import settings
from django.db import models


class Membership(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tenant_id = models.CharField(
        max_length=7, choices=[(f"BANK00{i}", f"BANK00{i}") for i in range(1, 4)]
    )
