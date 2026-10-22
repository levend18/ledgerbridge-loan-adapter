from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("storage", "0003_initial")]
    operations = [
        migrations.RunSQL("""
        GRANT USAGE ON SCHEMA ops TO app_django;
        GRANT SELECT,INSERT ON ops.sync_run TO app_django;
        GRANT UPDATE(status,error) ON ops.sync_run TO app_django;
        CREATE POLICY django_read_run ON ops.sync_run FOR SELECT TO app_django
          USING(tenant_id=current_setting('app.tenant_id',true));
        CREATE POLICY django_insert_run ON ops.sync_run FOR INSERT TO app_django
          WITH CHECK(tenant_id=current_setting('app.tenant_id',true) AND status='PENDING');
        CREATE POLICY django_fail_enqueue ON ops.sync_run FOR UPDATE TO app_django
          USING(tenant_id=current_setting('app.tenant_id',true) AND status='PENDING')
          WITH CHECK(tenant_id=current_setting('app.tenant_id',true) AND status='FAILED');
        GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO app_django;
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_django;
    """)
    ]
