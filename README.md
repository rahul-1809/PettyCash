# PettyCash Pro 💰

> An interactive, production-ready web application for managing petty cash ledgers, auto-generating dynamic pivot summaries & reconciliation statements, and exporting template-faithful Excel workbooks.

---

## 🌟 Key Features

1. **Excel Upload & Ingestion**:
   - Upload any petty cash `.xlsx` file.
   - Starts with empty sessions; upload an Excel workbook into the active session.
   - Auto-extracts opening balance, date periods, ledgers, and cost centers.

2. **Interactive Spreadsheet & CRUD Management**:
   - **Inline Edit & Row Management**: Modify descriptions, ledgers, receipts, payments, categories, approvers, and requesters.
   - **Add New Entry**: Dedicated form modal with auto-completion from known ledgers and projects.
   - **Delete Entries**: Instant removal with safety confirmation.
   - **Live Balance Recalculation**: Recomputes running `Outstanding Balance` sequentially ($\text{Balance}_i = \text{Balance}_{i-1} + \text{Receipt}_i - \text{Payment}_i$) whenever transactions or the opening balance change.
   - **Realtime Filter & Search**: Search by narration or filter by Project and Ledger.

3. **Dynamic Petty Cash Summary**:
   - **Left Table (Pivot Breakdown)**: Groups transactions by Project / Cost Center, calculating `Sum of Receipt`, `Sum of Payment`, and `Grand Total`.
   - **Right Table (Reconciliation Statement)**:
     - Opening Balance with period start date.
     - Additions breakdown with `=+SUM(...)` formula.
     - Withdrawals breakdown with `=-SUM(...)` formula.
     - Closing Balance evaluated as `Opening + Additions - Withdrawals`.

4. **Template-Faithful Excel Export**:
   - Downloads a multi-sheet `.xlsx` file containing:
     - **`Petty Cash Sheet`**: Full ledger with signature yellow headers (`#FFFF00`), borders, column widths, and currency formatting.
     - **`Petty Cash Summary `**: Side-by-side pivot table and reconciliation table with exact native Excel formulas (`=+SUM(...)`, `=-SUM(...)`), headers, and borders.

5. **Visual Analytics**:
   - Live breakdown bars showing expense distributions across projects and inflow sources.

---

## 🚀 Quick Start (Local Run)

### Option 1: Quick Launch
```bash
./run.sh
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser!

### Option 2: Run Backend & Frontend Separately
```bash
# 1. Start Backend (Port 8000)
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 2. In a separate terminal, run Vite Dev Server (Port 3000)
cd frontend
npm run dev
```

---

## 🐳 Production Deployment

### Docker Deployment (Render, Railway, Fly.io, AWS, GCP)
A production multi-stage Dockerfile is included:
```bash
docker build -t petty-cash-pro .
docker run -p 8000:8000 petty-cash-pro
```

### Cloud Platforms (e.g., Render / Railway / Heroku):
- Set build command: `cd frontend && npm install && npm run build && cd .. && pip install -r backend/requirements.txt`
- Set start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

### Recommended Free Deployment: Render + Supabase

The app uses SQLite locally, but Render's free filesystem is temporary. For
persistent saved sessions, set `DATABASE_URL` to a Supabase PostgreSQL
connection string. The backend automatically uses Supabase when `DATABASE_URL`
is set and keeps SQLite as the local-development fallback.

1. Create a free project at [Supabase](https://supabase.com).
2. Open **Connect**, select **Transaction pooler**, and copy its connection
   string. Replace the password placeholder with your database password.
3. Push this repository to GitHub.
4. In [Render](https://render.com), create **New → Web Service**, connect the
   repository, choose **Docker**, and select the **Free** plan.
5. Add this Render environment variable:

   ```text
   DATABASE_URL=postgresql://...
   ```

6. Set the Render health check path to `/api/health`, then deploy.

The `sessions` table is created automatically on the first startup. Do not
commit the Supabase connection string to the repository. Supabase Free
projects can pause after inactivity; their database contents remain stored.
Each uploaded session stores both the parsed transactions/summary and the
original workbook contents in Supabase. Existing sessions created before this
feature contain their parsed data but cannot recover an original workbook that
was never stored.

---

## 📁 Project Structure

```
PettyCash/
├── backend/
│   ├── main.py              # FastAPI application & REST endpoints
│   ├── excel_service.py     # openpyxl parser, calculation & export generator
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Interactive React dashboard & CRUD
│   │   ├── main.jsx         # React DOM root
│   │   └── index.css        # Tailwind styles & scrollbars
│   ├── package.json         # Node dependencies
│   ├── tailwind.config.js   # Tailwind configuration
│   └── vite.config.js       # Vite configuration with API proxy
├── Dockerfile               # Production multi-stage Docker build
├── run.sh                   # One-click startup script
└── README.md
```
