# Petty Cash Management System — Production Readiness & Security Audit

| Attribute | Details |
| :--- | :--- |
| **Assessment Date** | 24 November 2026 |
| **Deployment Verdict** | **NO-GO (conditional)** |
| **Production-Readiness Score** | **62 / 100** |
| **Classification** | Confidential — Internal Engineering |
| **Targets** | **Local (tested):** `http://127.0.0.1` / `http://localhost:8000/api`<br>**Production (reference):** `https://pettycash.ajassociate.online` |
| **Stack** | FastAPI (Python) · React + Vite SPA · SQLite (local/default) / PostgreSQL-Supabase (production) · Docker on Render |

---

## 1. Executive Summary

The **Petty Cash Management System** is a well-architected financial application whose core ledger engine is genuinely strong — concurrency-safe balance updates, exact decimal money handling in the service layer, a constraint-rich schema, and an immutable audit trail. Live adversarial testing confirmed its headline financial safety property holds: concurrent spending cannot double-spend or drive the balance negative.

However, the assessment found one **Critical** and three **High** severity defects that make the system not production-ready as-is. Most serious is a complete authentication gap on the entire Spreadsheet Sessions API: any unauthenticated caller can list, read, overwrite, and delete stored petty-cash data. Combined with bearer tokens accepted in URLs, sessions that survive password resets, and an admin endpoint that silently breaks ledger reconciliation, the verdict is **NO-GO** until the Phase 1 (P0) items are remediated.

* **Go/No-Go Verdict:** **NO-GO (conditional)**. Remediate the 1 Critical + 3 High (P0) findings and the financial-integrity P1 items, then re-test. The architecture is sound enough that a focused remediation sprint can realistically reach a GO.

### Risk Breakdown by Severity

| Critical | High | Medium | Low |
| :---: | :---: | :---: | :---: |
| **1** | **3** | **4** | **8** |

### Score Rationale
A score of **62/100** weights the blast radius of the Critical unauthenticated-data-destruction hole and the High auth/session/ledger findings against an unusually solid financial core and passing RBAC, IDOR, mass-assignment, idempotency, and concurrency-safety controls. Closing P0 would move the score into the high-70s; closing P0 + P1 into the high-80s.

### Scope & Environment Note
All dynamic, adversarial, concurrency, and database tests were executed locally against a freshly built instance of this exact codebase on a throwaway SQLite database (the real `sessions.db` was never modified by the tests; its integrity was verified afterward). Standing up the runtime required working around a locked-down corporate environment (`winget` blocked by group policy; the `pip` bootstrap domain blocked by the Zscaler proxy) — Python 3.12 was ultimately provisioned and the backend booted successfully. Adversarial/load testing was deliberately not run against live production. Read-only production probes were attempted, but the corporate network returned 403/timeout, so production-specific TLS/header results are inconclusive and not claimed here. Frontend UI findings are from source review (Node toolchain unavailable on this host).

The project's committed regression suite (11 modules, `tests/test_phase0-11`, 77 tests covering auth, RBAC, the request lifecycle, posting, financial controls, reversals, reporting, and operations) was executed in the rebuilt environment. All 77 tests' assertions passed (0 assertion failures); 66 are reported by the runner as 'errors' solely because of a Windows-only temp-directory cleanup lock (`WinError 32`) in `tearDown` — the app opens SQLite connections via `with get_connection()` but never closes them, so the test's `TemporaryDirectory` cannot be deleted while handles remain open. This is a Windows/SQLite resource-handling artifact, not a logic failure, and corroborates a minor connection-leak observation for the SQLite path.

---

## 2. Architecture & Feature Inventory

**Roles:** Admin, Manager, Employee, plus Unauthenticated.

| Domain | Key Endpoints | Notes |
| :--- | :--- | :--- |
| **Authentication & Sessions** | `/api/auth/bootstrap(-status)`, `/login`, `/logout`, `/me`, `/set-password`, `/users/{id}/token` | `bcrypt`, SHA-256 token hashes, 30-day rolling sessions |
| **Users & Assignments** | `/api/users`, `/api/assignments` (`+review`) | Admin provisioning; manager approves employee links |
| **Master Data** | `/api/projects`, `/api/ledgers`, `/api/project-categories` | Admin-managed; soft active/inactive |
| **Cash & Receipts** | `/api/cash-balance`, `/api/company-receipts`, `/api/cash-adjustments` | Version-locked balance; idempotent receipts |
| **Request Lifecycle** | `/api/requests` (`+submit/approve/reject/request-changes/supporting-files/submit-for-posting/post/return/reverse`) | `DRAFT` $\rightarrow$ `SUBMITTED` $\rightarrow$ `APPROVED` $\rightarrow$ `SUPPORTING_UPLOADED` $\rightarrow$ `POSTED`; `REJECTED`; `REVERSED` |
| **Financial Controls** | `/api/financial-periods` (`+close/reopen`), request & receipt reversals | Period locks; audited two-way reversals |
| **Audit & Reports** | `/api/audit-events`, `/api/reports/monthly` (`+excel/zip`) | Append-only trail; 12-column exports |
| **Operations** | `/api/operations/metrics\|errors\|backups\|rollback\|alerts`, `/health/live\|ready` | Admin-only; in-memory metrics/errors |
| **Spreadsheet Sessions** | `/api/sessions*`, `/api/upload`, `/api/recalculate`, `/api/export*` | **Unauthenticated** — see F-01 |

---

## 3. Test Coverage Matrix

* **12 controls verified working (PASS)**
* **10 weaknesses confirmed (FAIL)**
* **2 observations (INFO)**
* *Across 24 executed dynamic tests.*

| ID | Test Description | Layer | Severity | Observed Result | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AUTH-01** | Unauthenticated access to protected endpoint rejected | Security | Info | `401` | Control OK |
| **AUTH-02** | Bearer token accepted via URL query string (`?token=`) | Security | High | `200` (accepted) | Weakness |
| **AUTH-03** | Unauthenticated `CREATE` on `/api/sessions` (financial data) | Security | Critical | `200` created `id=e5f07138-6647-426d-b8e0-12994568eb15` | Weakness |
| **AUTH-04** | Unauthenticated `LIST` of all spreadsheet sessions | Security | Critical | `200`, 1 sessions | Weakness |
| **AUTH-05** | Unauthenticated `DELETE` of spreadsheet session (destructive) | Security | Critical | `200 {"deleted":true}` | Weakness |
| **AUTH-06** | Employee blocked from Admin endpoint `GET /api/users` | Security | Info | `403` | Control OK |
| **AUTH-07** | Manager blocked from Admin-only company receipt | Security | Info | `403` | Control OK |
| **IDOR-01** | Employee B cannot read Employee A's request by ID | Security | Info | `403` | Control OK |
| **MASS-01** | Extra fields (`status`/`requester_id`) ignored on create | Backend | Info | `status=DRAFT`, `requester=Tq_0i-OARu1-Nfk_gDbZbaS1` | Control OK |
| **MASS-02** | `PATCH` draft rejects non-whitelisted field `'status'` | Backend | Info | `200` | Weakness |
| **VAL-01** | Negative amount rejected server-side | Backend | Info | `400` | Control OK |
| **VAL-02** | Zero amount rejected | Backend | Info | `400` | Control OK |
| **VAL-03** | Sub-cent amount ($0.000001$) rejected (quantizes to 0) | Backend | Info | `400` | Control OK |
| **VAL-04** | Fractional-cent amount $10.999$ silently rounded | Backend | Low | `stored=11` | Observation |
| **VAL-05** | Over-wide amount vs `NUMERIC(18,2)` not enforced on SQLite | Database | Medium | `status=200` `stored=123456789012345680` | Weakness |
| **VAL-06** | No max-length bound on free-text `'purpose'` (100k chars) | Backend | Low | patch `status=200` | Weakness |
| **VAL-07** | Stored HTML/script not sanitized server-side (stored verbatim) | Security | Low | stored raw: `alert(1)` | Weakness |
| **ERR-01** | Internal error detail leaked in `/api/recalculate` 500 | Backend | Low | `422: {"detail":[{"type":"float_parsing"...` | Observation |
| **IDEM-01** | Replayed identical company receipt deduplicated | Concurrency | Info | `dup=True`, `delta=250.0` | Control OK |
| **CONC-01** | Concurrent posting: no double-spend / negative balance | Concurrency | Critical | `successes=6`, `final_balance=400.0`, `start=1000.0` | Control OK |
| **CONC-02** | DB-level lock contention under concurrent writes | Concurrency | Medium | lock/500/err responses $= 0 \text{ of } 20$ | Control OK |
| **LEDGER-01**| Ledger reconciles with balance after concurrent posts | Concurrency | High | `balance=400.0`, `ledger-derived=400.0` | Control OK |
| **LEDGER-02**| `PUT /api/cash-balance` overwrites balance without ledger entry | Database | High | balance set to $999999.99$, ledger-derived still $400.0$ | Weakness |
| **SESS-01** | Pre-reset session remains valid after password reset | Security | High | `me` before=`200`, `me` after reset=`200` | Weakness |

---

## 4. Detailed Defect & Vulnerability Log

### F-01 — Entire Spreadsheet Sessions API is Unauthenticated (Broken Access Control / BOLA)
* **Severity:** Critical
* **Stack Layer:** Security / Backend
* **Verification:** AUTH-03, AUTH-04, AUTH-05 (confirmed live)
* **Location:** `backend/main.py:1830-2061` (`api_list_sessions`, `api_get_session`, `api_create_session`, `api_update_session`, `api_rename_session`, `api_delete_session`, `api_export_session_zip`, `upload_excel`, `recalculate`, `export_*`); `frontend/src/api.js:397-406`
* **Reproduction:**
  ```bash
  curl -s http://HOST/api/sessions # returns 200 + full session list
  curl -X DELETE http://HOST/api/sessions/{id} # returns {"deleted":true}
  curl -s http://HOST/api/sessions/{id}?include_raw=true # returns source_excel_base64
  ```
* **Expected:** `401 Unauthorized`; role-restricted access to financial spreadsheet data.
* **Actual:** Unauthenticated `LIST` returned `200` with session data; unauthenticated `CREATE` returned a new ID; unauthenticated `DELETE` returned `{"deleted":true}` and removed the record.
* **Root Cause:** These routes declare no dependency on `current_user` / `require_roles`, unlike every `/api/requests`, `/api/users`, and `/api/cash-*` route. The 'Spreadsheet Sessions' module predates the auth layer and was never retrofitted with it.
* **Remediation:** Add `user: dict = Depends(current_user)` (and appropriate `require_roles`) to every `/api/sessions*`, `/api/upload`, `/api/recalculate`, `/api/export*`, `/api/default-data`, and `/api/project-categories` route, or mount them under an `APIRouter` with a global auth dependency. Add server-side authorization so a user can only read/modify sessions they own.

---

### F-02 — Session Bearer Token Accepted in the URL Query String
* **Severity:** High
* **Stack Layer:** Security
* **Verification:** AUTH-02 (confirmed live: `GET /api/cash-balance?token=...` $\rightarrow$ `200`)
* **Location:** `backend/main.py:566, 583` (`current_user` / `optional_current_user` read `request.query_params['token']` and `['auth_token']`); `frontend/src/api.js:269, 288, 296` build download/report URLs with `?token=`
* **Reproduction:** Execute `GET /api/cash-balance?token=<valid-session-token>` with no `Authorization` header $\rightarrow$ `200 OK`.
* **Expected:** Tokens transmitted only in the `Authorization` header; query-string tokens rejected.
* **Actual:** A 48-byte session token in the URL authenticated successfully.
* **Root Cause:** Download endpoints needed a way to pass auth for `window.open` flows, so query-param tokens were allowed globally for all `GET` endpoints.
* **Remediation:** Remove query-param token support. For file downloads, issue short-lived single-use signed URLs (HMAC + expiry) or stream via `fetch()` with the `Authorization` header and a blob (`api.js` already does this in `downloadFile()`). Treat the long-lived session token as header-only.

---

### F-03 — Existing Sessions are Not Revoked on Password Reset; 60s Auth Cache Delays Revocation
* **Severity:** High
* **Stack Layer:** Security
* **Verification:** SESS-01 (confirmed live: old token still `200` after reset; 2 active sessions remained in DB)
* **Location:** `backend/auth_service.py:206-235` (`set_password_with_token`), `22-33 & 125-181` (`_AUTH_CACHE`, 60s TTL)
* **Reproduction:** Login as user (token $T$). Admin issues a new onboarding token; user sets a new password. Call `GET /api/auth/me` with old token $T$ $\rightarrow$ still `200`. `user_sessions` rows for the user remain `revoked_at IS NULL`.
* **Expected:** Password set/reset revokes all of the user's active sessions (forced re-login).
* **Actual:** `set_password_with_token` updates `users.password_hash` only; it neither deletes/revokes `user_sessions` nor clears the in-memory auth cache, so pre-existing tokens stay valid for their full 30-day TTL.
* **Root Cause:** Password-set path was built for first-time onboarding (no prior sessions) and reused for resets without adding session invalidation.
* **Remediation:** In `set_password_with_token`: `DELETE`/revoke all `user_sessions` for `row['user_id']` and call `clear_auth_cache()`. Reduce `_AUTH_CACHE` TTL and re-check `revoked_at`/`expires_at` even on cache hit.

---

### F-04 — PUT /api/cash-balance Overwrites Ledger Balance with No Ledger Entry or Adjustment
* **Severity:** High
* **Stack Layer:** Database / Backend
* **Verification:** LEDGER-02 (confirmed live: balance set to $999,999.99$ while ledger-derived balance stayed $400.00$)
* **Location:** `backend/main.py:923-961` (`configure_cash_balance`)
* **Reproduction:** With balance $= 400$ backed by ledger entries, execute `PUT /api/cash-balance {"opening_balance": 999999.99}`. `cash_account_balances.current_balance` becomes $999999.99$; however, $ \sum \text{ledger\_entries} + \text{adjustments} $ remains $400$.
* **Expected:** Every change to `current_balance` is represented by an immutable ledger entry / adjustment so that:
  $$ \sum \text{ledger RECEIPT} - \sum \text{ledger PAYMENT} + \text{adjustments} = \text{current\_balance} $$
  at all times.
* **Actual:** The endpoint writes `current_balance` (and `opening_balance`) directly, bumping the version but creating no `ledger_entry`/`ledger_adjustment` and performing no closed-period check. Reconciliation is silently broken and the audit event records only `opening_balance`.
* **Root Cause:** Admin 'set opening balance' convenience endpoint mutates the live running balance instead of posting a reconciling adjustment.
* **Remediation:** Make all balance mutations flow through `create_balance_adjustment` (which writes `ledger_adjustments` and checks closed periods). Restrict direct `current_balance` initialization to the one-time case where no ledger activity exists, and record a full before/after audit event.

---

### F-05 — Monetary Amounts Typed as Float at API Boundary Cause Precision Loss
* **Severity:** Medium
* **Stack Layer:** Backend
* **Verification:** VAL-05 (confirmed live: $123456789012345678.90$ stored as $123456789012345680$)
* **Location:** `backend/main.py` Pydantic models: `PettyCashRequestCreate.amount`, `PettyCashRequestUpdate.amount` (350-351, 442), `CompanyReceiptRequest.amount` (469), `CashAccountRequest.opening_balance` (465), `BalanceAdjustmentRequest.amount` (489)
* **Reproduction:** `POST /api/requests` with `amount=123456789012345678.90` $\rightarrow$ stored amount $123456789012345680$ (fractional and low-order digits corrupted by IEEE-754 floating-point before `Decimal` ever sees the value).
* **Expected:** Exact decimal handling end-to-end for financial amounts.
* **Actual:** JSON numbers are parsed to Python `float` first; service code then does `Decimal(str(float))`, after the corruption has already occurred. Small values survive, but large/high-precision values do not.
* **Root Cause:** Pydantic field type is defined as `float` rather than a decimal or string type.
* **Remediation:** Accept amounts as JSON strings (or `pydantic.condecimal(max_digits=18, decimal_places=2)`) and construct `Decimal` from the raw string. Reject values with $> 2$ decimal places or outside an allowed range instead of silently rounding.

---

### F-06 — No Retry/Serialization on Optimistic-Lock Conflict: Legitimate Concurrent Postings Fail
* **Severity:** Medium
* **Stack Layer:** Concurrency
* **Verification:** CONC-01 / CONC-02 (live: 20 concurrent posts, 10 affordable, only 6 succeeded; 14 received `400 "Balance changed during posting; please retry."`)
* **Location:** `backend/posting_service.py:80-91`; same pattern in `receipt_service.py` and `financial_control_service.py`
* **Reproduction:** Seed balance $= 1000$. Create 20 approved + voucher-attached requests of $100$ each. Fire all `POST .../post` requests simultaneously. 6 succeed, ending with balance $= 400$ (no oversell), but $\sim 4+$ affordable requests are rejected purely due to version Compare-And-Swap (CAS) contention.
* **Expected:** Affordable postings succeed under concurrency via serialization; only genuinely unaffordable ones fail.
* **Actual:** Each post reads a version and executes `UPDATE ... WHERE version=N AND current_balance>=amt`. Losers of the CAS receive a hard `400` with no automatic retry, causing throughput to collapse under load.
* **Root Cause:** Single-attempt optimistic concurrency with no bounded retry loop and no per-account serialization.
* **Remediation:** Wrap the balance CAS in a bounded retry-with-backoff loop (re-read version, re-check funds), serialize per-account postings (`SELECT ... FOR UPDATE` on Postgres; `BEGIN IMMEDIATE + WAL` on SQLite), or move postings to a per-account queue.

---

### F-07 — NUMERIC(18,2) Width Not Enforced on SQLite; Only 2-DP Rounding Checked
* **Severity:** Medium
* **Stack Layer:** Database
* **Verification:** VAL-05 (confirmed live: 18+ digit amount accepted and stored)
* **Location:** `backend/migrations/0002_domain_foundation.sql:106-107, 154-155, 171-172` (`amount NUMERIC(18,2) CHECK (amount>0 AND amount=round(amount,2))`)
* **Reproduction:** Store an amount with more than 16 integer digits; SQLite accepts it because it ignores declared type precision/scale and the `CHECK` constraint validates only sign and 2-decimal-place rounding, not magnitude.
* **Expected:** Amounts bounded to the declared `NUMERIC(18,2)` domain.
* **Actual:** SQLite stores arbitrarily large magnitudes. (Postgres/Supabase in production would reject them, representing an environment-dependent gap).
* **Root Cause:** Reliance on SQL column type width that SQLite does not natively enforce.
* **Remediation:** Add explicit range constraints (e.g., `amount < 10000000000000000`) and validate magnitude in the service layer so behavior is identical across SQLite and Postgres.

---

### F-08 — Wildcard CORS Configured for Production
* **Severity:** Medium
* **Stack Layer:** Security / Config
* **Verification:** Static review (`render.yaml`)
* **Location:** `render.yaml:15-16` (`ALLOWED_ORIGINS: "*"`); consumed in `backend/main.py:325-334`
* **Reproduction:** Production environment sets `ALLOWED_ORIGINS=*`; `CORSMiddleware` subsequently permits requests from any origin.
* **Expected:** Strict allow-list containing only trusted frontend origin(s).
* **Actual:** Any web origin can call the production API from a browser and read responses. Impact is partially mitigated by Bearer token auth, but combined with token storage in `localStorage` (F-11), it widens the XSS/token-theft blast radius.
* **Root Cause:** Permissive default carried into production deployment settings.
* **Remediation:** Set `ALLOWED_ORIGINS` to canonical frontend origin(s) (e.g., `https://pettycash.ajassociate.online`).

---

### F-09 — Internal Error Details Leaked in 500 Responses
* **Severity:** Low
* **Stack Layer:** Backend
* **Verification:** ERR-01 (confirmed live: `POST /api/upload` $\rightarrow$ `500 'Failed to process uploaded file: File is not a zip file'`)
* **Location:** `backend/main.py:1789, 1808, 1825, 1889, 1941, 1981, 2016, 2038, 2061` (`detail=f"...: {str(e)}"`)
* **Reproduction:** `POST /api/upload` a non-xlsx file with a `.xlsx` filename extension $\rightarrow$ returns `500` with raw parser exception text.
* **Expected:** Generic error message + correlation ID; full stack details logged server-side only.
* **Actual:** Raw exception strings are returned to clients on multiple session/export/upload endpoints.
* **Root Cause:** Explicit `str(e)` string interpolation inside per-endpoint exception handlers.
* **Remediation:** Return generic details alongside `X-Correlation-ID`; log exception details server-side only.

---

### F-10 — No Length Bounds or Sanitization on Stored Free-Text Fields
* **Severity:** Low
* **Stack Layer:** Backend / Security
* **Verification:** VAL-06 (100,000-character purpose accepted), VAL-07 (`alert(1)` stored verbatim)
* **Location:** `backend/request_service.py` (`purpose`/`notes`), `receipt_service.py` (`description`); missing `max_length` constraints on Pydantic models
* **Reproduction:** `PATCH` a draft with a 100,000-character purpose field $\rightarrow$ `200 OK`; input stored verbatim.
* **Expected:** Server-enforced length bounds; stored content sanitized or escaped across rendering and export paths.
* **Actual:** Unbounded text is accepted and raw HTML/script strings are persisted. React auto-escaping mitigates web UI stored-XSS, but file exports (Excel/ZIP/PDF) or external consumers remain vulnerable.
* **Root Cause:** Missing input length validation and output-encoding contracts.
* **Remediation:** Apply `max_length` bounds (e.g., `purpose <= 500`, `notes/description <= 2000`) and ensure export generators escape untrusted inputs.

---

### F-11 — Long-Lived Auth Token Stored in `localStorage`
* **Severity:** Low
* **Stack Layer:** Security / Frontend
* **Verification:** Static review (`frontend/src/api.js`)
* **Location:** `frontend/src/api.js:8-18` (`getAuthToken`/`setAuthToken` utilize `localStorage['pettycash_auth_token']`)
* **Reproduction:** Any XSS vulnerability executing within the SPA context can read `localStorage` and extract the active 30-day bearer token.
* **Expected:** Tokens stored in `httpOnly` cookies (with CSRF protection) or short-lived memory tokens with refresh rotation.
* **Actual:** Long-lived (30-day) bearer token resides in JS-accessible storage.
* **Root Cause:** SPA client-side token storage design.
* **Remediation:** Transition to `httpOnly` + `SameSite` cookies with CSRF protection, or shorten access token lifetimes; enforce strict Content Security Policy (CSP).

---

### F-12 — Lenient, Per-Process Rate Limiting; No Login Lockout
* **Severity:** Low
* **Stack Layer:** Security / Reliability
* **Verification:** Static review (`observability.py`)
* **Location:** `backend/observability.py:306-344` (300 req/min; key $= \text{auth:last16}$ or IP; unbounded in-memory dict)
* **Reproduction:** Brute-force attacks against `/api/auth/login` are capped only at 300 req/min/IP with zero per-account lockout. Limiter state is per-process and resets on instance restart.
* **Expected:** Dedicated login throttling with account lockout and exponential backoff, managed via a distributed state store.
* **Actual:** Single global rate limiter without credential-stuffing controls.
* **Root Cause:** In-memory rate limiter lacking multi-node state sharing.
* **Remediation:** Implement per-account and per-IP login rate limits with lockout backoff; move limiter state to a shared store (e.g., Redis); key on full token hashes.

---

### F-13 — Sub-Cent Input Silently Rounded Rather Than Rejected
* **Severity:** Low
* **Stack Layer:** Backend
* **Verification:** VAL-04 ($10.999$ stored as $11.00$), VAL-03 ($0.000001$ rejected as it rounds to $0$)
* **Location:** `backend/request_service.py:26-33` (`_amount` quantize to `0.01`), `receipt_service.py:22-29`
* **Reproduction:** `POST amount=10.999` $\rightarrow$ stored as $11.00$ (`ROUND_HALF_EVEN`), creating an implicit $+0.001$ adjustment.
* **Expected:** Reject inputs exceeding 2 decimal places with validation errors.
* **Actual:** Values are silently quantized, creating potential penny discrepancies between client submission and ledger state.
* **Root Cause:** Quantization applied without enforcing precision preconditions.
* **Remediation:** Explicitly reject input values with precision $> 2$ decimal places.

---

### F-14 — Rolling 30-Day Sessions Auto-Extend Indefinitely
* **Severity:** Low
* **Stack Layer:** Security
* **Verification:** Static review (`auth_service.py`)
* **Location:** `backend/auth_service.py:159-171` (rolling extension to 30 days when remaining time $< 15$ days)
* **Reproduction:** Any API request using a token with $< 15$ days validity automatically resets expiry back to $+30$ days. Actively used tokens never expire.
* **Expected:** Hard upper bound on total session lifetime combined with idle timeouts.
* **Actual:** Indefinitely extending sessions prolong the exposure window for hijacked tokens.
* **Root Cause:** Unbounded rolling session renewal.
* **Remediation:** Enforce maximum absolute session duration (e.g., 12–24 hours) along with refresh-token rotation and idle timeouts.

---

### F-15 — Company Receipt Idempotency Key Derived from Content Fingerprint
* **Severity:** Low
* **Stack Layer:** Backend / Concurrency
* **Verification:** IDEM-01 (deduplication works, flagged for edge-case risk)
* **Location:** `backend/receipt_service.py:119-149` (`idempotency_key = sha256(amount|date|desc|ledger|category|project)`)
* **Reproduction:** Two distinct top-up transactions submitted on the same day with identical amount, date, and description: the second request is dropped as a duplicate.
* **Expected:** Idempotency tracking based on client-generated request identifiers.
* **Actual:** Legitimate duplicate transaction content is suppressed, causing cash-in undercounts.
* **Root Cause:** Content hashing used as sole deduplication key.
* **Remediation:** Require a client-supplied `Idempotency-Key` header/field for deduplication; use content hashing only for warning flags.

---

### F-16 — SQLite Connections Opened via Context Manager Are Never Closed
* **Severity:** Low
* **Stack Layer:** Backend / Reliability
* **Verification:** Corroborated by regression suite: 66/77 tests fail teardown with `WinError 32` (temporary DB file locked by open connection handles).
* **Location:** `backend/database.py:83-93` (`get_connection`); invoked as `with get_connection() as conn:` across endpoints.
* **Reproduction:** Python's `sqlite3` connection context manager handles transaction commit/rollback on exit but does **not** close the underlying connection. File handles accumulate on the SQLite path until garbage collected.
* **Expected:** Connections explicitly closed (`try/finally` or `contextlib.closing`) after execution.
* **Actual:** Unclosed connection handles remain open.
* **Root Cause:** Misunderstanding of `sqlite3` context manager scope.
* **Remediation:** Wrap usage in `contextlib.closing(get_connection())` or implement a custom context manager guaranteeing explicit connection closure.

---

## 5. Concurrency & Financial-Integrity Results

* **Double-spend Prevention:** **PASS**
  * **Test Scenario:** 20 concurrent `POST .../post` requests targeting an initial balance of **INR 1,000** with **20 $\times$ INR 100** total demand.
  * **Outcome:** Exactly 6 requests succeeded, yielding a final balance of **INR 400** (never negative), with 0 oversell. The ledger reconciled perfectly:
    $$ \text{INR } 1,000 \text{ (receipts)} - \text{INR } 600 \text{ (payments)} = \text{INR } 400 \text{ (current balance)} $$

* **Safety Mechanism:** Optimistic Compare-And-Swap (CAS) version locking combined with a `current_balance >= amount` condition in the update SQL.
* **Reliability Trade-off (F-06):** CAS lock contention causes unsuccessful requests to fail with a hard `400` ("Balance changed during posting; please retry") without automated retries. Out of 10 valid, affordable requests, 4 failed purely due to contention.
* **Database Stability:** Zero database deadlocks or lock-timeout errors were recorded ($0 / 20$). Idempotent replaying of company receipts (IDEM-01) correctly deduplicated requests and credited the account balance exactly once.
* **Precision Handling:** Service-layer arithmetic is exact (`Decimal`). Boundary weaknesses exist where `float` parsing distorts large inputs (F-05) before reaching `Decimal`, and where SQLite skips `NUMERIC(18,2)` range checks (F-07).

---

## 6. Strengths & Positive Controls

1. **Concurrency Safety & Double-Spend Defense:** Optimistic version CAS + `current_balance >= amount` state checks prevent double-spends and negative balances under high contention.
2. **Ledger Reconciliation Integrity:** Running balances match ledger state under load ($1,000 - 600 = 400$).
3. **Exact Service Math:** Standardized use of `Decimal` across core calculation pipelines; database schema enforces `CHECK (amount > 0 AND amount = round(amount,2))`.
4. **Auditability:** Immutable, append-only `audit_events` and `request_status_history` tables capture all state transitions with correlation IDs.
5. **Relational Integrity Constraints:** Foreign keys, `UNIQUE` index enforcement, and table-level `CHECK (requester_id <> approving_manager_id)` rules protect core logic.
6. **Role-Based Access Control (RBAC):** Server-side enforcement using `require_roles` successfully blocks unauthorized administrative actions (AUTH-06/07 return `403`). Ownership checks prevent IDOR (IDOR-01 returns `403`).
7. **Mass-Assignment Protections:** Strict Pydantic models drop unmapped fields; draft update endpoints whitelist permissible fields (MASS-01/02 block injected `status` and `requester_id`).
8. **Secure Authentication Primitives:** `bcrypt` password hashing (12-character minimum), SHA-256 hashed storage for session tokens, and fully parameterized SQL queries.
9. **State-Machine Rules:** Strict `VALID_TRANSITIONS` enforce lifecycle flow; financial period locks prevent back-dated posting and reversal operations.

---

## 7. Production-Readiness Engineering Roadmap

```
+-------------------------------------------------------------------+
|                     PHASE 1: P0 BLOCKERS                          |
| Must fix before routing any live production traffic               |
+-------------------------------------------------------------------+
  |-- F-01: Secure /api/sessions* endpoints with Auth & RBAC
  |-- F-02: Eliminate query-string auth tokens (Header-only / Signed URLs)
  |-- F-03: Invalidate sessions & clear auth cache on password reset
  |-- F-04: Enforce balance updates through reconciling ledger entries
  v
+-------------------------------------------------------------------+
|               PHASE 2: P1 HARDENING & INTEGRITY                   |
+-------------------------------------------------------------------+
  |-- F-05/F-07: Enforce string/Decimal monetary inputs & range checks
  |-- F-06: Implement bounded retries / queueing for posting CAS conflicts
  |-- F-08: Restrict CORS origins to trusted frontend domains
  |-- F-12/F-14: Add login rate limiting, lockout, & session caps
  |-- F-09/F-10/F-13/F-15: Sanitize 500 responses, bound text lengths, 
  |                         and implement client idempotency keys
  v
+-------------------------------------------------------------------+
|             PHASE 3: OBSERVABILITY, SCALE & COMPLIANCE            |
+-------------------------------------------------------------------+
  |-- Externalize telemetry (Prometheus/OTel, Sentry)
  |-- Add automated CI security regression test steps
  |-- Implement tamper-evident hash-chained audit trails
  |-- Conduct DB pool tuning & background job queue implementation
```

---

## 8. Methodology & Limitations

* **Approach:** Combined white-box code and schema review across the FastAPI backend and React frontend with scripted dynamic HTTP security testing (via `httpx`).
* **Execution Environment:** Executed locally against a dedicated test backend and isolated SQLite database. Verified authentication, access controls, mass assignment, input validation, exception handling, idempotency, and 20-thread concurrent request safety.
* **Excluded Operations:** Direct load or penetration testing against the live production environment (`https://pettycash.ajassociate.online`) was omitted to prevent operational impact. Production TLS and header probes were restricted by corporate proxy constraints. Node toolchain limitations required frontend evaluation via code review.
* **Dependency Note:** Local test execution resolved current major library versions (`FastAPI 0.165`, `Pydantic 2.14`, `pandas 3.1`). Production deployments should verify compatibility against exact pinned requirements.

---
*Petty Cash Management System — Production Readiness & Security Audit · 24 November 2026 · Confidential*