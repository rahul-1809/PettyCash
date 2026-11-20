-- Categories are request-level input, not Admin-managed master data.
-- Keep category_id for schema compatibility while storing the entered value here.
ALTER TABLE petty_cash_requests ADD COLUMN category_name TEXT;
