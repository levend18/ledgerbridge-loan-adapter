from pathlib import Path
import json

from django.db import migrations

SQL = (
    Path(__file__).resolve().parents[3] / "adapter/warehouse/infrastructure/sql/002_operations.sql"
).read_text()


def seed_codes(apps, schema_editor):
    path = Path(__file__).resolve().parents[3] / "adapter/quality/schemas/codes.yaml"
    for domain, variants in json.loads(path.read_text()).items():
        for canonical, values in variants.items():
            for value in set([canonical, *values]):
                schema_editor.execute(
                    "INSERT INTO ref.code_mapping VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (domain, value, canonical),
                )


class Migration(migrations.Migration):
    dependencies = [("storage", "0001_warehouse")]
    operations = [migrations.RunSQL(SQL), migrations.RunPython(seed_codes)]
