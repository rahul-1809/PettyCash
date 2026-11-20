-- Phase 7: Financial controls, adjustments, and legacy ledger isolation.

ALTER TABLE petty_cash_requests ADD COLUMN is_reversed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE petty_cash_requests ADD COLUMN reversed_at TEXT;
ALTER TABLE petty_cash_requests ADD COLUMN reversed_by TEXT;
ALTER TABLE petty_cash_requests ADD COLUMN reversal_reason TEXT;

ALTER TABLE company_receipts ADD COLUMN is_reversed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE company_receipts ADD COLUMN reversed_at TEXT;
ALTER TABLE company_receipts ADD COLUMN reversed_by TEXT;
ALTER TABLE company_receipts ADD COLUMN reversal_reason TEXT;

ALTER TABLE ledger_entries ADD COLUMN is_reversed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ledger_entries ADD COLUMN reversed_at TEXT;

CREATE TABLE IF NOT EXISTS ledger_adjustments (
    id TEXT PRIMARY KEY,
    cash_account_id TEXT NOT NULL REFERENCES cash_accounts(id),
    adjustment_type TEXT NOT NULL CHECK (adjustment_type IN ('REVERSAL', 'ADJUSTMENT')),
    related_ledger_entry_id TEXT REFERENCES ledger_entries(id),
    related_request_id TEXT REFERENCES petty_cash_requests(id),
    related_company_receipt_id TEXT REFERENCES company_receipts(id),
    direction TEXT NOT NULL CHECK (direction IN ('INFLOW', 'OUTFLOW')),
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0 AND amount = round(amount, 2)),
    effective_date TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_adjustments_account_date
    ON ledger_adjustments(cash_account_id, effective_date);
CREATE INDEX IF NOT EXISTS idx_audit_events_action_created
    ON audit_events(action, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor
    ON audit_events(actor_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_financial_periods_dates
    ON financial_periods(period_start, period_end, status);
