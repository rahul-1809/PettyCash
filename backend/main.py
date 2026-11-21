import os
import base64
import threading
from typing import List, Dict, Any, Optional

try:
    from pathlib import Path
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=True)
except ImportError:
    pass

from fastapi import Depends, FastAPI, UploadFile, File, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

try:
    from backend import database
    from backend.excel_service import parse_petty_cash_file, recalculate_summary, generate_styled_excel, generate_drilldown_excel
    from backend.database import (
        init_db, list_sessions, create_session, get_session, update_session,
        rename_session, delete_session, list_project_categories,
        add_project_category, add_project_categories,
    )
    from backend.auth_service import (
        authenticate_user,
        create_onboarding_token,
        create_session as create_auth_session,
        get_authenticated_user,
        revoke_session,
        set_password_with_token,
    )
    from backend.notification_service import (
        get_preferences,
        list_notifications,
        mark_notification_read,
        mark_notification_unread,
        mark_all_notifications_read,
        update_preferences,
        send_email,
    )
    from backend.user_service import (
        create_assignment,
        create_bootstrap_admin,
        delete_user,
        list_assignments,
        list_users,
        provision_user,
        review_assignment,
    )
    from backend.request_service import (
        create_draft,
        get_request,
        list_requests,
        manager_decision,
        submit_request,
        update_draft,
    )
    from backend.posting_service import post_request, return_for_correction
    from backend.supporting_service import (
        get_supporting_file,
        list_supporting_files,
        upload_supporting_file,
    )
    from backend.receipt_service import create_company_receipt, list_company_receipts
    from backend.domain_repository import (
        create_cash_account,
        create_master_record,
        list_cash_accounts,
        list_master_records,
        set_master_record_active,
        delete_master_record,
    )
    from backend.audit_service import list_audit_events, get_audit_event, record_audit_event
    from backend.financial_control_service import (
        create_financial_period,
        close_financial_period,
        reopen_financial_period,
        list_financial_periods,
        reverse_posted_request,
        reverse_company_receipt,
        create_balance_adjustment,
        list_adjustments,
    )
    from backend.legacy_ledger_service import (
        import_session_to_legacy,
        create_legacy_session,
        list_legacy_sessions,
        get_legacy_session,
        update_legacy_session,
        delete_legacy_session,
    )
    from backend.report_service import (
        get_monthly_report_data,
        generate_monthly_excel,
        generate_monthly_zip_bundle,
        generate_legacy_12col_excel,
    )
    from backend.observability import (
        CorrelationIdMiddleware,
        RateLimitMiddleware,
        setup_observability,
        global_error_tracker,
        global_metrics_collector,
        get_correlation_id,
    )
    from backend.operations_service import (
        get_liveness,
        get_readiness,
        get_business_metrics,
        create_database_backup,
        list_backups,
        verify_database_backup,
        restore_database_backup,
        execute_deployment_rollback,
        evaluate_alert_rules,
        simulate_alert_scenario,
        acknowledge_alert,
    )
except ImportError:
    import database
    from excel_service import parse_petty_cash_file, recalculate_summary, generate_styled_excel, generate_drilldown_excel
    from database import (
        init_db, list_sessions, create_session, get_session, update_session,
        rename_session, delete_session, list_project_categories,
        add_project_category, add_project_categories,
    )
    from auth_service import (
        authenticate_user,
        create_session as create_auth_session,
        get_authenticated_user,
        revoke_session,
        set_password_with_token,
    )
    from notification_service import (
        get_preferences,
        list_notifications,
        mark_notification_read,
        mark_notification_unread,
        mark_all_notifications_read,
        update_preferences,
        send_email,
    )
    from user_service import (
        create_assignment,
        create_bootstrap_admin,
        delete_user,
        list_assignments,
        list_users,
        provision_user,
        review_assignment,
    )
    from request_service import (
        create_draft,
        get_request,
        list_requests,
        manager_decision,
        submit_request,
        update_draft,
    )
    from posting_service import post_request, return_for_correction
    from supporting_service import (
        get_supporting_file,
        list_supporting_files,
        upload_supporting_file,
    )
    from receipt_service import create_company_receipt, list_company_receipts
    from domain_repository import (
        create_cash_account,
        create_master_record,
        list_cash_accounts,
        list_master_records,
        set_master_record_active,
        delete_master_record,
    )
    from audit_service import list_audit_events, get_audit_event, record_audit_event
    from financial_control_service import (
        create_financial_period,
        close_financial_period,
        reopen_financial_period,
        list_financial_periods,
        reverse_posted_request,
        reverse_company_receipt,
        create_balance_adjustment,
        list_adjustments,
    )
    from legacy_ledger_service import (
        import_session_to_legacy,
        create_legacy_session,
        list_legacy_sessions,
        get_legacy_session,
        update_legacy_session,
        delete_legacy_session,
    )
    from report_service import (
        get_monthly_report_data,
        generate_monthly_excel,
        generate_monthly_zip_bundle,
        generate_legacy_12col_excel,
    )
    from observability import (
        CorrelationIdMiddleware,
        RateLimitMiddleware,
        setup_observability,
        global_error_tracker,
        global_metrics_collector,
        get_correlation_id,
    )
    from operations_service import (
        get_liveness,
        get_readiness,
        get_business_metrics,
        create_database_backup,
        list_backups,
        verify_database_backup,
        restore_database_backup,
        execute_deployment_rollback,
        evaluate_alert_rules,
        simulate_alert_scenario,
        acknowledge_alert,
    )

OPENAPI_TAGS = [
    {
        "name": "Health Probes",
        "description": "Liveness and readiness probes for orchestrators and infrastructure health checks.",
    },
    {
        "name": "Operations & Observability",
        "description": "Operational management, metrics aggregation, error tracking, database backups, and alerting.",
    },
    {
        "name": "Authentication",
        "description": "Bootstrap administrative user, login, session token authentication, and password updates.",
    },
    {
        "name": "Users & Assignments",
        "description": "User provisioning, role assignment, and manager-to-employee review hierarchy.",
    },
    {
        "name": "Notification Preferences",
        "description": "In-app and email alert preferences per user.",
    },
    {
        "name": "Projects, Ledgers & Categories",
        "description": "Master financial catalog: projects, ledger heads, and expenditure categories.",
    },
    {
        "name": "Cash Balance & Accounts",
        "description": "Petty cash vault balance and reserve threshold management.",
    },
    {
        "name": "Company Receipts",
        "description": "Direct entry of company cash infusions and top-ups.",
    },
    {
        "name": "Requests & Approvals",
        "description": "Petty cash disbursement requests, submissions, and manager approvals.",
    },
    {
        "name": "Supporting Files",
        "description": "Receipts and vouchers storage, validation, and retrieval.",
    },
    {
        "name": "Posting & Accounting",
        "description": "Finance posting to official ledger and return-for-correction flows.",
    },
    {
        "name": "Financial Controls & Periods",
        "description": "Accounting period closure, adjustments, and audited two-way reversals.",
    },
    {
        "name": "Audit Events",
        "description": "Append-only, immutable audit trail for governance and compliance.",
    },
    {
        "name": "Reports & Exports",
        "description": "12-column standardized monthly reports, Excel workbooks, and ZIP evidence bundles.",
    },
    {
        "name": "Legacy Ledger",
        "description": "Isolated compatibility workspace for importing legacy sheets.",
    },
    {
        "name": "Spreadsheet Sessions",
        "description": "Direct spreadsheet upload, interactive session recalculation, and legacy exports.",
    },
]

app = FastAPI(
    title="Petty Cash Management API",
    version="1.0.0",
    description="Enterprise-grade Petty Cash Management System API with strict financial controls, automated workflows, and production observability.",
    openapi_tags=OPENAPI_TAGS,
)

# Initialize structured logging
setup_observability(os.getenv("LOG_LEVEL", "INFO"))

# Initialize SQLite DB on startup
init_db()

# Correlation ID, request tracing, and rate limiting middleware
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RateLimitMiddleware)

# Enable CORS for local development and deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000"
    ).split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)

DEFAULT_EXCEL_FILENAME = "RTEAM -Petty Cash Sheet -  01.10.2026-06.11.2026.xlsx"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXCEL_PATH = os.path.join(BASE_DIR, DEFAULT_EXCEL_FILENAME)
auth_scheme = HTTPBearer(auto_error=False)


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


class BootstrapAdminRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SetPasswordRequest(BaseModel):
    token: str
    password: str


class ProvisionUserRequest(BaseModel):
    username: str
    email: str
    role: str


class AssignmentRequest(BaseModel):
    manager_id: str
    employee_id: str


class AssignmentReviewRequest(BaseModel):
    decision: str
    reason: Optional[str] = None


class NotificationPreferencesRequest(BaseModel):
    in_app_enabled: bool
    email_enabled: bool


class PettyCashRequestCreate(BaseModel):
    project_id: str
    ledger_id: str
    category: str
    request_date: str
    amount: float
    purpose: str
    notes: Optional[str] = None
    approving_manager_id: str


class PettyCashRequestUpdate(BaseModel):
    project_id: Optional[str] = None
    ledger_id: Optional[str] = None
    category: Optional[str] = None
    request_date: Optional[str] = None
    amount: Optional[float] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None
    approving_manager_id: Optional[str] = None


class RequestDecision(BaseModel):
    reason: Optional[str] = None


class PostingRequest(BaseModel):
    effective_date: str


class MasterDataRequest(BaseModel):
    name: str


class MasterDataStatusRequest(BaseModel):
    is_active: bool


class CashAccountRequest(BaseModel):
    opening_balance: float


class CompanyReceiptRequest(BaseModel):
    amount: float
    receipt_date: Optional[str] = None
    date: Optional[str] = None
    description: str
    ledger_id: Optional[str] = None
    category: Optional[str] = None
    project_id: Optional[str] = None


class FinancialPeriodCreate(BaseModel):
    period_start: str
    period_end: str


class ReversalRequest(BaseModel):
    reason: str
    effective_date: Optional[str] = None


class BalanceAdjustmentRequest(BaseModel):
    amount: float
    effective_date: str
    reason: str
    direction: str = "INFLOW"
    cash_account_id: Optional[str] = "system-main-cash"


class LegacySessionUpdateRequest(BaseModel):
    transactions: list
    opening_balance: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    name: Optional[str] = None


class BackupVerifyRequest(BaseModel):
    backup_id: str = Field(..., description="Backup filename or relative path to verify")


class BackupRestoreRequest(BaseModel):
    backup_id: str = Field(..., description="Backup filename or relative path to restore from")
    target_db_path: Optional[str] = Field(None, description="Optional target database path")


class DeploymentRollbackRequest(BaseModel):
    target_version: str = Field(..., description="Target release version to roll back to")
    backup_id: Optional[str] = Field(None, description="Optional specific backup ID to restore")


class AlertTestRequest(BaseModel):
    scenario: str = Field(
        ...,
        description="Scenario to simulate: queue_backlog, failed_postings, auth_failures, anomalous_balance, backup_failures",
    )


class AlertAcknowledgeRequest(BaseModel):
    rule_id: str = Field(..., description="Alert rule identifier to acknowledge")


from fastapi.openapi.utils import get_openapi


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="Petty Cash Management API",
        version="1.0.0",
        description="Enterprise-grade Petty Cash Management System API with strict financial controls, automated workflows, and production observability.",
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    schema["components"] = schema.get("components", {})
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Token",
            "description": "Session Bearer token obtained from `/api/auth/login`.",
        }
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


def current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> dict:
    raw_token = None
    if credentials:
        raw_token = credentials.credentials
    if not raw_token:
        raw_token = request.query_params.get("token") or request.query_params.get("auth_token")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    user = get_authenticated_user(raw_token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")
    return {**user, "_token": raw_token}


def optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> Optional[dict]:
    raw_token = None
    if credentials:
        raw_token = credentials.credentials
    if not raw_token:
        raw_token = request.query_params.get("token") or request.query_params.get("auth_token")
    if not raw_token:
        return None
    user = get_authenticated_user(raw_token)
    if not user:
        return None
    return {**user, "_token": raw_token}


def require_roles(*roles: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            record_audit_event(
                actor_user_id=user["id"],
                action="AUTH_ACCESS_DENIED",
                entity_type="rbac",
                after={"required_roles": list(roles), "user_role": user["role"]},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return user

    return dependency


# ─── Authentication, Users, Assignments, Notifications ─────────────────────

@app.get("/api/auth/bootstrap-status", tags=["Authentication"], summary="Check if initial admin bootstrap is required")
def check_bootstrap_status():
    marker = database._placeholder()
    with database.get_connection() as connection:
        admin_row = connection.execute(
            f"""
            SELECT u.id FROM users u
            JOIN roles r ON r.id=u.role_id
            WHERE r.name={marker} AND u.is_active=1
            """,
            ("Admin",),
        ).fetchone()
    return {"admin_exists": bool(admin_row)}


@app.post("/api/auth/bootstrap", tags=["Authentication"], summary="Create bootstrap administrator")
def bootstrap_admin(req: BootstrapAdminRequest):
    try:
        return create_bootstrap_admin(req.username, req.email, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login", tags=["Authentication"], summary="User login")
def login(req: LoginRequest):
    user = authenticate_user(req.email, req.password)
    if not user:
        record_audit_event(
            actor_user_id=None,
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            after={"email": req.email},
        )
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_auth_session(user["id"])
    user.pop("is_active", None)
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/api/auth/set-password", tags=["Authentication"], summary="Set user password")
def set_password(req: SetPasswordRequest):
    try:
        return set_password_with_token(req.token, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/logout", tags=["Authentication"], summary="User logout")
def logout(user: dict = Depends(current_user)):
    revoke_session(user["_token"])
    return {"logged_out": True}


@app.get("/api/auth/me", tags=["Authentication"], summary="Get authenticated profile")
def auth_me(user: dict = Depends(current_user)):
    user.pop("_token", None)
    return user


@app.post("/api/users", tags=["Users & Assignments"], summary="Provision new user (Admin)")
def create_user(
    req: ProvisionUserRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        smtp_values = {
            "host": os.getenv("SMTP_HOST", ""),
            "port": int(os.getenv("SMTP_PORT", "587")),
            "username": os.getenv("SMTP_USERNAME", ""),
            "password": os.getenv("SMTP_PASSWORD", ""),
            "sender": os.getenv("SMTP_SENDER", ""),
        }
        smtp_configured = all(
            (
                smtp_values["host"],
                smtp_values["username"],
                smtp_values["password"],
                smtp_values["sender"],
            )
        )
        if os.getenv("APP_ENV", "development") == "production" and not smtp_configured:
            raise HTTPException(status_code=503, detail="SMTP is required to provision users in production.")

        user, onboarding_token = provision_user(
            req.username, req.email, req.role, admin["id"]
        )
        if smtp_configured:
            def _async_send_onboarding():
                try:
                    send_email(
                        user["email"],
                        "PettyCash account setup",
                        f"Use this one-time setup token to set your password: {onboarding_token}",
                        **smtp_values,
                    )
                except Exception as send_err:
                    import logging
                    logging.getLogger("petty_cash.app").warning(f"Failed to dispatch onboarding email: {send_err}")

            threading.Thread(target=_async_send_onboarding, daemon=True).start()

        # Always return onboarding_token so Admin can view/share it directly
        return {**user, "onboarding_token": onboarding_token}
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/users", tags=["Users & Assignments"], summary="List users (Admin)")
def get_users(_: dict = Depends(require_roles("Admin"))):
    return list_users()


@app.post("/api/users/{user_id}/token", tags=["Users & Assignments"], summary="Generate setup token for user (Admin)")
def generate_user_token_endpoint(user_id: str, admin: dict = Depends(require_roles("Admin"))):
    try:
        token = create_onboarding_token(user_id)
        return {"user_id": user_id, "onboarding_token": token}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to generate token: {exc}") from exc


@app.delete("/api/users/{user_id}", tags=["Users & Assignments"], summary="Delete user (Admin)")
def delete_user_endpoint(user_id: str, admin: dict = Depends(require_roles("Admin"))):
    try:
        return delete_user(user_id, admin["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to delete user: {exc}") from exc


@app.post("/api/assignments", tags=["Users & Assignments"], summary="Create manager-employee assignment (Admin)")
def assign_employee(
    req: AssignmentRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return create_assignment(req.manager_id, req.employee_id, admin["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Assignment could not be created.") from exc


@app.get("/api/assignments", tags=["Users & Assignments"], summary="List manager assignments")
def get_assignments(user: dict = Depends(current_user)):
    return list_assignments(user["id"], user["role"])


@app.post("/api/assignments/{assignment_id}/review", tags=["Users & Assignments"], summary="Review manager assignment (Manager)")
def review_employee_assignment(
    assignment_id: str,
    req: AssignmentReviewRequest,
    manager: dict = Depends(require_roles("Manager")),
):
    try:
        return review_assignment(assignment_id, manager["id"], req.decision, req.reason)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/notifications", tags=["Notification Preferences"], summary="List user notifications")
def get_notifications(
    unread_only: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
    user: dict = Depends(current_user),
):
    return list_notifications(user["id"], unread_only, limit=limit, offset=offset)


@app.post("/api/notifications/{notification_id}/read", tags=["Notification Preferences"], summary="Mark notification as read")
def read_notification(notification_id: str, user: dict = Depends(current_user)):
    if not mark_notification_read(user["id"], notification_id):
        raise HTTPException(status_code=404, detail="Notification not found or already read.")
    return {"read": True}


@app.post("/api/notifications/{notification_id}/unread", tags=["Notification Preferences"], summary="Mark notification as unread")
def unread_notification(notification_id: str, user: dict = Depends(current_user)):
    if not mark_notification_unread(user["id"], notification_id):
        raise HTTPException(status_code=404, detail="Notification not found or already unread.")
    return {"read": False}


@app.post("/api/notifications/mark-all-read", tags=["Notification Preferences"], summary="Mark all notifications as read")
def mark_all_read(user: dict = Depends(current_user)):
    count = mark_all_notifications_read(user["id"])
    return {"marked_read": count}


@app.get("/api/notification-preferences")
def get_notification_preferences(user: dict = Depends(current_user)):
    return get_preferences(user["id"])


@app.put("/api/notification-preferences", tags=["Notification Preferences"], summary="Update notification preferences")
def put_notification_preferences(
    req: NotificationPreferencesRequest,
    user: dict = Depends(current_user),
):
    return update_preferences(user["id"], req.in_app_enabled, req.email_enabled)


# ─── Admin Master Data and Cash Accounts ─────────────────────────────────────

def _master_data_route(table: str):
    def list_records(_: dict = Depends(current_user)):
        return list_master_records(table)

    return list_records


@app.get("/api/projects", tags=["Projects, Ledgers & Categories"], summary="List projects")
def get_projects(user: dict = Depends(current_user)):
    return list_master_records("projects")


@app.post("/api/projects", tags=["Projects, Ledgers & Categories"], summary="Create project (Admin)")
def add_project(req: MasterDataRequest, admin: dict = Depends(require_roles("Admin"))):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")
    try:
        return create_master_record("projects", req.name, actor_id=admin["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Project could not be created.") from exc


@app.patch("/api/projects/{project_id}", tags=["Projects, Ledgers & Categories"], summary="Update project status (Admin)")
def set_project_status(
    project_id: str,
    req: MasterDataStatusRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    if not set_master_record_active("projects", project_id, req.is_active, actor_id=admin["id"]):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"id": project_id, "is_active": req.is_active}


@app.delete("/api/projects/{project_id}", tags=["Projects, Ledgers & Categories"], summary="Delete project (Admin)")
def api_delete_project(
    project_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return delete_master_record("projects", project_id, actor_id=admin["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ledgers", tags=["Projects, Ledgers & Categories"], summary="List ledgers")
def get_ledgers(_: dict = Depends(current_user)):
    return list_master_records("ledgers")


@app.post("/api/ledgers", tags=["Projects, Ledgers & Categories"], summary="Create ledger (Admin)")
def add_ledger(req: MasterDataRequest, admin: dict = Depends(require_roles("Admin"))):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Ledger name cannot be empty.")
    try:
        return create_master_record("ledgers", req.name, actor_id=admin["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Ledger could not be created.") from exc


@app.patch("/api/ledgers/{ledger_id}", tags=["Projects, Ledgers & Categories"], summary="Update ledger status (Admin)")
def set_ledger_status(
    ledger_id: str,
    req: MasterDataStatusRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    if not set_master_record_active("ledgers", ledger_id, req.is_active, actor_id=admin["id"]):
        raise HTTPException(status_code=404, detail="Ledger not found.")
    return {"id": ledger_id, "is_active": req.is_active}


@app.delete("/api/ledgers/{ledger_id}", tags=["Projects, Ledgers & Categories"], summary="Delete ledger (Admin)")
def api_delete_ledger(
    ledger_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return delete_master_record("ledgers", ledger_id, actor_id=admin["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cash-balance", tags=["Cash Balance & Accounts"], summary="Get petty cash balance")
def get_cash_balance(_: dict = Depends(current_user)):
    accounts = list_cash_accounts()
    account = next((item for item in accounts if item["id"] == "system-main-cash"), None)
    if not account:
        raise HTTPException(status_code=500, detail="Main petty cash balance is not configured.")
    return account


@app.put("/api/cash-balance", tags=["Cash Balance & Accounts"], summary="Update petty cash balance (Admin)")
def configure_cash_balance(
    req: CashAccountRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    if req.opening_balance < 0:
        raise HTTPException(status_code=400, detail="Outstanding balance cannot be negative.")
    marker = database._placeholder()
    try:
        with database.get_connection() as connection:
            timestamp = database.now_iso()
            connection.execute(
                f"""
                UPDATE cash_accounts
                SET opening_balance={marker}, updated_at={marker}
                WHERE id='system-main-cash'
                """,
                (str(req.opening_balance), timestamp),
            )
            connection.execute(
                f"""
                UPDATE cash_account_balances
                SET current_balance={marker}, version=version+1, updated_at={marker}
                WHERE cash_account_id='system-main-cash'
                """,
                (str(req.opening_balance), timestamp),
            )
            record_audit_event(
                connection=connection,
                actor_user_id=admin["id"],
                action="CASH_BALANCE_UPDATED",
                entity_type="cash_account",
                entity_id="system-main-cash",
                after={"opening_balance": str(req.opening_balance)},
            )
            connection.commit()
        return get_cash_balance()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Outstanding balance could not be configured.") from exc


@app.post("/api/company-receipts", tags=["Company Receipts"], summary="Create company receipt (Admin)")
def create_cash_receipt(
    req: CompanyReceiptRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    target_date = req.receipt_date or req.date
    if not target_date:
        raise HTTPException(status_code=400, detail="Receipt date is required.")
    try:
        return create_company_receipt(
            admin_id=admin["id"],
            amount=req.amount,
            receipt_date=target_date,
            description=req.description,
            ledger_id=req.ledger_id,
            category=req.category,
            project_id=req.project_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/company-receipts", tags=["Company Receipts"], summary="List company receipts (Admin)")
def get_cash_receipts(admin: dict = Depends(require_roles("Admin"))):
    return list_company_receipts(admin["id"])


# ─── Petty Cash Request Lifecycle ───────────────────────────────────────────

@app.post("/api/requests", tags=["Requests & Approvals"], summary="Create petty cash request draft (Employee)")
def create_petty_cash_request(
    req: PettyCashRequestCreate,
    employee: dict = Depends(require_roles("Employee")),
):
    try:
        return create_draft(
            employee["id"],
            req.project_id,
            req.ledger_id,
            req.category,
            req.request_date,
            req.amount,
            req.purpose,
            req.notes,
            req.approving_manager_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/requests", tags=["Requests & Approvals"], summary="List petty cash requests")
def get_petty_cash_requests(
    limit: Optional[int] = None,
    offset: int = 0,
    user: dict = Depends(current_user),
):
    return list_requests(user["id"], user["role"], limit=limit, offset=offset)


@app.get("/api/requests/{request_id}", tags=["Requests & Approvals"], summary="Get petty cash request details")
def get_petty_cash_request(request_id: str, user: dict = Depends(current_user)):
    try:
        request_data = get_request(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if user["role"] == "Employee" and request_data["requester_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You cannot access this request.")
    if user["role"] == "Manager" and request_data["approving_manager_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You cannot access this request.")
    return request_data


@app.post("/api/requests/{request_id}/supporting-files", tags=["Supporting Files"], summary="Upload supporting receipt file (Employee)")
async def upload_request_supporting_file(
    request_id: str,
    file: UploadFile = File(...),
    employee: dict = Depends(require_roles("Employee")),
):
    try:
        content = await file.read()
        return upload_supporting_file(
            request_id,
            employee["id"],
            file.filename or "",
            file.content_type or "",
            content,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/requests/{request_id}/supporting-files", tags=["Supporting Files"], summary="List supporting files for request")
def get_request_supporting_files(
    request_id: str,
    user: dict = Depends(current_user),
):
    try:
        request_data = get_request(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if user["role"] != "Admin" and request_data["requester_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You cannot access these supporting files.")
    return list_supporting_files(request_id)


@app.post("/api/requests/{request_id}/submit-for-posting", tags=["Requests & Approvals"], summary="Submit approved request with vouchers for admin posting (Employee)")
def api_submit_for_posting(
    request_id: str,
    employee: dict = Depends(require_roles("Employee")),
):
    marker = database._placeholder()
    with database.get_connection() as connection:
        req_row = connection.execute(
            f"SELECT * FROM petty_cash_requests WHERE id={marker}",
            (request_id,),
        ).fetchone()
        if not req_row:
            raise HTTPException(status_code=404, detail="Request not found.")
        if req_row["requester_id"] != employee["id"]:
            raise HTTPException(status_code=403, detail="Only the requester can submit this request for posting.")
        if req_row["status"] not in {"APPROVED", "SUPPORTING_UPLOADED"}:
            raise HTTPException(status_code=400, detail="Only approved requests can be submitted for posting.")
        files = connection.execute(
            f"SELECT COUNT(*) FROM supporting_files WHERE request_id={marker}",
            (request_id,),
        ).fetchone()[0]
        if files == 0:
            raise HTTPException(status_code=400, detail="Please upload at least one supporting receipt/voucher before submitting for posting.")

        timestamp = database.now_iso()
        connection.execute(
            f"UPDATE petty_cash_requests SET status='SUPPORTING_UPLOADED', updated_at={marker} WHERE id={marker}",
            (timestamp, request_id),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=employee["id"],
            action="PETTY_CASH_REQUEST_SUBMITTED_FOR_POSTING",
            entity_type="petty_cash_request",
            entity_id=request_id,
            after={"status": "SUPPORTING_UPLOADED"},
        )
        admins = connection.execute(
            "SELECT u.id FROM users u JOIN roles r ON r.id=u.role_id WHERE r.name='Admin' AND u.is_active=1"
        ).fetchall()
        connection.commit()

    amt_str = f"₹{Decimal(str(req_row['amount'])).quantize(Decimal('0.01'))}"
    purpose_str = req_row["purpose"] or "Petty cash expense"
    for adm in admins:
        create_notification(
            adm["id"],
            "REQUEST_READY_FOR_POSTING",
            f"Voucher submitted by {employee['username']}",
            f"Request for {amt_str} ({purpose_str}) by {employee['username']} has vouchers attached and is ready for posting.",
            "petty_cash_request",
            request_id,
        )
    return get_request(request_id)


@app.get("/api/supporting-files/{file_id}", tags=["Supporting Files"], summary="Download supporting receipt file")
@app.get("/api/supporting-files/{file_id}/download", tags=["Supporting Files"], summary="Download supporting receipt file")
def download_supporting_file(
    file_id: str,
    user: Optional[dict] = Depends(optional_current_user),
):
    user_id = user["id"] if user else None
    role = user["role"] if user else None
    try:
        metadata, path = get_supporting_file(file_id, user_id, role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=metadata["content_type"],
        filename=metadata["original_filename"],
        content_disposition_type="inline",
    )


@app.post("/api/requests/{request_id}/post", tags=["Posting & Accounting"], summary="Post request to official ledger (Admin)")
def post_petty_cash_request(
    request_id: str,
    req: PostingRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return post_request(request_id, admin["id"], req.effective_date)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/return-for-correction", tags=["Posting & Accounting"], summary="Return request for correction (Admin)")
def return_petty_cash_request_for_correction(
    request_id: str,
    req: RequestDecision,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return return_for_correction(request_id, admin["id"], req.reason or "")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/requests/{request_id}", tags=["Requests & Approvals"], summary="Update petty cash draft (Employee)")
def edit_petty_cash_request(
    request_id: str,
    req: PettyCashRequestUpdate,
    employee: dict = Depends(require_roles("Employee")),
):
    values = {key: value for key, value in req.model_dump().items() if value is not None}
    try:
        return update_draft(request_id, employee["id"], values)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/submit", tags=["Requests & Approvals"], summary="Submit draft for manager approval (Employee)")
def submit_petty_cash_request(
    request_id: str,
    employee: dict = Depends(require_roles("Employee")),
):
    try:
        return submit_request(request_id, employee["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/approve", tags=["Requests & Approvals"], summary="Approve petty cash request (Manager)")
def approve_petty_cash_request(
    request_id: str,
    manager: dict = Depends(require_roles("Manager")),
):
    try:
        return manager_decision(request_id, manager["id"], "APPROVED", None)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/request-changes", tags=["Requests & Approvals"], summary="Request changes on request (Manager)")
def request_petty_cash_changes(
    request_id: str,
    req: RequestDecision,
    manager: dict = Depends(require_roles("Manager")),
):
    try:
        return manager_decision(request_id, manager["id"], "DRAFT", req.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/reject", tags=["Requests & Approvals"], summary="Reject petty cash request (Manager)")
def reject_petty_cash_request(
    request_id: str,
    req: RequestDecision,
    manager: dict = Depends(require_roles("Manager")),
):
    try:
        return manager_decision(request_id, manager["id"], "REJECTED", req.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ─── Phase 7: Financial Controls, Reversals, Adjustments, Periods & Legacy Ledger ───

@app.get("/api/audit-events", tags=["Audit Events"], summary="List immutable audit trail events (Admin)")
def api_list_audit_events(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: dict = Depends(require_roles("Admin")),
):
    return list_audit_events(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )


@app.get("/api/audit-events/{event_id}", tags=["Audit Events"], summary="Get single audit event details (Admin)")
def api_get_audit_event(
    event_id: str,
    _: dict = Depends(require_roles("Admin")),
):
    event = get_audit_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Audit event not found.")
    return event


@app.post("/api/financial-periods", tags=["Financial Controls & Periods"], summary="Create financial period (Admin)")
def api_create_financial_period(
    req: FinancialPeriodCreate,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return create_financial_period(admin["id"], req.period_start, req.period_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/financial-periods", tags=["Financial Controls & Periods"], summary="List financial periods (Admin)")
def api_list_financial_periods(
    _: dict = Depends(require_roles("Admin")),
):
    return list_financial_periods()


@app.post("/api/financial-periods/{period_id}/close", tags=["Financial Controls & Periods"], summary="Close financial period (Admin)")
def api_close_financial_period(
    period_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return close_financial_period(period_id, admin["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/financial-periods/{period_id}/reopen", tags=["Financial Controls & Periods"], summary="Reopen financial period (Admin)")
def api_reopen_financial_period(
    period_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return reopen_financial_period(period_id, admin["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/reverse", tags=["Financial Controls & Periods"], summary="Reverse posted request (Admin)")
def api_reverse_petty_cash_request(
    request_id: str,
    req: ReversalRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return reverse_posted_request(request_id, admin["id"], req.reason, req.effective_date)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/company-receipts/{receipt_id}/reverse", tags=["Financial Controls & Periods"], summary="Reverse company receipt (Admin)")
def api_reverse_company_receipt(
    receipt_id: str,
    req: ReversalRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return reverse_company_receipt(receipt_id, admin["id"], req.reason, req.effective_date)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/cash-adjustments", tags=["Financial Controls & Periods"], summary="Create manual balance adjustment (Admin)")
def api_create_cash_adjustment(
    req: BalanceAdjustmentRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return create_balance_adjustment(
            admin_id=admin["id"],
            amount=req.amount,
            effective_date=req.effective_date,
            reason=req.reason,
            direction=req.direction,
            cash_account_id=req.cash_account_id or "system-main-cash",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cash-adjustments", tags=["Financial Controls & Periods"], summary="List manual balance adjustments (Admin)")
def api_list_cash_adjustments(
    cash_account_id: str = "system-main-cash",
    _: dict = Depends(require_roles("Admin")),
):
    return list_adjustments(cash_account_id=cash_account_id)


@app.post("/api/legacy-ledger/import-session/{session_id}", tags=["Legacy Ledger"], summary="Import session to isolated legacy ledger (Admin)")
def api_import_session_to_legacy(
    session_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return import_session_to_legacy(admin["id"], session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/legacy-ledger/sessions", tags=["Legacy Ledger"], summary="List legacy ledger sessions (Admin)")
def api_list_legacy_sessions(
    admin: dict = Depends(require_roles("Admin")),
):
    return list_legacy_sessions(admin["id"])


@app.get("/api/legacy-ledger/sessions/{session_id}", tags=["Legacy Ledger"], summary="Get legacy ledger session (Admin)")
def api_get_legacy_session(
    session_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return get_legacy_session(session_id, admin["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/legacy-ledger/sessions/{session_id}", tags=["Legacy Ledger"], summary="Update legacy ledger session (Admin)")
def api_update_legacy_session(
    session_id: str,
    req: LegacySessionUpdateRequest,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        return update_legacy_session(
            session_id=session_id,
            admin_id=admin["id"],
            transactions=req.transactions,
            opening_balance=req.opening_balance,
            start_date=req.start_date,
            end_date=req.end_date,
            name=req.name,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/legacy-ledger/sessions/{session_id}", tags=["Legacy Ledger"], summary="Delete legacy ledger session (Admin)")
def api_delete_legacy_session(
    session_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    try:
        delete_legacy_session(session_id, admin["id"])
        return {"deleted": True}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─── Phase 8: Reporting & Standardized 12-Column Exports ──────────────────────

@app.get("/api/reports/monthly", tags=["Reports & Exports"], summary="Get monthly report data")
def api_get_monthly_report(
    month: Optional[str] = None,
    user: dict = Depends(current_user),
):
    """Monthly report showing posted totals, daily movement, breakdowns, and unposted requests."""
    selected_month = month or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    try:
        return get_monthly_report_data(selected_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reports/monthly/excel", tags=["Reports & Exports"], summary="Export monthly report as multi-sheet Excel")
def api_export_monthly_excel(
    request: Request,
    month: Optional[str] = None,
    user: dict = Depends(current_user),
):
    """Export monthly report to an Excel workbook using the standardized 12-column schema."""
    selected_month = month or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    try:
        report_data = get_monthly_report_data(selected_month)
        base_url = str(request.base_url)
        buf = generate_monthly_excel(report_data, web_base_url=base_url)
        filename = f"Petty_Cash_Report_{selected_month.replace('-', '_')}.xlsx"
        record_audit_event(
            actor_user_id=user["id"],
            action="MONTHLY_EXCEL_EXPORTED",
            entity_type="monthly_report",
            entity_id=selected_month,
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reports/monthly/zip", tags=["Reports & Exports"], summary="Export monthly report bundle as ZIP (Admin)")
def api_export_monthly_zip(
    month: Optional[str] = None,
    admin: dict = Depends(require_roles("Admin")),
):
    """Export monthly ZIP package containing 12-column workbook with relative links, offline evidence viewer, and all supporting files."""
    selected_month = month or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    try:
        zip_buf = generate_monthly_zip_bundle(selected_month)
        filename = f"Petty_Cash_Bundle_{selected_month.replace('-', '_')}.zip"
        record_audit_event(
            actor_user_id=admin["id"],
            action="MONTHLY_ZIP_BUNDLE_EXPORTED",
            entity_type="monthly_report",
            entity_id=selected_month,
        )
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/legacy-ledger/sessions/{session_id}/export", tags=["Legacy Ledger"], summary="Export legacy session as 12-column Excel (Admin)")
def api_export_legacy_session(
    session_id: str,
    admin: dict = Depends(require_roles("Admin")),
):
    """Export an isolated legacy session into the standardized 12-column Excel schema."""
    try:
        session_data = get_legacy_session(session_id, admin["id"])
        buf = generate_legacy_12col_excel(session_data)
        clean_name = re.sub(r"[^A-Za-z0-9_ -]", "_", session_data.get("name", "Legacy_Session")).strip()
        filename = f"{clean_name}_12col.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─── Health Probes ───────────────────────────────────────────────────────────

@app.get(
    "/health/live",
    tags=["Health Probes"],
    summary="Liveness probe",
    description="Verifies that the API service process is running and responsive.",
)
@app.get(
    "/api/health/live",
    tags=["Health Probes"],
    summary="Liveness probe",
    description="Verifies that the API service process is running and responsive.",
)
def liveness_probe():
    return get_liveness()


@app.get(
    "/health/ready",
    tags=["Health Probes"],
    summary="Readiness probe",
    description="Verifies that database and file storage subsystems are fully operational. Returns 503 if any check fails.",
)
@app.get(
    "/api/health/ready",
    tags=["Health Probes"],
    summary="Readiness probe",
    description="Verifies that database and file storage subsystems are fully operational. Returns 503 if any check fails.",
)
def readiness_probe(response: Response):
    is_ready, details = get_readiness()
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return details


@app.get(
    "/api/health",
    tags=["Health Probes"],
    summary="Legacy health check",
    description="Backward-compatible health check ping.",
)
def health_check():
    return {"status": "ok", "app": "Petty Cash Management API"}


# ─── Operations & Observability ──────────────────────────────────────────────

@app.get(
    "/api/operations/metrics",
    tags=["Operations & Observability"],
    summary="Get API and business metrics (Admin)",
    description="Retrieves API latency/status counts and domain business performance indicators.",
)
def get_metrics(admin: dict = Depends(require_roles("Admin"))):
    return {
        "api_metrics": global_metrics_collector.get_api_metrics(),
        "business_metrics": get_business_metrics(),
        "timestamp": database.now_iso(),
    }


@app.get(
    "/api/operations/errors",
    tags=["Operations & Observability"],
    summary="Get recent production errors (Admin)",
    description="Returns recent exceptions captured by the in-memory ring buffer for post-mortem debugging.",
)
def get_recent_errors(limit: int = 50, admin: dict = Depends(require_roles("Admin"))):
    errors = global_error_tracker.get_errors(limit=limit)
    return {"count": len(errors), "errors": errors}


@app.post(
    "/api/operations/backups/create",
    tags=["Operations & Observability"],
    summary="Create online database backup (Admin)",
    description="Performs an online, non-blocking ACID database snapshot with SHA256 checksum verification.",
)
def trigger_backup(admin: dict = Depends(require_roles("Admin"))):
    try:
        backup = create_database_backup()
        record_audit_event(
            actor_user_id=admin["id"],
            action="DATABASE_BACKUP_CREATED",
            entity_type="backup",
            entity_id=backup["backup_id"],
            after=backup,
        )
        return backup
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database backup failed: {str(exc)}") from exc


@app.get(
    "/api/operations/backups",
    tags=["Operations & Observability"],
    summary="List database backups (Admin)",
    description="Lists all database backups with metadata and verification status.",
)
def get_backups(admin: dict = Depends(require_roles("Admin"))):
    return list_backups()


@app.post(
    "/api/operations/backups/verify",
    tags=["Operations & Observability"],
    summary="Verify database backup integrity (Admin)",
    description="Executes PRAGMA integrity check and verifies core tables on the specified backup.",
)
def verify_backup(req: BackupVerifyRequest, admin: dict = Depends(require_roles("Admin"))):
    result = verify_database_backup(req.backup_id)
    record_audit_event(
        actor_user_id=admin["id"],
        action="DATABASE_BACKUP_VERIFIED",
        entity_type="backup",
        entity_id=req.backup_id,
        after=result,
    )
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result)
    return result


@app.post(
    "/api/operations/backups/restore",
    tags=["Operations & Observability"],
    summary="Restore database from backup (Admin)",
    description="Performs an ACID database restoration from a verified snapshot.",
)
def restore_backup(req: BackupRestoreRequest, admin: dict = Depends(require_roles("Admin"))):
    try:
        result = restore_database_backup(req.backup_id, req.target_db_path)
        record_audit_event(
            actor_user_id=admin["id"],
            action="DATABASE_BACKUP_RESTORED",
            entity_type="backup",
            entity_id=req.backup_id,
            after=result,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database restore failed: {str(exc)}") from exc


@app.post(
    "/api/operations/rollback",
    tags=["Operations & Observability"],
    summary="Execute deployment rollback (Admin)",
    description="Executes a controlled deployment rollback restoring verified database state and recording release audit event.",
)
def deployment_rollback(req: DeploymentRollbackRequest, admin: dict = Depends(require_roles("Admin"))):
    try:
        result = execute_deployment_rollback(req.target_version, req.backup_id)
        record_audit_event(
            actor_user_id=admin["id"],
            action="DEPLOYMENT_ROLLBACK_EXECUTED",
            entity_type="release",
            entity_id=req.target_version,
            after=result,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(exc)}") from exc


@app.get(
    "/api/operations/alerts",
    tags=["Operations & Observability"],
    summary="Evaluate production alert rules (Admin)",
    description="Evaluates alert rules for queue backlog, failed postings, auth failures, balance anomalies, and backup freshness.",
)
def get_alerts(admin: dict = Depends(require_roles("Admin"))):
    return evaluate_alert_rules()


@app.post(
    "/api/operations/alerts/test",
    tags=["Operations & Observability"],
    summary="Simulate alert rule for testing (Admin)",
    description="Simulates an alerting condition (queue_backlog, failed_postings, auth_failures, anomalous_balance, backup_failures) for verification.",
)
def test_alert(req: AlertTestRequest, admin: dict = Depends(require_roles("Admin"))):
    try:
        return simulate_alert_scenario(req.scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/operations/alerts/acknowledge",
    tags=["Operations & Observability"],
    summary="Acknowledge alert rule (Admin)",
    description="Acknowledges a firing alert rule, clearing it and recording an ALERT_ACKNOWLEDGED event in the audit trail.",
)
def acknowledge_alert_endpoint(req: AlertAcknowledgeRequest, admin: dict = Depends(require_roles("Admin"))):
    try:
        return acknowledge_alert(req.rule_id, admin["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ─── Default Data ────────────────────────────────────────────────────────────

@app.get("/api/default-data", tags=["Spreadsheet Sessions"], summary="Load default spreadsheet data")
def get_default_data():
    if not os.path.exists(DEFAULT_EXCEL_PATH):
        raise HTTPException(status_code=404, detail="Default Excel file not found.")
    try:
        data = parse_petty_cash_file(DEFAULT_EXCEL_PATH)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse default file: {str(e)}")


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.post("/api/upload", tags=["Spreadsheet Sessions"], summary="Upload Excel spreadsheet")
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

@app.post("/api/recalculate", tags=["Spreadsheet Sessions"], summary="Recalculate summary metrics")
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

@app.get("/api/sessions", tags=["Spreadsheet Sessions"], summary="List spreadsheet sessions")
def api_list_sessions():
    """Return all sessions (metadata only, no transaction blobs)."""
    return list_sessions()


@app.get("/api/project-categories", tags=["Spreadsheet Sessions"], summary="List session categories")
def api_list_project_categories():
    return list_project_categories()


class ProjectCategoryRequest(BaseModel):
    name: str


@app.post("/api/project-categories", tags=["Spreadsheet Sessions"], summary="Add session category")
def api_add_project_category(req: ProjectCategoryRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")
    return {"name": add_project_category(name)}


@app.post("/api/sessions", tags=["Spreadsheet Sessions"], summary="Save spreadsheet session")
def api_create_session(req: SaveSessionRequest):
    """Create a new saved session from current state."""
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        add_project_categories([tx.get("project", "") for tx in tx_dicts])
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


@app.get("/api/sessions/{session_id}", tags=["Spreadsheet Sessions"], summary="Get spreadsheet session")
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


@app.put("/api/sessions/{session_id}", tags=["Spreadsheet Sessions"], summary="Update spreadsheet session")
def api_update_session(session_id: str, req: SaveSessionRequest):
    """Save/overwrite an existing session with new state."""
    existing = get_session(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        tx_dicts = [tx.model_dump() for tx in req.transactions]
        add_project_categories([tx.get("project", "") for tx in tx_dicts])
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


@app.patch("/api/sessions/{session_id}/rename", tags=["Spreadsheet Sessions"], summary="Rename spreadsheet session")
def api_rename_session(session_id: str, req: RenameSessionRequest):
    """Rename a session without changing its data."""
    existing = get_session(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found.")
    session = rename_session(session_id, req.name)
    return {"id": session["id"], "name": session["name"], "updated_at": session["updated_at"]}


@app.delete("/api/sessions/{session_id}", tags=["Spreadsheet Sessions"], summary="Delete spreadsheet session")
def api_delete_session(session_id: str):
    """Permanently delete a session."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"deleted": True}


# ─── Drilldown Export ─────────────────────────────────────────────────────────

@app.post("/api/export-drilldown", tags=["Spreadsheet Sessions"], summary="Export drilldown Excel")
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

@app.post("/api/export", tags=["Spreadsheet Sessions"], summary="Export styled Excel")
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
