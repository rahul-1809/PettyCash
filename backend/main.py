import os
import base64
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from backend.excel_service import parse_petty_cash_file, recalculate_summary, generate_styled_excel, generate_drilldown_excel
    from backend.database import init_db, list_sessions, create_session, get_session, update_session, rename_session, delete_session
except ImportError:
    from excel_service import parse_petty_cash_file, recalculate_summary, generate_styled_excel, generate_drilldown_excel
    from database import init_db, list_sessions, create_session, get_session, update_session, rename_session, delete_session

app = FastAPI(title="Petty Cash Management API")

# Initialize SQLite DB on startup
init_db()

# Enable CORS for local development and deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_EXCEL_FILENAME = "RTEAM -Petty Cash Sheet -  01.10.2026-06.11.2026.xlsx"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXCEL_PATH = os.path.join(BASE_DIR, DEFAULT_EXCEL_FILENAME)


# ─── Pydantic Models ────────────────────────────────────────────────────────

class TransactionItem(BaseModel):
    id: Optional[str] = None
    date: Optional[str] = ""
    month: Optional[str] = ""
    ledger: Optional[str] = ""
    memo: Optional[str] = ""
    receipt: Optional[float] = 0.0
    payment: Optional[float] = 0.0
    balance: Optional[float] = 0.0
    approved: Optional[str] = ""
    requested_by: Optional[str] = ""
    category: Optional[str] = ""
    project: Optional[str] = ""
    status: Optional[str] = "NA"
    supportings: List[dict] = Field(default_factory=list)
    notes: Optional[str] = ""


class RecalculateRequest(BaseModel):
    opening_balance: float
    start_date: str
    end_date: str
    transactions: List[TransactionItem]


class SaveSessionRequest(BaseModel):
    name: Optional[str] = None          # If provided at create time
    opening_balance: float
    start_date: str
    end_date: str
    transactions: List[TransactionItem]
    source_excel_base64: Optional[str] = None
    source_excel_filename: Optional[str] = None


class RenameSessionRequest(BaseModel):
    name: str


class DrilldownExportRequest(BaseModel):
    project: str
    type: str  # 'receipt' | 'payment'
    transactions: List[TransactionItem]


# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "Petty Cash Management API"}


# ─── Default Data ────────────────────────────────────────────────────────────

@app.get("/api/default-data")
def get_default_data():
    if not os.path.exists(DEFAULT_EXCEL_PATH):
        raise HTTPException(status_code=404, detail="Default Excel file not found.")
    try:
        data = parse_petty_cash_file(DEFAULT_EXCEL_PATH)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse default file: {str(e)}")


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported.")
    try:
        content = await file.read()
        data = parse_petty_cash_file(content)
        # Attach original filename to data so frontend can use it as default session name
        data["filename"] = file.filename
        data["source_excel_base64"] = base64.b64encode(content).decode("ascii")
        data["source_excel_filename"] = file.filename
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded file: {str(e)}")


# ─── Recalculate ─────────────────────────────────────────────────────────────

@app.post("/api/recalculate")
def recalculate(req: RecalculateRequest):
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        summary_result = recalculate_summary(
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            transactions=tx_dicts
        )
        return summary_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recalculation error: {str(e)}")


# ─── Session CRUD ─────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def api_list_sessions():
    """Return all sessions (metadata only, no transaction blobs)."""
    return list_sessions()


@app.post("/api/sessions")
def api_create_session(req: SaveSessionRequest):
    """Create a new saved session from current state."""
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        # Compute fresh summary before saving
        summary = recalculate_summary(
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            transactions=tx_dicts
        )
        name = req.name or f"Petty Cash {req.start_date} – {req.end_date}"
        session = create_session(
            name=name,
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            transactions=summary.get("transactions", tx_dicts),
            summary=summary,
            source_excel_base64=req.source_excel_base64,
            source_excel_filename=req.source_excel_filename,
        )
        # Return flattened structure (without nested data blob for list view)
        return {
            "id": session["id"],
            "name": session["name"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "opening_balance": session["opening_balance"],
            "start_date": session["start_date"],
            "end_date": session["end_date"],
            "tx_count": session["tx_count"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@app.get("/api/sessions/{session_id}")
def api_get_session(session_id: str):
    """Load a session's full data (transactions + summary)."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "id": session["id"],
        "name": session["name"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "opening_balance": session["opening_balance"],
        "start_date": session["start_date"],
        "end_date": session["end_date"],
        "tx_count": session["tx_count"],
        **session["data"],   # expands: transactions, summary
    }


@app.put("/api/sessions/{session_id}")
def api_update_session(session_id: str, req: SaveSessionRequest):
    """Save/overwrite an existing session with new state."""
    existing = get_session(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        summary = recalculate_summary(
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            transactions=tx_dicts
        )
        session = update_session(
            session_id=session_id,
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            transactions=summary.get("transactions", tx_dicts),
            summary=summary,
            source_excel_base64=req.source_excel_base64,
            source_excel_filename=req.source_excel_filename,
            name=req.name,
        )
        return {
            "id": session["id"],
            "name": session["name"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "opening_balance": session["opening_balance"],
            "start_date": session["start_date"],
            "end_date": session["end_date"],
            "tx_count": session["tx_count"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update session: {str(e)}")


@app.patch("/api/sessions/{session_id}/rename")
def api_rename_session(session_id: str, req: RenameSessionRequest):
    """Rename a session without changing its data."""
    existing = get_session(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found.")
    session = rename_session(session_id, req.name)
    return {"id": session["id"], "name": session["name"], "updated_at": session["updated_at"]}


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str):
    """Permanently delete a session."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"deleted": True}


# ─── Drilldown Export ─────────────────────────────────────────────────────────

@app.post("/api/export-drilldown")
def export_drilldown(req: DrilldownExportRequest):
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        excel_buf = generate_drilldown_excel(req.project, req.type, tx_dicts)
        filename = f"Details_{req.project}_{req.type}.xlsx".replace(" ", "_").replace("/", "-")
        return StreamingResponse(
            excel_buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Full Export ──────────────────────────────────────────────────────────────

@app.post("/api/export")
def export_excel(req: RecalculateRequest):
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        excel_buffer = generate_styled_excel(
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            transactions=tx_dicts
        )
        filename = f"Petty_Cash_{req.start_date}_to_{req.end_date}.xlsx".replace(" ", "_").replace("/", "-")
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")


# ─── Serve Frontend ───────────────────────────────────────────────────────────

frontend_dist = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
