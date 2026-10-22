CREATE TABLE ops.sync_run (
    id UUID PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES ref.tenant,
    loan_type TEXT NOT NULL, trigger TEXT NOT NULL, force BOOLEAN NOT NULL,
    status TEXT NOT NULL, source_version BIGINT NOT NULL DEFAULT 0,
    batch_id UUID, counts JSONB NOT NULL DEFAULT '{}',
    issues_summary JSONB NOT NULL DEFAULT '{}', unit_decisions JSONB NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '', duration_ms BIGINT NOT NULL DEFAULT 0,
    peak_rss_kb BIGINT NOT NULL DEFAULT 0, gc_duration_ms BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON ops.sync_run(tenant_id,created_at DESC);
CREATE UNIQUE INDEX one_active_run ON ops.sync_run(tenant_id,loan_type)
 WHERE status IN ('PENDING','FETCHING','PROCESSING','VALIDATING','PUBLISHING');
CREATE TABLE ops.validation_issue (
    id BIGSERIAL PRIMARY KEY, run_id UUID NOT NULL REFERENCES ops.sync_run,
    tenant_id TEXT NOT NULL, dataset TEXT NOT NULL, row_number INTEGER NOT NULL,
    key TEXT NOT NULL, column_name TEXT NOT NULL, rule_id TEXT NOT NULL,
    severity TEXT NOT NULL, raw_value TEXT NOT NULL, normalized_value TEXT NOT NULL, message TEXT NOT NULL
);
CREATE INDEX ON ops.validation_issue(tenant_id,run_id,id);
CREATE TABLE ops.validation_issue_summary (
    run_id UUID NOT NULL REFERENCES ops.sync_run, tenant_id TEXT NOT NULL,
    severity_rule TEXT NOT NULL, count BIGINT NOT NULL, PRIMARY KEY(run_id,severity_rule)
);
CREATE TABLE ops.column_profile (
    tenant_id TEXT NOT NULL, loan_type TEXT NOT NULL, batch_id UUID NOT NULL,
    dataset TEXT NOT NULL, column_name TEXT NOT NULL, stats JSONB NOT NULL,
    PRIMARY KEY(tenant_id,loan_type,batch_id,dataset,column_name)
);
CREATE TABLE ref.code_mapping (
    domain TEXT NOT NULL, raw_key TEXT NOT NULL, canonical TEXT NOT NULL,
    PRIMARY KEY(domain,raw_key)
);
ALTER TABLE ops.sync_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.validation_issue ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.validation_issue_summary ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.column_profile ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_read ON ops.sync_run FOR SELECT TO app_reader USING (tenant_id=current_setting('app.tenant_id',true));
CREATE POLICY tenant_read ON ops.validation_issue FOR SELECT TO app_reader USING (tenant_id=current_setting('app.tenant_id',true));
CREATE POLICY tenant_read ON ops.validation_issue_summary FOR SELECT TO app_reader USING (tenant_id=current_setting('app.tenant_id',true));
CREATE POLICY current_profile ON ops.column_profile FOR SELECT TO app_reader USING (
 tenant_id=current_setting('app.tenant_id',true) AND (loan_type,batch_id) IN
 (SELECT loan_type,batch_id FROM dwh.current_snapshot WHERE tenant_id=current_setting('app.tenant_id',true)));
GRANT SELECT ON ops.sync_run,ops.validation_issue,ops.validation_issue_summary,ops.column_profile,ref.code_mapping TO app_reader;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA ops TO app_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA ops TO app_writer;
GRANT SELECT ON ref.code_mapping TO app_writer;
GRANT SELECT,INSERT,UPDATE,DELETE ON ref.code_mapping TO app_django;
GRANT USAGE ON SCHEMA ref TO app_django;
