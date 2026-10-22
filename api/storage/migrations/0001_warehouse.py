from pathlib import Path

from django.db import migrations

SQL = (
    Path(__file__).resolve().parents[3] / "adapter/warehouse/infrastructure/sql/001_warehouse.sql"
).read_text()


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.RunSQL(SQL)]
