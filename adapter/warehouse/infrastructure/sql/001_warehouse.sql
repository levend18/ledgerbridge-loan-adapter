CREATE SCHEMA ref;
CREATE SCHEMA ops;
CREATE SCHEMA dwh;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO app_django;
GRANT USAGE ON SCHEMA ref, ops, dwh TO app_reader, app_writer;

CREATE TABLE ref.tenant (
    tenant_id TEXT PRIMARY KEY CHECK (tenant_id IN ('BANK001','BANK002','BANK003'))
);
INSERT INTO ref.tenant VALUES ('BANK001'), ('BANK002'), ('BANK003');
GRANT SELECT ON ref.tenant TO app_reader, app_writer;

CREATE TABLE dwh.current_snapshot (
    tenant_id TEXT NOT NULL REFERENCES ref.tenant,
    loan_type TEXT NOT NULL CHECK (loan_type IN ('RETAIL','COMMERCIAL')),
    batch_id UUID NOT NULL,
    source_version BIGINT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_counts JSONB NOT NULL,
    PRIMARY KEY (tenant_id, loan_type)
);
ALTER TABLE dwh.current_snapshot ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_snapshot ON dwh.current_snapshot FOR SELECT TO app_reader
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE dwh.fact_loan_retail (
    tenant_id TEXT NOT NULL REFERENCES ref.tenant,
    batch_id UUID NOT NULL,
    source_row_number INTEGER NOT NULL,
    customer_id TEXT NOT NULL,
    customer_type TEXT NOT NULL CHECK (customer_type IN ('INDIVIDUAL','T','V')),
    loan_account_number TEXT NOT NULL,
    loan_status_code TEXT NOT NULL CHECK (loan_status_code IN ('ACTIVE','CLOSED')),
    days_past_due INTEGER NOT NULL,
    final_maturity_date DATE NOT NULL,
    total_installment_count INTEGER,
    outstanding_installment_count INTEGER,
    paid_installment_count INTEGER,
    first_payment_date DATE,
    original_loan_amount NUMERIC(18,2) NOT NULL,
    outstanding_principal_balance NUMERIC(18,2) NOT NULL,
    nominal_interest_rate NUMERIC(12,8),
    total_interest_amount NUMERIC(18,2),
    kkdf_rate NUMERIC(12,8),
    kkdf_amount NUMERIC(18,2),
    bsmv_rate NUMERIC(12,8),
    bsmv_amount NUMERIC(18,2),
    grace_period_months INTEGER,
    installment_frequency INTEGER,
    loan_start_date DATE NOT NULL,
    loan_closing_date DATE,
    insurance_included BOOLEAN,
    customer_district_code TEXT,
    customer_province_code TEXT,
    internal_rating TEXT,
    external_rating TEXT
) PARTITION BY LIST (tenant_id);

CREATE TABLE dwh.fact_loan_commercial (
    tenant_id TEXT NOT NULL REFERENCES ref.tenant,
    batch_id UUID NOT NULL,
    source_row_number INTEGER NOT NULL,
    loan_account_number TEXT NOT NULL,
    customer_type TEXT NOT NULL CHECK (customer_type IN ('INDIVIDUAL','T','V')),
    customer_id TEXT NOT NULL,
    loan_product_type TEXT,
    loan_status_code TEXT NOT NULL CHECK (loan_status_code IN ('ACTIVE','CLOSED')),
    loan_status_flag TEXT,
    days_past_due INTEGER NOT NULL,
    final_maturity_date DATE NOT NULL,
    total_installment_count INTEGER,
    outstanding_installment_count INTEGER,
    paid_installment_count INTEGER,
    first_payment_date DATE,
    original_loan_amount NUMERIC(18,2) NOT NULL,
    outstanding_principal_balance NUMERIC(18,2) NOT NULL,
    nominal_interest_rate NUMERIC(12,8),
    total_interest_amount NUMERIC(18,2),
    kkdf_rate NUMERIC(12,8),
    kkdf_amount NUMERIC(18,2),
    bsmv_rate NUMERIC(12,8),
    bsmv_amount NUMERIC(18,2),
    grace_period_months INTEGER,
    installment_frequency INTEGER,
    loan_start_date DATE NOT NULL,
    loan_closing_date DATE,
    customer_region_code TEXT,
    sector_code TEXT,
    internal_credit_rating TEXT,
    default_probability NUMERIC(10,8),
    risk_class TEXT,
    customer_segment TEXT,
    internal_rating TEXT,
    external_rating TEXT
) PARTITION BY LIST (tenant_id);

CREATE TABLE dwh.fact_installment (
    tenant_id TEXT NOT NULL REFERENCES ref.tenant,
    batch_id UUID NOT NULL,
    source_row_number INTEGER NOT NULL,
    loan_type TEXT NOT NULL CHECK (loan_type IN ('RETAIL','COMMERCIAL')),
    loan_account_number TEXT NOT NULL,
    installment_number INTEGER NOT NULL,
    actual_payment_date DATE,
    scheduled_payment_date DATE,
    installment_amount NUMERIC(18,2),
    principal_component NUMERIC(18,2),
    interest_component NUMERIC(18,2),
    kkdf_component NUMERIC(18,2),
    bsmv_component NUMERIC(18,2),
    installment_status TEXT CHECK (installment_status IN ('OPEN','CLOSED')),
    remaining_principal NUMERIC(18,2),
    remaining_interest NUMERIC(18,2),
    remaining_kkdf NUMERIC(18,2),
    remaining_bsmv NUMERIC(18,2)
) PARTITION BY LIST (tenant_id);

CREATE TABLE dwh.fact_loan_retail_bank001 PARTITION OF dwh.fact_loan_retail FOR VALUES IN ('BANK001');
CREATE TABLE dwh.fact_loan_retail_bank002 PARTITION OF dwh.fact_loan_retail FOR VALUES IN ('BANK002');
CREATE TABLE dwh.fact_loan_retail_bank003 PARTITION OF dwh.fact_loan_retail FOR VALUES IN ('BANK003');
CREATE TABLE dwh.fact_loan_commercial_bank001 PARTITION OF dwh.fact_loan_commercial FOR VALUES IN ('BANK001');
CREATE TABLE dwh.fact_loan_commercial_bank002 PARTITION OF dwh.fact_loan_commercial FOR VALUES IN ('BANK002');
CREATE TABLE dwh.fact_loan_commercial_bank003 PARTITION OF dwh.fact_loan_commercial FOR VALUES IN ('BANK003');
CREATE TABLE dwh.fact_installment_bank001 PARTITION OF dwh.fact_installment FOR VALUES IN ('BANK001');
CREATE TABLE dwh.fact_installment_bank002 PARTITION OF dwh.fact_installment FOR VALUES IN ('BANK002');
CREATE TABLE dwh.fact_installment_bank003 PARTITION OF dwh.fact_installment FOR VALUES IN ('BANK003');

CREATE INDEX ON dwh.fact_loan_retail (tenant_id, batch_id, loan_account_number);
CREATE INDEX ON dwh.fact_loan_commercial (tenant_id, batch_id, loan_account_number);
CREATE INDEX ON dwh.fact_installment (tenant_id, batch_id, loan_account_number, installment_number);

ALTER TABLE dwh.fact_loan_retail ENABLE ROW LEVEL SECURITY;
ALTER TABLE dwh.fact_loan_commercial ENABLE ROW LEVEL SECURITY;
ALTER TABLE dwh.fact_installment ENABLE ROW LEVEL SECURITY;

CREATE POLICY current_tenant_snapshot ON dwh.fact_loan_retail FOR SELECT TO app_reader
USING (tenant_id = current_setting('app.tenant_id', true)
    AND batch_id IN (SELECT batch_id FROM dwh.current_snapshot
                    WHERE tenant_id = current_setting('app.tenant_id', true) AND loan_type = 'RETAIL'));
CREATE POLICY current_tenant_snapshot ON dwh.fact_loan_commercial FOR SELECT TO app_reader
USING (tenant_id = current_setting('app.tenant_id', true)
    AND batch_id IN (SELECT batch_id FROM dwh.current_snapshot
                    WHERE tenant_id = current_setting('app.tenant_id', true) AND loan_type = 'COMMERCIAL'));
CREATE POLICY current_tenant_snapshot ON dwh.fact_installment FOR SELECT TO app_reader
USING (tenant_id = current_setting('app.tenant_id', true)
    AND (loan_type, batch_id) IN (SELECT loan_type, batch_id FROM dwh.current_snapshot
                               WHERE tenant_id = current_setting('app.tenant_id', true)));

GRANT SELECT ON dwh.current_snapshot, dwh.fact_loan_retail,
    dwh.fact_loan_commercial, dwh.fact_installment TO app_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.current_snapshot, dwh.fact_loan_retail,
    dwh.fact_loan_commercial, dwh.fact_installment TO app_writer;

CREATE VIEW dwh.v_loan_common WITH (security_invoker = true) AS
    SELECT tenant_id, batch_id, 'RETAIL'::TEXT AS loan_type, loan_account_number,
           original_loan_amount, outstanding_principal_balance FROM dwh.fact_loan_retail
    UNION ALL
    SELECT tenant_id, batch_id, 'COMMERCIAL'::TEXT, loan_account_number,
           original_loan_amount, outstanding_principal_balance FROM dwh.fact_loan_commercial;
GRANT SELECT ON dwh.v_loan_common TO app_reader, app_writer;
