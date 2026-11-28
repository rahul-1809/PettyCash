import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.main import app
from backend.auth_service import create_session as create_auth_session
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    provision_user,
    review_assignment,
)
from backend.observability import (
    JSONLogFormatter,
    redact_sensitive_data,
    get_correlation_id,
    set_correlation_id,
    global_error_tracker,
    global_metrics_collector,
)
from backend.operations_service import (
    check_database_health,
    check_storage_health,
    create_database_backup,
    evaluate_alert_rules,
    get_backup_dir,
    get_business_metrics,
    get_liveness,
    get_readiness,
    list_backups,
    simulate_alert_scenario,
    verify_database_backup,
)
from backend.domain_repository import create_master_record
from backend.request_service import create_draft, submit_request
from backend.audit_service import list_audit_events


class Phase9Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase9.sqlite")
        database.DATABASE_URL = None
        database.init_db()

        # Set backup directory inside temp dir
        self.backup_dir = Path(self.temp_dir.name) / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        os.environ["BACKUP_DIR"] = str(self.backup_dir)

        # Create director, finance, manager, employee
        self.admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        self.admin_token = create_auth_session(self.admin["id"])

        self.finance, _ = provision_user("finance", "finance@example.com", "Finance", self.admin["id"])
        self.finance_token = create_auth_session(self.finance["id"])

        self.manager, _ = provision_user("manager", "manager@example.com", "Manager", self.admin["id"])
        self.manager_token = create_auth_session(self.manager["id"])

        self.employee, _ = provision_user("employee", "employee@example.com", "Employee", self.admin["id"])
        self.employee_token = create_auth_session(self.employee["id"])

        assignment = create_assignment(self.manager["id"], self.employee["id"], self.admin["id"])
        review_assignment(assignment["id"], self.manager["id"], "APPROVED")

        self.client = TestClient(app)
        global_error_tracker.clear()
        global_metrics_collector.reset()

    def tearDown(self):
        self.temp_dir.cleanup()
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url

    def test_01_openapi_schema_and_swagger_ui(self):
        """Acceptance Criteria: Swagger UI is available; every production API route has an OpenAPI definition."""
        # 1. Fetch openapi.json
        res = self.client.get("/openapi.json")
        self.assertEqual(res.status_code, 200)
        schema = res.json()

        # Check API metadata
        self.assertEqual(schema["info"]["title"], "Petty Cash Management API")
        self.assertEqual(schema["info"]["version"], "1.0.0")

        # Check security schemes include BearerAuth
        self.assertIn("components", schema)
        self.assertIn("securitySchemes", schema["components"])
        self.assertIn("BearerAuth", schema["components"]["securitySchemes"])
        self.assertEqual(schema["components"]["securitySchemes"]["BearerAuth"]["type"], "http")
        self.assertEqual(schema["components"]["securitySchemes"]["BearerAuth"]["scheme"], "bearer")

        # Check OpenAPI tags cover key subsystems
        tag_names = [t["name"] for t in schema.get("tags", [])]
        self.assertIn("Operations & Observability", tag_names)
        self.assertIn("Health Probes", tag_names)
        self.assertIn("Authentication", tag_names)
        self.assertIn("Requests & Approvals", tag_names)
        self.assertIn("Financial Controls & Periods", tag_names)
        self.assertIn("Reports & Exports", tag_names)

        # Check that core routes are documented
        paths = schema["paths"]
        self.assertIn("/api/health/live", paths)
        self.assertIn("/api/health/ready", paths)
        self.assertIn("/api/operations/metrics", paths)
        self.assertIn("/api/operations/backups", paths)
        self.assertIn("/api/operations/alerts", paths)
        self.assertIn("/api/requests", paths)
        self.assertIn("/api/company-receipts", paths)

        # 2. Check Swagger UI endpoint
        res_docs = self.client.get("/docs")
        self.assertEqual(res_docs.status_code, 200)
        self.assertIn("swagger-ui", res_docs.text.lower())

    def test_02_correlation_id_propagation_and_header(self):
        """Acceptance Criteria: Logs are structured and include correlation IDs; incoming correlation ID propagated."""
        # Request with custom correlation ID
        custom_cid = "test-corr-abc-12345"
        res = self.client.get(
            "/api/health/live",
            headers={"X-Correlation-ID": custom_cid},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Correlation-ID"), custom_cid)

        # Request without correlation ID auto-generates one
        res2 = self.client.get("/api/health/live")
        self.assertEqual(res2.status_code, 200)
        generated_cid = res2.headers.get("X-Correlation-ID")
        self.assertTrue(generated_cid)
        self.assertTrue(generated_cid.startswith("corr-"))

        # Verify audit trail captures the active correlation ID
        audit_corr_id = "corr-audit-flow-999"
        res3 = self.client.post(
            "/api/financial-periods",
            headers={
                "Authorization": f"Bearer {self.finance_token}",
                "X-Correlation-ID": audit_corr_id,
            },
            json={"period_start": "2026-11-01", "period_end": "2026-11-30"},
        )
        self.assertEqual(res3.status_code, 200)
        events = list_audit_events(action="FINANCIAL_PERIOD_CREATED")
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["correlation_id"], audit_corr_id)

    def test_03_structured_json_logging_and_sensitive_redaction(self):
        """Acceptance Criteria: Sensitive credentials and personal data are not written to logs."""
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="petty_cash.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="User login attempted with password and token",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-log-test-111"
        record.__dict__["credentials"] = {"password": "SuperSecretPassword123!", "token": "xyz987token"}
        record.__dict__["authorization"] = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        self.assertEqual(log_data["level"], "INFO")
        self.assertEqual(log_data["logger"], "petty_cash.test")
        self.assertEqual(log_data["correlation_id"], "corr-log-test-111")
        self.assertIn("timestamp", log_data)

        # Sensitive field redaction test
        extras = log_data.get("extra", {})
        self.assertEqual(extras["credentials"], "[REDACTED]")
        self.assertEqual(extras["authorization"], "[REDACTED]")

        scrubbed_str = redact_sensitive_data("Authorization header: Bearer my-secret-token")
        self.assertEqual(scrubbed_str, "Authorization header: Bearer [REDACTED]")

        # Unit test redact_sensitive_data directly
        raw_dict = {
            "user_id": "usr_1",
            "password": "plain_password",
            "password_hash": "$2b$12$e...",
            "new_password": "new_plain_pass",
            "api_key": "sk-12345",
            "safe_field": "valid_value",
            "nested": {
                "secret_key": "hidden",
                "normal": 42,
            },
        }
        scrubbed = redact_sensitive_data(raw_dict)
        self.assertEqual(scrubbed["password"], "[REDACTED]")
        self.assertEqual(scrubbed["password_hash"], "[REDACTED]")
        self.assertEqual(scrubbed["new_password"], "[REDACTED]")
        self.assertEqual(scrubbed["api_key"], "[REDACTED]")
        self.assertEqual(scrubbed["nested"]["secret_key"], "[REDACTED]")
        self.assertEqual(scrubbed["safe_field"], "valid_value")
        self.assertEqual(scrubbed["nested"]["normal"], 42)

    def test_04_liveness_and_readiness_probes(self):
        """Acceptance Criteria: Health checks detect database connectivity and readiness failures."""
        # Liveness probe
        res_live = self.client.get("/api/health/live")
        self.assertEqual(res_live.status_code, 200)
        self.assertEqual(res_live.json()["status"], "ok")
        self.assertIn("timestamp", res_live.json())

        # Readiness probe healthy
        res_ready = self.client.get("/api/health/ready")
        self.assertEqual(res_ready.status_code, 200)
        ready_data = res_ready.json()
        self.assertEqual(ready_data["status"], "ready")
        self.assertEqual(ready_data["database"]["status"], "healthy")
        self.assertEqual(ready_data["storage"]["status"], "healthy")

        # Readiness probe failure detection (simulating database downtime)
        with patch("backend.operations_service.check_database_health") as mock_db_health:
            mock_db_health.return_value = {
                "status": "unhealthy",
                "latency_ms": 15.2,
                "error": "database connection refused",
            }
            res_fail = self.client.get("/api/health/ready")
            self.assertEqual(res_fail.status_code, 503)
            fail_data = res_fail.json()
            self.assertEqual(fail_data["status"], "not_ready")
            self.assertEqual(fail_data["database"]["status"], "unhealthy")

    def test_05_metrics_collection_and_endpoint(self):
        """Acceptance Criteria: API latency, error metrics, and business metrics tracking."""
        # Unauthenticated request to metrics
        res_unauth = self.client.get("/api/operations/metrics")
        self.assertEqual(res_unauth.status_code, 401)

        # Unauthorized (employee) request
        res_emp = self.client.get(
            "/api/operations/metrics",
            headers={"Authorization": f"Bearer {self.employee_token}"},
        )
        self.assertEqual(res_emp.status_code, 403)

        # Perform some actions to populate metrics
        self.client.get("/api/health/live")
        project = create_master_record("projects", "Phase 9 Project")
        ledger = create_master_record("ledgers", "Phase 9 Ledger")
        draft = create_draft(
            requester_id=self.employee["id"],
            project_id=project["id"],
            ledger_id=ledger["id"],
            category="Office Supplies",
            request_date="2026-11-18",
            amount=75.0,
            purpose="Office stationary",
            notes=None,
            approving_manager_id=self.manager["id"],
        )
        submit_request(draft["id"], self.employee["id"])

        # Admin fetches metrics
        res_admin = self.client.get(
            "/api/operations/metrics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_admin.status_code, 200)
        data = res_admin.json()

        # Check API metrics structure
        self.assertIn("api_metrics", data)
        api = data["api_metrics"]
        self.assertGreater(api["total_requests"], 0)
        self.assertIn("status_distribution", api)
        self.assertIn("endpoints", api)

        # Check Business metrics structure
        self.assertIn("business_metrics", data)
        biz = data["business_metrics"]
        self.assertIn("total_requests", biz)
        self.assertIn("requests_by_status", biz)
        self.assertIn("queue_backlog", biz)
        self.assertEqual(biz["queue_backlog"]["total_pending"], 1)  # 1 submitted request
        self.assertIn("volume_metrics", biz)
        self.assertIn("cash_account", biz)

    def test_06_error_tracking_and_endpoint(self):
        """Acceptance Criteria: Errors are captured with actionable context."""
        # Record a test error directly into error tracker
        global_error_tracker.record_error(
            error_type="IntegrityError",
            message="Database constraint violation on ledger post",
            status_code=500,
            path="/api/requests/req-123/post",
            method="POST",
            correlation_id="corr-err-456",
            stack_trace="Traceback (most recent call last)...",
            context={"user_id": self.admin["id"], "password": "sensitive_password"},
        )

        res = self.client.get(
            "/api/operations/errors",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["count"], 1)

        err = data["errors"][0]
        self.assertEqual(err["error_type"], "IntegrityError")
        self.assertEqual(err["correlation_id"], "corr-err-456")
        self.assertEqual(err["status_code"], 500)
        self.assertEqual(err["path"], "/api/requests/req-123/post")
        # Ensure password in error context was scrubbed
        self.assertEqual(err["context"]["password"], "[REDACTED]")

    def test_07_backup_creation_and_integrity_verification(self):
        """Acceptance Criteria: Database backup creation, listing, and PRAGMA integrity verification."""
        # 1. Create online backup
        res_create = self.client.post(
            "/api/operations/backups/create",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_create.status_code, 200)
        backup_info = res_create.json()
        backup_id = backup_info["backup_id"]
        self.assertTrue(backup_id.startswith("petty_cash_backup_"))
        self.assertTrue(backup_id.endswith(".db"))
        self.assertGreater(backup_info["size_bytes"], 0)
        self.assertTrue(backup_info["checksum_sha256"])

        # Check audit event
        events = list_audit_events(action="DATABASE_BACKUP_CREATED")
        self.assertGreaterEqual(len(events), 1)

        # 2. List backups
        res_list = self.client.get(
            "/api/operations/backups",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_list.status_code, 200)
        backups = res_list.json()
        self.assertGreaterEqual(len(backups), 1)
        self.assertEqual(backups[0]["backup_id"], backup_id)

        # 3. Verify backup integrity
        res_verify = self.client.post(
            "/api/operations/backups/verify",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"backup_id": backup_id},
        )
        self.assertEqual(res_verify.status_code, 200)
        verify_data = res_verify.json()
        self.assertTrue(verify_data["valid"])
        self.assertEqual(verify_data["integrity_check"], "ok")
        self.assertGreaterEqual(verify_data["tables_count"], 4)

        # 4. Verify invalid backup file failure
        res_inv = self.client.post(
            "/api/operations/backups/verify",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"backup_id": "non_existent_backup.db"},
        )
        self.assertEqual(res_inv.status_code, 400)

    def test_08_alert_rules_evaluation(self):
        """Acceptance Criteria: Queue, posting, backup, and financial anomaly alerts are testable."""
        # Call alert evaluation
        res = self.client.get(
            "/api/operations/alerts",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("timestamp", data)
        self.assertIn("active_alerts_count", data)
        self.assertEqual(data["total_rules_evaluated"], 4)

        rule_ids = [a["rule_id"] for a in data["alerts"]]
        self.assertIn("queue_backlog", rule_ids)
        self.assertIn("failed_postings", rule_ids)
        self.assertIn("auth_failures", rule_ids)
        self.assertIn("backup_failures", rule_ids)

        for alert in data["alerts"]:
            self.assertIn("severity", alert)
            self.assertIn("status", alert)
            self.assertIn("message", alert)
            self.assertIn("threshold", alert)
            self.assertIn("trigger_value", alert)

    def test_09_alert_simulation_endpoint(self):
        """Acceptance Criteria: Queue, posting, backup, and financial anomaly alerts are testable via test endpoint."""
        scenarios = [
            "queue_backlog",
            "failed_postings",
            "auth_failures",
            "backup_failures",
        ]

        for sc in scenarios:
            res = self.client.post(
                "/api/operations/alerts/test",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={"scenario": sc},
            )
            self.assertEqual(res.status_code, 200, f"Failed for scenario {sc}")
            data = res.json()
            self.assertTrue(data["simulated"])
            self.assertEqual(data["scenario"], sc)
            self.assertEqual(data["alert"]["rule_id"], sc)
            self.assertEqual(data["alert"]["status"], "FIRING")

        # Invalid scenario returns 400
        res_bad = self.client.post(
            "/api/operations/alerts/test",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"scenario": "non_existent_rule"},
        )
        self.assertEqual(res_bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
