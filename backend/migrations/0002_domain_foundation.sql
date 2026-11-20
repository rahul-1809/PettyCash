-- Phase 1 normalized domain foundation.

CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    role_id TEXT NOT NULL REFERENCES roles(id),
    password_hash TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS onboarding_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manager_employee_assignments (
    id TEXT PRIMARY KEY,
    manager_id TEXT NOT NULL REFERENCES users(id),
    employee_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    requested_by TEXT NOT NULL REFERENCES users(id),
    reviewed_by TEXT REFERENCES users(id),
    review_reason TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    UNIQUE (manager_id, employee_id)
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledgers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    currency TEXT NOT NULL DEFAULT 'INR',
    opening_balance NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (opening_balance = round(opening_balance, 2)),
    minimum_balance NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (minimum_balance >= 0 AND minimum_balance = round(minimum_balance, 2)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_account_balances (
    cash_account_id TEXT PRIMARY KEY REFERENCES cash_accounts(id),
    current_balance NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (current_balance = round(current_balance, 2)),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS petty_cash_requests (
    id TEXT PRIMARY KEY,
    requester_id TEXT NOT NULL REFERENCES users(id),
    approving_manager_id TEXT NOT NULL REFERENCES users(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    ledger_id TEXT NOT NULL REFERENCES ledgers(id),
    category_id TEXT NOT NULL REFERENCES categories(id),
    cash_account_id TEXT REFERENCES cash_accounts(id),
    request_date TEXT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL
        CHECK (amount > 0 AND amount = round(amount, 2)),
    purpose TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN (
            'DRAFT',
            'SUBMITTED',
            'APPROVED',
            'SUPPORTING_UPLOADED',
            'POSTED',
            'REJECTED'
        )),
    change_reason TEXT,
    rejection_reason TEXT,
    submitted_at TEXT,
    approved_at TEXT,
    posted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (requester_id <> approving_manager_id)
);

CREATE TABLE IF NOT EXISTS request_status_history (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES petty_cash_requests(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_by TEXT NOT NULL REFERENCES users(id),
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supporting_files (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES petty_cash_requests(id),
    storage_key TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    checksum_sha256 TEXT NOT NULL,
    uploaded_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_receipts (
    id TEXT PRIMARY KEY,
    cash_account_id TEXT NOT NULL REFERENCES cash_accounts(id),
    amount NUMERIC(18, 2) NOT NULL
        CHECK (amount > 0 AND amount = round(amount, 2)),
    receipt_date TEXT NOT NULL,
    description TEXT NOT NULL,
    receipt_reference TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id TEXT PRIMARY KEY,
    cash_account_id TEXT NOT NULL REFERENCES cash_accounts(id),
    request_id TEXT UNIQUE REFERENCES petty_cash_requests(id),
    company_receipt_id TEXT UNIQUE REFERENCES company_receipts(id),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('RECEIPT', 'PAYMENT')),
    effective_date TEXT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL
        CHECK (amount > 0 AND amount = round(amount, 2)),
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (
        (entry_type = 'PAYMENT' AND request_id IS NOT NULL AND company_receipt_id IS NULL)
        OR
        (entry_type = 'RECEIPT' AND company_receipt_id IS NOT NULL AND request_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    read_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    in_app_enabled INTEGER NOT NULL DEFAULT 1 CHECK (in_app_enabled IN (0, 1)),
    email_enabled INTEGER NOT NULL DEFAULT 1 CHECK (email_enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    before_json TEXT,
    after_json TEXT,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_periods (
    id TEXT PRIMARY KEY,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'CLOSED')),
    closed_by TEXT REFERENCES users(id),
    closed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (period_start, period_end),
    CHECK (period_start <= period_end)
);

CREATE TABLE IF NOT EXISTS legacy_ledger_sessions (
    id TEXT PRIMARY KEY,
    source_session_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    source_filename TEXT,
    imported_at TEXT NOT NULL,
    imported_by TEXT REFERENCES users(id),
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_role_id
    ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_assignments_manager_status
    ON manager_employee_assignments(manager_id, status);
CREATE INDEX IF NOT EXISTS idx_assignments_employee_status
    ON manager_employee_assignments(employee_id, status);
CREATE INDEX IF NOT EXISTS idx_requests_status_manager
    ON petty_cash_requests(status, approving_manager_id);
CREATE INDEX IF NOT EXISTS idx_requests_requester_date
    ON petty_cash_requests(requester_id, request_date);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_account_date
    ON ledger_entries(cash_account_id, effective_date);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read
    ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_entity
    ON audit_events(entity_type, entity_id);
