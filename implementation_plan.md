# PettyCash Implementation Plan

This plan aligns the current prototype, the audit findings in [Petty Cash Report.pdf](./Petty%20Cash%20Report.pdf), and the required behavior in [petty_cash_application_specification.md](./petty_cash_application_specification.md).

The existing spreadsheet/session features should be preserved during migration, but the target system must become a controlled, role-based financial application.

## Phase 0 — Baseline and migration preparation

### Objectives

- Preserve existing uploads, sessions, summaries, and Excel exports.
- Establish a safe foundation for domain workflows.
- Avoid directly modifying production data.

### Work

- Freeze current prototype behavior with regression tests.
- Inventory the existing session JSON structure.
- Create an import strategy for existing sessions, transactions, projects, and opening balances.
- Add development, test, and production configuration.
- Establish database migration tooling.
- Define canonical rules for INR currency, decimal precision, dates, time zones, financial periods, identifiers, and audit timestamps.

### Deliverables

- Baseline test suite
- Migration scripts
- Test database
- Backward-compatible legacy session reader
- Environment configuration template

### Acceptance criteria

- Existing upload, session, summary, filter, and export behavior passes regression tests.
- Existing data can be imported without losing transaction values.
- Production data is not modified during migration development.
- A new deployment can initialize an empty test database reproducibly.

## Phase 1 — Domain database foundation

### Objectives

Replace the JSON session model with normalized financial entities.

### Core entities

- `users`
- `roles`
- `user_sessions`
- `onboarding_tokens`
- `manager_employee_assignments`
- `projects`
- `ledgers`
- `categories`
- `cash_accounts`
- `cash_account_balances`
- `petty_cash_requests`
- `request_status_history`
- `supporting_files`
- `ledger_entries`
- `company_receipts`
- `notifications`
- `notification_preferences`
- `audit_events`
- `financial_periods`
- `legacy_ledger_sessions`

### Work

- Use fixed-precision numeric types for money.
- Enforce foreign keys and unique constraints.
- Store financial records with ownership and audit metadata.
- Prevent direct edits to posted entries.
- Validate request state transitions server-side.
- Add idempotency support for financial mutations.
- Add transaction and row/version-locking helpers.
- Map existing session transactions into the new model.

### Acceptance criteria

- Domain records are persisted independently of legacy session JSON.
- Monetary calculations do not use floating-point persistence.
- Foreign keys, unique constraints, and required indexes are present.
- Financial mutations run inside database transactions.
- Existing sessions remain readable through the compatibility layer.
- Migration results can be reconciled against source session totals.

## Phase 2 — Authentication and RBAC

### Objectives

Implement the required Admin, Manager, and Employee security model.

### Work

- Create the first Admin during initial deployment.
- Require email and password for Admin bootstrap.
- Prevent repeated bootstrap after an Admin exists.
- Hash passwords with Argon2id or bcrypt.
- Implement login, logout, expiration, refresh/server-side sessions, password reset, and first-time password setup.
- Generate temporary, single-use, time-bound onboarding tokens.
- Add login/token rate limiting.
- Add backend authorization for every protected route.
- Add CSRF protection, secure headers, strict CORS, validation, and correlation IDs.

### Role permissions

#### Admin

- User provisioning
- Master data management
- Balance configuration
- Final posting
- Reports
- Legacy Ledger

#### Manager

- Assigned employee requests
- Approval decisions
- Assignment approvals

#### Employee

- Own requests
- Own request history
- Supporting uploads after approval

### Acceptance criteria

- Unauthenticated users cannot access protected APIs or screens.
- Admin, Manager, and Employee permissions are enforced server-side.
- Users cannot access another user’s records.
- Employees cannot approve their own requests.
- Onboarding tokens expire, are single-use, and cannot be reused.
- Passwords are never stored in plaintext.
- Repeated failed authentication attempts are rate limited.
- CORS and security headers are restricted for production configuration.

## Phase 3 — Users, assignments, and notifications

### Objectives

Implement user provisioning, many-to-many manager assignments, and notifications.

### Work

- Add Admin screens and APIs for creating Managers and Employees.
- Send onboarding emails with temporary setup tokens.
- Support user activation, deactivation, and invitation resend.
- Support many-to-many Manager–Employee assignments.
- Require Manager approval or rejection of assignments.
- Preserve assignment status history.
- Add in-app notification history and read/unread state.
- Add independent In-App and Email notification preferences.
- Add SMTP configuration validation and background email dispatch with retry logging.

### Acceptance criteria

- Admin can create a Manager or Employee with username, email, and role.
- A created user receives a secure onboarding token through configured email delivery.
- A Manager can oversee multiple Employees.
- An Employee can have multiple approved Managers.
- An Employee cannot select a Manager before assignment approval.
- Assignment notifications are sent to the correct users.
- Users can disable In-App and Email notifications independently.
- Notifications can be marked as read and remain available in history.
- Email failure does not silently discard the underlying in-app notification.

## Phase 4 — Petty cash request lifecycle

### Objectives

Implement the required request state machine:

```text
DRAFT
  -> SUBMITTED
  -> APPROVED
  -> SUPPORTING_UPLOADED
  -> POSTED
```

Alternative transitions:

```text
SUBMITTED -> DRAFT        Request Changes
SUBMITTED -> REJECTED    Reject
```

### Employee request fields

- Project
- Ledger
- Category
- Request date
- Amount
- Purpose/description
- Optional notes
- Approving Manager

### Work

- Allow Employees to create and edit drafts.
- Allow Employees to submit requests.
- Require approved assigned Managers.
- Prevent supporting files at draft stage.
- Add Manager pending queue.
- Add approve, request-changes, and reject actions.
- Require reasons for request-changes and rejection.
- Preserve complete request status history.
- Allow resubmission after requested changes.

### Acceptance criteria

- Employees can create, edit, save, and submit valid drafts.
- Project and ledger values come only from Admin-controlled master data.
- Requests are always money-out transactions.
- Invalid amounts, dates, users, and Manager assignments are rejected.
- Backend rejects invalid state transitions.
- Managers see only requests assigned to them.
- Request changes require a reason and return the request to editable `DRAFT`.
- Rejections require a reason and prevent posting.
- Approved requests do not reduce the cash balance.
- Every transition records actor, timestamp, reason where applicable, and correlation ID.

## Phase 5 — Secure supporting files and Admin posting

### Objectives

Allow supporting documents only after approval and provide controlled Admin posting.

### File handling

Accept only:

- PDF
- PNG
- JPEG

Implement:

- MIME verification using file contents
- File-size limits
- Filename sanitization
- Private storage
- Access-controlled downloads
- File metadata and checksum
- Multiple files per request
- Upload audit events

### Admin posting

Admin must be able to:

- View approved requests
- View supporting documents
- Validate request data
- Select an effective posting date
- Post or return a request for correction
- View the complete history

### Posting behavior

Posting must atomically:

1. Validate request status.
2. Validate supporting documentation.
3. Validate available balance.
4. Create exactly one ledger payment entry.
5. Deduct the amount from the outstanding balance.
6. Mark the request as `POSTED`.
7. Write audit records.
8. Emit notifications.

### Acceptance criteria

- Draft requests cannot accept supporting documents.
- Invalid extensions, MIME types, oversized files, and unsafe filenames are rejected.
- Only authorized users can download supporting files.
- Admin can review the approved request and its documents.
- Posting requires an effective posting date.
- Posting and balance deduction either both succeed or both roll back.
- A request cannot be posted twice.
- Posted requests cannot be directly edited or deleted.
- File upload and posting events appear in the audit history.

## Phase 6 — Company cash receipts

### Objectives

Implement the Admin-only `Cash Accounts → Company Receipt` workflow.

### Fields

- Amount
- Date
- Description
- Receipt reference
- Idempotency key

### Work

- Validate positive receipt amounts.
- Create a receipt ledger entry.
- Increase the outstanding balance atomically.
- Prevent duplicate submissions.
- Preserve receipt history and audit information.
- Notify relevant users where required.

### Acceptance criteria

- Only authorized Admin users can create company receipts.
- Invalid amounts and dates are rejected.
- A receipt increases the balance exactly once.
- Duplicate idempotency keys do not create duplicate entries.
- Receipt references are unique where required.
- Receipt posting and balance update are atomic.
- Company receipts are distinguishable from employee expense requests.
- Receipt actions are included in audit history.

## Phase 7 — Financial controls and Legacy Ledger isolation

### Objectives

Protect financial records and isolate older spreadsheet data.

### Audit trail

Record immutable events for:

- User creation
- Assignment creation, approval, and rejection
- Request creation, editing, and submission
- Approval, rejection, and change requests
- File upload and download
- Posting
- Receipt creation
- Balance changes
- Period locking
- Legacy Ledger changes
- Authentication and authorization failures

Each event should include actor, action, entity, entity ID, timestamp, before/after values where appropriate, correlation ID, and relevant request metadata.

### Financial integrity

Implement:

- Database transactions
- Row/version locking
- Idempotency keys
- Unique constraints
- Balance validation
- Negative-balance rules
- Financial-period locks
- Backdated posting controls
- Reversal/adjustment entries instead of editing posted records
- Concurrent posting protection

### Legacy Ledger

Create an isolated Admin-only workspace for:

- Importing older spreadsheet sessions
- Viewing and managing legacy rows
- Preserving legacy history
- Preventing automatic synchronization into the active ledger

### Acceptance criteria

- Every financial state transition creates an immutable audit event.
- Posted records cannot be modified directly.
- Corrections use authorized reversal or adjustment entries.
- Closed periods reject unauthorized changes.
- Concurrent postings cannot produce an incorrect balance.
- Negative-balance rules are enforced consistently.
- Legacy rows cannot automatically become active posted ledger entries.
- Legacy and controlled records are clearly distinguished in the UI and APIs.

## Phase 8 — Reporting and exports

### Objectives

Implement monthly reporting and the required export format.

### Monthly reporting

Allow month selection and display:

- Posted entries by posting month
- Period totals
- Daily cash movement
- Spending by ledger
- Spending by category and project
- Opening and closing balances
- Unposted requests separately by request date
- Pending approvals
- Rejected and change-request totals

### Required 12-column schema

Both active monthly exports and Legacy Ledger exports must use exactly:

1. Date
2. Ledger
3. Description
4. Receipt
5. Payment
6. Outstanding Balance
7. Approved By
8. Requested By
9. Category
10. Project
11. Supportings
12. Notes

### ZIP export

Admin monthly exports must contain:

- Excel cash sheet
- Petty Cash Summary
- Supporting Files sheet
- All supporting documents
- Relative links from Excel to extracted files

The primary `Supportings` cell must link to the first supporting file for that request.

### Acceptance criteria

- Monthly posted totals match the authoritative ledger.
- Pending and unposted requests are excluded from posted totals.
- Unposted requests are filtered by request date.
- Daily movement and ledger/category/project breakdowns reconcile to period totals.
- Exported sheets contain exactly the required 12 columns in the required order.
- ZIP exports contain all required documents and workbook sheets.
- Relative links work after extracting the ZIP archive.
- Export generation does not mutate financial data.
- Export failures are surfaced clearly and logged.

## Phase 9 — Swagger/OpenAPI and operations

### Objectives

Provide interactive API documentation and production observability.

### API documentation

Document:

- Authentication
- Users and assignments
- Projects, ledgers, and categories
- Requests
- Approvals
- Supporting files
- Posting
- Company receipts
- Reports
- Notifications
- Legacy Ledger

Documentation must include request/response schemas, authentication requirements, role permissions, error responses, state transitions, and idempotency behavior.

### Observability

Implement:

- JSON structured logs
- Correlation IDs
- Request and background-job tracing
- Error tracking
- API latency and error metrics
- Business metrics for request volume, approvals, postings, rejections, balance changes, and queue backlog
- Database health checks
- Backup verification
- Alerts for failed postings, queue backlog, authorization failures, anomalous balance changes, and backup failures

### Acceptance criteria

- Swagger UI is available in non-production or protected production environments.
- Every production API route has an OpenAPI definition.
- Protected routes show their required authentication and roles.
- Logs are structured and include correlation IDs.
- Errors are captured with actionable context.
- Health checks detect database connectivity and readiness failures.
- Queue, posting, backup, and financial anomaly alerts are testable.
- Sensitive credentials and personal data are not written to logs.

## Phase 10 — Frontend redesign

### Objectives

Replace the spreadsheet-first experience with role-based workflows while preserving import and compatibility features.

### Shared navigation

- Dashboard
- Profile
- Notifications
- Logout

### Admin navigation

- Dashboard
- Users & Access
- Creating Projects & Ledgers, configuring opening-balance(outstanding balance)
- Creating new company receipts
- Requests for Posting
- Reports
- Legacy Ledger
- Audit Log

### Manager navigation

- Dashboard
- Pending Assignments
- Approval Queue
- Request History
- Assigned Employees
- Profile
- Notifications

### Employee navigation

- Dashboard
- New Request
- Drafts
- Submitted Requests
- Request History
- Assigned Managers
- Profile
- Notifications

### UI requirements

- No gradients
- No default framework blue
- Consistent subtle corner radius
- Accessible controls
- Responsive layouts
- Keyboard navigation
- Clear validation errors
- Loading states
- Confirmation dialogs
- Success and error notifications
- Empty states
- Permission-aware navigation

The existing spreadsheet interface may remain as a controlled migration/import utility rather than the primary product workflow.
* Reference Standards: Consult and follow the design patterns and skill guidelines in nextlevelbuilder/ui-ux-pro-max-skill (which was already installed in this project) before creating or modifying any UI components.


### Acceptance criteria

- Each role sees only the navigation and actions allowed for that role.
- Employee request creation, Manager approval, and Admin posting can be completed through the UI.
- All forms provide validation, loading, success, and error states.
- Keyboard navigation and accessible labels are present for interactive controls.
- Screens remain usable on mobile, tablet, and desktop sizes.
- The UI follows the specification’s visual constraints.
- Unauthorized actions are hidden where appropriate and rejected by the backend regardless of UI state.
- Existing import and compatibility workflows remain available and functional.


## Phase 11 — Testing and release verification

### Backend tests

- Authentication and password setup
- RBAC and resource authorization
- Assignment rules
- Request state transitions
- Self-approval prevention
- File validation
- Duplicate receipt protection
- Idempotency
- Balance calculations
- Atomic posting
- Period locking
- Audit event creation

### Frontend tests

- Role-based navigation
- Form validation
- Draft editing
- Approval actions
- File upload states
- Notifications
- Responsive layouts
- Accessibility behavior
- Loading and error states

### Financial tests

- Opening balance
- Multiple receipts
- Multiple payments
- Approved but unposted requests
- Posted requests
- Concurrent posting
- Duplicate requests
- Reversal and adjustment behavior
- Monthly report totals
- ZIP/export links

### Operational tests

- Database backup and restore
- Health and readiness probes
- Queue retry behavior
- SMTP failure handling
- Error tracking
- Log correlation
- Deployment rollback

### Acceptance criteria

- All critical and high-priority automated tests pass.
- Unauthorized API and UI access tests pass.
- Financial calculations reconcile against independently calculated expected values.
- State-transition tests cover every allowed and rejected transition.
- File security tests cover invalid MIME types, sizes, filenames, and access permissions.
- Duplicate posting and receipt tests prove balances are not double-counted.
- Existing session, upload, summary, filter, and analytics regression tests pass.
- Accessibility and responsive checks pass for supported breakpoints.
- Backup restore and deployment rollback are successfully demonstrated.
- Production release approval is documented.

## Recommended delivery sequence

1. Baseline tests and migration preparation
2. Domain schema and database migrations
3. Authentication and RBAC
4. Users, assignments, and notifications
5. Request lifecycle
6. Supporting files and Admin posting
7. Company receipts and balance controls
8. Audit trail and Legacy Ledger
9. Reports and ZIP exports
10. Swagger and observability
11. Role-based frontend
12. Full verification and production release

## Scope decisions

Cash advances, OCR, recurring expenses, accounting integrations, multi-branch support, and multi-currency should remain separate future initiatives unless the business explicitly adds them to the approved scope.

The implementation must not begin by deleting the current session functionality. The current import, session history, summary, and analytics capabilities should be migrated, tested, and retained as compatibility functionality while the controlled workflows are introduced.
