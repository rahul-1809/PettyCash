# Petty Cash Management System — Product & Engineering Specification

## 1. Overview & User Roles
The Petty Cash application is a production-grade financial management system designed to track cash disbursements, approvals, receipts, and reporting. 

There are **3 distinct user roles** with strict Role-Based Access Control (RBAC):
1. **Admin:** System setup, user provisioning, manager-employee mapping, project/ledger creation, opening balance configuration, cash receipts, final ledger posting, reporting, and legacy ledger management.
2. **Manager:** Reviews and approves/rejects employee assignments and petty cash requests.
3. **Employee:** Creates, edits, and submits petty cash requests, and uploads supporting documentation post-approval.

Universal Access: Every role (Admin, Manager, and Employee) has access to their own dedicated Profile section and Notifications center.
---

## 2. Application Workflow

### Phase 1: Initial Setup & User Onboarding
1. **Admin Bootstrap:** On initial application startup/deployment, the primary **Admin** account is created by providing an email and password.
2. **Admin Login:** The Admin logs into the Petty Cash application using their credentials.
3. **User Creation:** Inside the **Users & Access** section, the Admin creates accounts for Managers and Employees by entering:
   - Username
   - Email Address
   - Role selection via dropdown (`Manager` or `Employee`)
4. **Token Generation & Email Dispatch:** Upon clicking **Create Manager/Employee**, the system generates a secure, temporary onboarding token and dispatches an email to the new user containing:
   - Their registered email address
   - The temporary setup token
5. **Password Setup:** On the login screen, new users select the **Set Password / First-Time Login** option, enter their temporary token, and define their permanent password.
6. **Standard Authentication:** Once the password is set, the Manager or Employee logs in using their email and newly created password.

### Phase 2: Manager–Employee Assignment (Many-to-Many)
1. **Assignment Initiation:** In **Users & Access**, the Admin assigns Employees to Managers. This supports a **many-to-many relationship** (one Manager can oversee multiple Employees, and one Employee can report to multiple Managers).
2. **Assignment Notification:** Once assigned, the target Manager receives both an **in-app notification** and an **email** (e.g., *"You have been assigned Employee [Name] by Admin [Name]"*).
3. **Manager Approval:** Upon logging in, the Manager views the pending assignment request and chooses to **Approve** or **Reject**:
   - **If Approved:** Both the Admin and the assigned Employee receive in-app and email notifications. The Employee can now view the Manager in their **Assigned Managers** section.
   - **If Rejected:** The Admin who initiated the assignment is notified via in-app alert and email.

### Phase 3: Master Data & Balance Configuration
- **Admin-Only Configuration:** Only Admins can create and manage:
  - **Projects**
  - **Ledgers**
  - **Initial/Outstanding Cash Balance**

### Phase 4: Petty Cash Request Lifecycle
1. **Draft Creation (Employee):**
   - Employees raise a request (always categorized as **money out**) by entering:
     - **Project** (selected from Admin-created list)
     - **Ledger** (selected from Admin-created list)
     - **Category**
     - **Request Date** (defaults to current entry date)
     - **Amount**
     - **Purpose / Description**
     - **Notes** *(Optional)*
     - **Approving Manager** (selected from the Employee's approved assigned managers)
   - *Note:* Supporting files are neither required nor accepted at the draft stage.
2. **Submission (Employee):**
   - The Employee reviews/edits the draft and clicks **Submit**.
   - The request enters the selected Manager’s review queue. **Submitting does not deduct from the outstanding balance.**
3. **Manager Review:**
   - The designated Manager receives an in-app and email notification.
   - The Manager reviews the request and selects one of three actions *(Note: A requester cannot approve their own request)*:
     - **Approve:** Advances the request to the supporting document upload stage.
     - **Request Changes:** Returns the request to `DRAFT` status so the Employee can edit and resubmit. *(Mandatory reason required)*.
     - **Reject:** Terminates/returns the request without posting. *(Mandatory reason required)*.
4. **Supporting Document Upload (Employee):**
   - After Manager approval, the Employee navigates to the request's **History** view and uploads supporting documentation (`PDF`, `PNG`, or `JPEG`).
   - Upon upload, the **Admin** receives a notification.
5. **Final Review & Ledger Posting (Admin):**
   - The Admin reviews the approved request alongside the uploaded supporting document and selects an **effective posting date**.
   - Clicking **Post** creates a single ledger payment entry and **deducts the amount from the outstanding balance**.
   - *Example:* If the outstanding balance is `₹5,000.00` and the Admin posts an approved `₹300.00` request, the balance updates to `₹4,700.00`.

### Phase 5: Direct Company Cash Receipts (Admin)
- When the company replenishes petty cash, the Admin navigates to **Cash Accounts → Company Receipt** and records:
  - **Amount**
  - **Date**
  - **Description**
- This is a direct receipt requiring no Employee request or Manager approval.
- *Example:* Recording a `₹150.00` receipt increases the balance from `₹4,700.00` to `₹4,850.00`.
- **Idempotency / Duplicate Protection:** The system enforces duplicate detection to prevent the same receipt from being posted twice.

---

## 3. Request State Machine

```text
DRAFT ──[Submit]──> SUBMITTED ──[Approve]──> APPROVED ──[Employee Uploads Support]──> [Admin Posts] ──> POSTED
  ▲                     │
  │                     ├──[Request Changes (Reason Req.)]──> (Returns to DRAFT)
  │                     │
  │                     └──[Reject (Reason Req.)]───────────> REJECTED (Returns to DRAFT / Closed)
  │
  └──[Edit while in DRAFT]
```

---

## 4. Core Modules & Functional Requirements

### 4.1 Reports & Monthly Export
- **Monthly Filtering:** Users/Admins select a specific month to view:
  - Posted entries for that posting month
  - Period totals
  - Daily cash movement
  - Spending breakdown by ledger
  - *Note:* Unposted/pending requests are listed separately filtered by their **request date**.
- **ZIP Archive Export:** Admins can download a monthly ZIP bundle containing:
  1. Excel Cash Sheet (`.xlsx`)
  2. Petty Cash Summary
  3. All associated Supporting Files
- **Excel Hyperlink Structure:**
  - Users must extract the ZIP archive before opening Excel to preserve relative file paths.
  - The main **Supportings** column links directly to the *first* supporting file for that request.
  - A dedicated **Supporting Files** sheet in the workbook links to *every* uploaded file.

### 4.2 Standardized 12-Column Ledger Schema
Both the **Monthly Report Excel Export** and the **Legacy Ledger Excel Sheet** must strictly follow this 12-column structure:
1. `Date`
2. `Ledger`
3. `Description`
4. `Receipt`
5. `Payment`
6. `Outstanding Balance`
7. `Approved By`
8. `Requested By`
9. `Category`
10. `Project`
11. `Supportings`
12. `Notes`

### 4.3 Notifications Center
- Dedicated **Notifications** section accessible to all users.
- **Granular Preferences:** Each user can independently toggle **In-App** and **Email** notifications on or off.
- **Email Prerequisites:** Outbound email alerts require valid SMTP server configuration and a verified sender/recipient mailbox.
- **Alert Management:** Users can inspect alert history and mark in-app notifications as read.

### 4.4 Legacy Ledger Workspace
- Maintained as an isolated **Admin-only workspace** for viewing/managing older spreadsheet sessions.
- Rows in the Legacy Ledger **do not** automatically sync or convert into posted entries in the active, controlled cash book.

---

## 5. UI/UX & Design Guidelines
All new and existing screens must adhere strictly to the following visual and interaction standards:
- **Reference Standards:** Consult and follow the design patterns and skill guidelines in [`nextlevelbuilder/ui-ux-pro-max-skill`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) before creating or modifying any UI components.
- **Visual Constraints:**
  - **No gradients** (use flat, deliberate, high-contrast surfaces).
  - **No default browser/framework blues** (use a curated, domain-appropriate financial color palette).
  - **No sharp/0px corners** (use consistent, subtle border radii).
  - **No generic/stock icons** (use cohesive, intentional iconography).
- **Usability & Accessibility:** Controls must be consistent across all screens, WCAG accessible, fully responsive, and provide clear, immediate user feedback (loading states, validation errors, confirmation toasts).

---

## 6. Security, Architecture & Operations

### 6.1 Financial-Grade Security
- Strong password hashing (e.g., Argon2id / bcrypt) and cryptographically secure, time-bound, single-use onboarding tokens.
- Strict Role-Based Access Control (RBAC) and resource-level authorization (e.g., preventing self-approval, enforcing manager-employee assignment checks, locking posted ledger records against tampering).
- Immutable audit trails for all financial state transitions, balance adjustments, approvals, and file uploads.
- Strict file upload validation (MIME-type verification, file size limits, sanitized filenames) restricted to `PDF`, `PNG`, and `JPEG`.
- CSRF protection, rate limiting, secure HTTP headers, and encrypted credentials/SMTP secrets.

### 6.2 System Design & API Documentation
- **Production-Grade Architecture:** Built for reliability, ACID-compliant database transactions (especially around balance deductions and receipt postings), idempotency keys for duplicate prevention, and asynchronous background workers for email/notification dispatch and ZIP generation.
- **API Documentation:** Parallel implementation of **Swagger UI / OpenAPI** specifications for interactive API exploration and testing.

### 6.3 Monitoring & Supportability
The production deployment must include full observability:
- **Structured Application Logging:** JSON-formatted logs with correlation IDs and severity levels.
- **Error Tracking:** Automated exception capture and stack-trace aggregation.
- **Metrics:** Application performance metrics (latency, throughput, error rates) and business metrics (request volume, posting rates).
- **Alerts:** Automated alerting rules for critical failures, queue backlogs, or anomalous financial activity.
- **Database Health Checks:** Liveness/readiness probes monitoring connection pools and query latency.
- **Backup Monitoring:** Automated verification of scheduled database and file-storage backups.
- **Request Tracing:** End-to-end distributed tracing across API requests, background jobs, and database queries.