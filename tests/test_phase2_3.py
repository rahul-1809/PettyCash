import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend import database
from backend.auth_service import (
    authenticate_user,
    create_session,
    get_authenticated_user,
    revoke_session,
    set_password_with_token,
)
from backend.notification_service import (
    get_preferences,
    list_notifications,
    mark_notification_read,
    update_preferences,
)
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    provision_user,
    review_assignment,
)


class Phase2And3Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "auth.sqlite")
        database.DATABASE_URL = None
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        self.temp_dir.cleanup()

    def test_bootstrap_password_setup_and_session_lifecycle(self):
        admin = create_bootstrap_admin(
            "admin",
            "ADMIN@example.com",
            "a-secure-password",
        )
        self.assertEqual(admin["role"], "Admin")
        self.assertIsNone(authenticate_user("admin@example.com", "wrong-password"))

        user, onboarding_token = provision_user(
            "employee",
            "employee@example.com",
            "Employee",
            admin["id"],
        )
        set_password_with_token(onboarding_token, "another-secure-password")
        authenticated = authenticate_user(
            "employee@example.com",
            "another-secure-password",
        )
        self.assertEqual(authenticated["role"], "Employee")

        session_token = create_session(authenticated["id"])
        self.assertEqual(get_authenticated_user(session_token)["id"], authenticated["id"])
        self.assertTrue(revoke_session(session_token))
        self.assertIsNone(get_authenticated_user(session_token))

    def test_bootstrap_and_onboarding_are_single_use(self):
        create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        with self.assertRaises(ValueError):
            create_bootstrap_admin("second", "second@example.com", "a-secure-password")

        admin = authenticate_user("admin@example.com", "a-secure-password")
        user, token = provision_user(
            "employee",
            "employee@example.com",
            "Employee",
            admin["id"],
        )
        set_password_with_token(token, "another-secure-password")
        with self.assertRaises(ValueError):
            set_password_with_token(token, "third-secure-password")

    def test_assignments_and_notifications_follow_required_channels(self):
        admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        manager, _ = provision_user(
            "manager", "manager@example.com", "Manager", admin["id"]
        )
        employee, _ = provision_user(
            "employee", "employee@example.com", "Employee", admin["id"]
        )
        assignment = create_assignment(manager["id"], employee["id"], admin["id"])
        reviewed = review_assignment(assignment["id"], manager["id"], "APPROVED")
        self.assertEqual(reviewed["status"], "APPROVED")

        employee_notifications = list_notifications(employee["id"])
        self.assertTrue(any(n["event_type"] == "ASSIGNMENT_APPROVED" for n in employee_notifications))

        preferences = update_preferences(employee["id"], False, True)
        self.assertEqual(preferences["in_app_enabled"], 0)
        self.assertEqual(get_preferences(employee["id"])["email_enabled"], 1)

        notification = employee_notifications[0]
        self.assertTrue(mark_notification_read(employee["id"], notification["id"]))
        self.assertEqual(list_notifications(employee["id"], unread_only=True), [])

    def test_assignment_rejection_requires_reason(self):
        admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        manager, _ = provision_user("manager", "manager@example.com", "Manager", admin["id"])
        employee, _ = provision_user("employee", "employee@example.com", "Employee", admin["id"])
        assignment = create_assignment(manager["id"], employee["id"], admin["id"])

        with self.assertRaises(ValueError):
            review_assignment(assignment["id"], manager["id"], "REJECTED")

    def test_foreign_keys_remain_enabled_for_auth_domain(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with database.get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO user_sessions
                        (id, user_id, token_hash, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("session", "missing-user", "token", "future", "now"),
                )


if __name__ == "__main__":
    unittest.main()
