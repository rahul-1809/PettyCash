-- Phase 12: Role restructuring (Director & Finance), Finance-Manager hierarchy, and request routing.

UPDATE roles SET name = 'Director' WHERE id = 'role-admin' AND name = 'Admin';

INSERT INTO roles (id, name, created_at)
VALUES ('role-finance', 'Finance', '2026-11-28T00:00:00Z')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS finance_manager_assignments (
    id TEXT PRIMARY KEY,
    finance_user_id TEXT NOT NULL REFERENCES users(id),
    manager_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'APPROVED'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    assigned_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(finance_user_id, manager_id)
);

CREATE INDEX IF NOT EXISTS idx_finance_mgr_assign_fin
    ON finance_manager_assignments(finance_user_id, status);

CREATE INDEX IF NOT EXISTS idx_finance_mgr_assign_mgr
    ON finance_manager_assignments(manager_id, status);

ALTER TABLE petty_cash_requests ADD COLUMN request_type TEXT NOT NULL DEFAULT 'EMPLOYEE_REQUEST';
ALTER TABLE petty_cash_requests ADD COLUMN assigned_finance_id TEXT REFERENCES users(id);
