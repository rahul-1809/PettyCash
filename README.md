# PettyCash Pro

A production-grade, enterprise petty cash management and canonical ledger system with role-based governance, multi-tier approval workflows, voucher receipt audit trails, and template-faithful financial Excel reporting.

---

## Architecture & Core Capabilities

- **Role-Based Access Control (RBAC)**:
  - **Employee**: Drafts petty cash requests, attaches cost centers/ledgers, uploads voucher evidence upon approval, and tracks disbursement status.
  - **Manager**: Reviews pending requests within their hierarchy, approves, requests corrections with detailed feedback, or rejects.
  - **Admin**: Master financial control, user & hierarchy provisioning, cash vault opening balance adjustments, financial accounting period locks, and canonical ledger posting.

- **Voucher Audit Trail & Document Evidence**:
  - Secure storage for PDF and image receipts with SHA-256 integrity verification.
  - Immutable audit logging tracking every state transition with correlation IDs and diff payloads.

- **Dual-Engine Persistence & Cloud Scale**:
  - **Local Development**: Zero-config SQLite database.
  - **Production**: Live cloud PostgreSQL (Supabase) with persistent connection pooling (`psycopg_pool`) and query latency optimization (<300ms).

- **Enterprise Observability & Protection**:
  - Health probes (`/health/live` and `/health/ready`) monitoring database and storage availability.
  - Built-in production alerts (queue backlog, failed postings, auth failures, anomalous balances, backup freshness).
  - Sliding-window in-memory rate limiting and short-lived session caching.

- **Financial Reporting Engine**:
  - 12-column template-faithful Excel generation adhering strictly to accounting standards.
  - Side-by-side dynamic pivot tables and reconciliation statements with native formula preservation.
  - Complete monthly ZIP evidence packages bundling workbooks and physical receipt documents.

---

## 🏛️ System Architecture & Workflows

### 1. Multi-Tier System Architecture
```mermaid
flowchart TD
    subgraph ClientLayer["Frontend Client Layer (React 18 + Vite + Tailwind)"]
        UI_Emp["Employee Dashboard (Drafting & Vouchers)"]
        UI_Mgr["Manager Dashboard (Approvals & Hierarchy)"]
        UI_Adm["Admin Dashboard (Vault, Periods & Ledger)"]
        API_Client["Centralized API Client (Bearer Tokens & Correlation IDs)"]
        UI_Emp --> API_Client
        UI_Mgr --> API_Client
        UI_Adm --> API_Client
    end

    subgraph GatewayLayer["API Gateway & Middleware Layer (FastAPI)"]
        MW_Trace["Correlation ID Tracing Middleware"]
        MW_CORS["CORS Middleware"]
        MW_Rate["In-Memory Sliding-Window Rate Limiter"]
        MW_Auth["Bearer Token Auth & In-Memory Fast Cache"]
        API_Client --> MW_Trace
        MW_Trace --> MW_CORS
        MW_CORS --> MW_Rate
        MW_Rate --> MW_Auth
    end

    subgraph ServiceLayer["Core Domain Services"]
        S_Req["Request & Workflow Service"]
        S_Post["Posting & Canonical Ledger Service"]
        S_Fin["Financial Control & Vault Service"]
        S_Supp["Supporting Files & SHA-256 Storage"]
        S_Audit["Immutable Audit Service"]
        S_Notif["Notification & SMTP Email Service"]
        S_Rep["Excel & Monthly ZIP Report Engine"]
        MW_Auth --> S_Req
        MW_Auth --> S_Post
        MW_Auth --> S_Fin
        MW_Auth --> S_Supp
        MW_Auth --> S_Audit
        MW_Auth --> S_Notif
        MW_Auth --> S_Rep
    end

    subgraph PersistenceLayer["Storage & Database Layer"]
        DB_Pool["Psycopg 3 Connection Pool (min: 2, max: 12)"]
        Supabase[("Supabase PostgreSQL (Cloud Database)")]
        LocalDB[("SQLite Fallback (sessions.db)")]
        FileStore["Private Supporting Files (PDF/PNG Receipts)"]
        SMTP_Server["Gmail SMTP Server (Email Dispatch)"]
        
        S_Req & S_Post & S_Fin & S_Audit & S_Rep --> DB_Pool
        DB_Pool --> Supabase
        DB_Pool -.-> LocalDB
        S_Supp --> FileStore
        S_Notif --> SMTP_Server
    end
```

### 2. Request Lifecycle & Approval State Machine
```mermaid
stateDiagram-v2
    [*] --> DRAFT: Employee creates request
    DRAFT --> SUBMITTED: Employee submits for review
    SUBMITTED --> DRAFT: Manager requests correction
    SUBMITTED --> REJECTED: Manager rejects request
    SUBMITTED --> APPROVED: Manager approves request
    APPROVED --> READY_FOR_POSTING: Employee uploads physical voucher
    READY_FOR_POSTING --> RETURNED_FOR_CORRECTION: Admin flags invoice discrepancy
    RETURNED_FOR_CORRECTION --> READY_FOR_POSTING: Employee re-uploads voucher
    READY_FOR_POSTING --> POSTED: Admin finalizes to Canonical Ledger
    POSTED --> REVERSED: Admin executes audited reversal
    POSTED --> [*]
    REJECTED --> [*]
    REVERSED --> [*]
```

### 3. End-to-End Voucher Evidence & Ledger Posting Sequence
```mermaid
sequenceDiagram
    autonumber
    actor Employee
    actor Manager
    actor Admin
    participant System as FastAPI Backend
    participant DB as Supabase PostgreSQL
    participant FS as Supporting Storage
    participant SMTP as Gmail SMTP

    Employee->>System: Submit Petty Cash Request (Amount, Purpose, Cost Center)
    System->>DB: Record Request (SUBMITTED) & Audit Event
    System->>SMTP: Dispatch notification email to Manager
    Manager->>System: Review & Approve Request
    System->>DB: Update Status (APPROVED) & Audit Event
    System->>SMTP: Dispatch approval email to Employee
    Employee->>System: Upload Receipt Document (PDF/JPG)
    System->>FS: Verify SHA-256 Checksum & Save to Disk
    System->>DB: Link voucher to request (READY_FOR_POSTING)
    System->>SMTP: Dispatch ready-for-posting email to Admin
    Admin->>System: Validate voucher against Ledger Window
    Admin->>System: Post Request to Canonical Ledger
    System->>DB: Deduct Vault, Credit Expense, Seal Transaction
    System->>SMTP: Dispatch confirmation email to Employee
    Admin->>System: Request Monthly Audit ZIP Package
    System->>System: Generate 12-Column Excel & Attach Evidence
    System-->>Admin: Deliver Complete Reconciliation ZIP Bundle
```

---

## Tech Stack

| Component | Technology |
| :--- | :--- |
| **Backend API** | Python 3.11+, FastAPI, Uvicorn, Pydantic |
| **Frontend UI** | React 18, Vite, Tailwind CSS, Lucide Icons |
| **Database** | PostgreSQL (Supabase) / SQLite, Psycopg 3 Pool |
| **Excel Engine** | OpenPyXL, Pandas |
| **Auth & Security** | BCrypt password hashing, Bearer Token sessions, Sliding-window Rate Limiting |
| **Notifications** | Gmail SMTP background delivery, Real-time in-app alerts |
| **Deployment** | Docker multi-stage build, Render Blueprint (`render.yaml`) |

---

## Local Development Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm

### 1. Backend Setup
```bash
# Clone the repository
git clone https://github.com/rahul-1809/PettyCash.git
cd PettyCash

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your database or SMTP credentials if using cloud PostgreSQL

# Start FastAPI server (Runs on http://localhost:8000)
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
# In a separate terminal window
cd frontend
npm install
npm run dev
# Vite runs on http://localhost:3000 (proxies /api to port 8000)
```

---

## Environment Variables Configuration

Create a `.env` file in the root directory:

```env
# Runtime
APP_ENV=development
PORT=8000

# Persistence
# Leave blank to use local SQLite (sessions.db). Set PostgreSQL URL for production.
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres

# CORS & Base URL
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
APP_BASE_URL=http://localhost:3000

# Logging & Uploads
LOG_LEVEL=INFO
UPLOAD_MAX_BYTES=10485760

# SMTP Email Notification Service
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_SENDER=your-email@gmail.com
```

---

## Initial Setup & Production Bootstrap

### Creating the First Administrator
1. When starting with a clean database, open the web app.
2. The login screen automatically displays the **"Init Admin"** tab when no administrator exists.
3. Enter the desired administrator username, email, and password (minimum 12 characters).
4. Click **Initialize Administrator**.
5. Once created, the bootstrap endpoint permanently locks down, and the "Init Admin" tab disappears from the UI.

Alternatively, you can initialize an administrator via CLI:
```bash
python scripts/create_admin.py --username "Admin" --email "admin@yourcompany.com" --password "YourStrongPassword123!"
```

### Resetting Data for Production
To clear all test/demo transactions, requests, and users while keeping database tables, system roles, and baseline categories intact:
```bash
python scripts/reset_database.py
```
*(You will be prompted to type `RESET` to confirm).*

---

## Production Deployment on Render

This project includes a multi-stage [Dockerfile](Dockerfile) and a [render.yaml](render.yaml) blueprint for one-click deployment.

### Steps to Deploy:
1. Push your repository to GitHub:
   ```bash
   git add .
   git commit -m "feat: production release"
   git push origin main
   ```
2. In the [Render Dashboard](https://dashboard.render.com/):
   - Click **New +** > **Web Service**.
   - Select your GitHub repository.
   - Select Environment: **Docker**.
   - Health Check Path: `/health/ready`.
3. Add the required Environment Variables in Render:
   - `APP_ENV`: `production`
   - `DATABASE_URL`: Your Supabase connection string.
   - `ALLOWED_ORIGINS`: `*` (or your Render URL).
   - `APP_BASE_URL`: `https://<your-service>.onrender.com`
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SENDER`.
4. Click **Deploy**.

---

## Automated Verification & Testing

The application includes an extensive automated test suite covering all 12 system phases (domain models, authentication, request lifecycle, approvals, vouchers, ledger postings, financial periods, reporting, and operations):

```bash
PYTHONPATH=. pytest -v
```

All 74 test suites run in an isolated test database and must pass before deployment.

---

## License
Proprietary & Confidential. Built for enterprise financial management.
