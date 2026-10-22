from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("storage", "0004_api_permissions")]
    operations = [
        migrations.RunSQL(
            """
            CREATE FUNCTION ops.analyze_partition(target_table text, target_tenant text)
            RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
            BEGIN
              CASE target_table || '_' || target_tenant
                WHEN 'fact_loan_retail_BANK001' THEN ANALYZE dwh.fact_loan_retail_bank001;
                WHEN 'fact_loan_retail_BANK002' THEN ANALYZE dwh.fact_loan_retail_bank002;
                WHEN 'fact_loan_retail_BANK003' THEN ANALYZE dwh.fact_loan_retail_bank003;
                WHEN 'fact_loan_commercial_BANK001' THEN ANALYZE dwh.fact_loan_commercial_bank001;
                WHEN 'fact_loan_commercial_BANK002' THEN ANALYZE dwh.fact_loan_commercial_bank002;
                WHEN 'fact_loan_commercial_BANK003' THEN ANALYZE dwh.fact_loan_commercial_bank003;
                WHEN 'fact_installment_BANK001' THEN ANALYZE dwh.fact_installment_bank001;
                WHEN 'fact_installment_BANK002' THEN ANALYZE dwh.fact_installment_bank002;
                WHEN 'fact_installment_BANK003' THEN ANALYZE dwh.fact_installment_bank003;
                ELSE RAISE EXCEPTION 'Invalid warehouse partition';
              END CASE;
            END $$;
            REVOKE ALL ON FUNCTION ops.analyze_partition(text,text) FROM PUBLIC;
            GRANT EXECUTE ON FUNCTION ops.analyze_partition(text,text) TO app_writer;
            """,
            "DROP FUNCTION ops.analyze_partition(text,text)",
        )
    ]
