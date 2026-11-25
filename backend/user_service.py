"""User provisioning and manager-employee assignment persistence."""

import secrets
from typing import Optional

try:
    from backend import database
    from backend.auth_service import create_onboarding_token, hash_password
    from backend.notification_service import create_notification
    from backend.audit_service import record_audit_event
except ImportError:
    import database
    from auth_service import create_onboarding_token, hash_password
    from notification_service import create_notification
    from audit_service import record_audit_event


ROLE_IDS = {
    "Admin": "role-admin",
    "Manager": "role-manager",
    "Employee": "role-employee",
}


def create_bootstrap_admin(username: str, email: str, password: str) -> dict:
    marker = database._placeholder()
    normalized_username = username.strip()
    normalized_email = email.strip().lower()

    with database.get_connection() as connection:
        existing = connection.execute(
            f"""
            SELECT u.id FROM users u
            JOIN roles r ON r.id=u.role_id
            WHERE r.name={marker}
            """,
            ("Admin",),
        ).fetchone()
        if existing:
            raise ValueError("An Admin account already exists.")

        existing_user = connection.execute(
            f"SELECT username, email FROM users WHERE LOWER(username)=LOWER({marker}) OR LOWER(email)=LOWER({marker})",
            (normalized_username, normalized_email),
        ).fetchone()
        if existing_user:
            if existing_user["username"].lower() == normalized_username.lower():
                raise ValueError(f"Username '{normalized_username}' is already in use.")
            raise ValueError(f"Email '{normalized_email}' is already registered.")

        user_id = secrets.token_urlsafe(18)
        password_hash = hash_password(password)
        timestamp = database.now_iso()
        connection.execute(
            f"""
            INSERT INTO users
                (id, username, email, role_id, password_hash, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                user_id,
                normalized_username,
                normalized_email,
                ROLE_IDS["Admin"],
                password_hash,
                timestamp,
                timestamp,
            ),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=user_id,
            action="ADMIN_BOOTSTRAPPED",
            entity_type="user",
            entity_id=user_id,
            after={"username": normalized_username, "email": normalized_email, "role": "Admin"},
            correlation_id=user_id,
        )
        connection.commit()
    return {"id": user_id, "username": normalized_username, "email": normalized_email, "role": "Admin"}


def provision_user(username: str, email: str, role: str, actor_user_id: str) -> tuple[dict, str]:
    if role not in {"Admin", "Manager", "Employee"}:
        raise ValueError("Only Admin, Manager, or Employee accounts can be provisioned.")
    marker = database._placeholder()
    normalized_username = username.strip()
    normalized_email = email.strip().lower()

    with database.get_connection() as connection:
        # Pre-check for duplicate active username or email
        active_conflict = connection.execute(
            f"SELECT username, email FROM users WHERE is_active = 1 AND (LOWER(username)=LOWER({marker}) OR LOWER(email)=LOWER({marker}))",
            (normalized_username, normalized_email),
        ).fetchone()
        if active_conflict:
            act_dict = dict(active_conflict)
            if act_dict["username"].lower() == normalized_username.lower():
                raise ValueError(f"User with username '{normalized_username}' already exists.")
            raise ValueError(f"User with email '{normalized_email}' already exists.")

        # Check if there is an inactive user to reactivate
        inactive_user = connection.execute(
            f"SELECT id, username, email FROM users WHERE is_active = 0 AND (LOWER(username)=LOWER({marker}) OR LOWER(email)=LOWER({marker}))",
            (normalized_username, normalized_email),
        ).fetchone()
        if inactive_user:
            inact_dict = dict(inactive_user)
            target_user_id = inact_dict["id"]
            timestamp = database.now_iso()
            connection.execute(
                f"""
                UPDATE users
                SET role_id = {marker}, username = {marker}, email = {marker}, is_active = 1, updated_at = {marker}
                WHERE id = {marker}
                """,
                (ROLE_IDS[role], normalized_username, normalized_email, timestamp, target_user_id),
            )
            record_audit_event(
                connection=connection,
                actor_user_id=actor_user_id,
                action="USER_REACTIVATED",
                entity_type="user",
                entity_id=target_user_id,
                after={"username": normalized_username, "email": normalized_email, "role": role},
                correlation_id=target_user_id,
            )
            connection.commit()

            token = create_onboarding_token(target_user_id)
            create_notification(
                actor_user_id,
                "USER_REACTIVATED",
                "User account reactivated",
                f"{role} account {normalized_email} was reactivated.",
                "user",
                target_user_id,
            )
            return (
                {"id": target_user_id, "username": normalized_username, "email": normalized_email, "role": role, "reactivated": True},
                token,
            )

        user_id = secrets.token_urlsafe(18)
        timestamp = database.now_iso()
        try:
            connection.execute(
                f"""
                INSERT INTO users
                    (id, username, email, role_id, created_at, updated_at)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (
                    user_id,
                    normalized_username,
                    normalized_email,
                    ROLE_IDS[role],
                    timestamp,
                    timestamp,
                ),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "integrity" in str(exc).lower():
                raise ValueError(f"A user with username '{normalized_username}' or email '{normalized_email}' already exists.") from exc
            raise

        record_audit_event(
            connection=connection,
            actor_user_id=actor_user_id,
            action="USER_CREATED",
            entity_type="user",
            entity_id=user_id,
            after={"username": normalized_username, "email": normalized_email, "role": role},
            correlation_id=user_id,
        )
        connection.commit()

    token = create_onboarding_token(user_id)
    create_notification(
        actor_user_id,
        "USER_CREATED",
        "User account created",
        f"{role} account {email.strip().lower()} was created.",
        "user",
        user_id,
    )
    return (
        {"id": user_id, "username": username.strip(), "email": email.strip().lower(), "role": role},
        token,
    )


def list_users(include_inactive: bool = False) -> list[dict]:
    with database.get_connection() as connection:
        where_clause = "" if include_inactive else "WHERE u.is_active = 1"
        rows = connection.execute(
            f"""
            SELECT u.id, u.username, u.email, r.name AS role, u.is_active,
                   u.created_at, u.updated_at
            FROM users u JOIN roles r ON r.id=u.role_id
            {where_clause}
            ORDER BY u.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_user(user_id: str, admin_user_id: str) -> dict:
    """Deletes or deactivates a user account, revoking sessions and clearing assignments."""
    if user_id == admin_user_id:
        raise ValueError("Administrators cannot delete their own active account.")

    marker = database._placeholder()
    with database.get_connection() as connection:
        user_row = connection.execute(
            f"SELECT id, username, email, is_active FROM users WHERE id = {marker}",
            (user_id,),
        ).fetchone()
        if not user_row:
            raise LookupError("User not found.")

        # Check for financial bindings (petty cash requests, company receipts, closed periods, adjustments)
        has_requests = connection.execute(
            f"SELECT 1 FROM petty_cash_requests WHERE requester_id = {marker} OR approving_manager_id = {marker} LIMIT 1",
            (user_id, user_id),
        ).fetchone()
        has_receipts = connection.execute(
            f"SELECT 1 FROM company_receipts WHERE created_by = {marker} LIMIT 1",
            (user_id,),
        ).fetchone()
        has_closed_periods = connection.execute(
            f"SELECT 1 FROM financial_periods WHERE closed_by = {marker} LIMIT 1",
            (user_id,),
        ).fetchone()
        has_adjustments = connection.execute(
            f"SELECT 1 FROM ledger_adjustments WHERE created_by = {marker} LIMIT 1",
            (user_id,),
        ).fetchone()

        # Delete manager-employee assignments involving this user
        connection.execute(
            f"""
            DELETE FROM manager_employee_assignments
            WHERE manager_id = {marker} OR employee_id = {marker} OR requested_by = {marker} OR reviewed_by = {marker}
            """,
            (user_id, user_id, user_id, user_id),
        )

        # Invalidate active sessions & tokens
        connection.execute(
            f"DELETE FROM user_sessions WHERE user_id = {marker}",
            (user_id,),
        )
        connection.execute(
            f"DELETE FROM onboarding_tokens WHERE user_id = {marker}",
            (user_id,),
        )

        if has_requests or has_receipts or has_closed_periods or has_adjustments:
            # User is tied to permanent ledger records; soft-delete (deactivate) so ledger integrity is preserved
            connection.execute(
                f"UPDATE users SET is_active = 0, updated_at = {marker} WHERE id = {marker}",
                (database.now_iso(), user_id),
            )
            mode = "DEACTIVATED"
        else:
            # User has no immutable financial records; remove all auxiliary records and delete user completely
            connection.execute(
                f"DELETE FROM notifications WHERE user_id = {marker}",
                (user_id,),
            )
            connection.execute(
                f"DELETE FROM notification_preferences WHERE user_id = {marker}",
                (user_id,),
            )
            connection.execute(
                f"UPDATE audit_events SET actor_user_id = NULL WHERE actor_user_id = {marker}",
                (user_id,),
            )
            connection.execute(
                f"DELETE FROM users WHERE id = {marker}",
                (user_id,),
            )
            mode = "DELETED"

        record_audit_event(
            connection=connection,
            actor_user_id=admin_user_id,
            action="USER_DELETED",
            entity_type="user",
            entity_id=user_id,
            before={
                "username": user_row["username"],
                "email": user_row["email"],
                "is_active": user_row["is_active"],
            },
            after={"status": mode, "deleted_by": admin_user_id},
        )
        connection.commit()

    return {"id": user_id, "username": user_row["username"], "status": mode}


def deactivate_user(user_id: str, admin_user_id: str) -> dict:
    """Explicitly deactivates a user account, revoking active sessions and clearing assignments."""
    if user_id == admin_user_id:
        raise ValueError("Administrators cannot deactivate their own active account.")

    marker = database._placeholder()
    with database.get_connection() as connection:
        user_row = connection.execute(
            f"SELECT id, username, email, is_active FROM users WHERE id = {marker}",
            (user_id,),
        ).fetchone()
        if not user_row:
            raise LookupError("User not found.")
        user_dict = dict(user_row)
        if user_dict.get("is_active") == 0:
            return {"id": user_id, "username": user_dict["username"], "status": "ALREADY_DEACTIVATED"}

        # Clear assignments involving this user
        connection.execute(
            f"""
            DELETE FROM manager_employee_assignments
            WHERE manager_id = {marker} OR employee_id = {marker} OR requested_by = {marker} OR reviewed_by = {marker}
            """,
            (user_id, user_id, user_id, user_id),
        )

        # Invalidate active sessions & tokens
        connection.execute(
            f"DELETE FROM user_sessions WHERE user_id = {marker}",
            (user_id,),
        )
        connection.execute(
            f"DELETE FROM onboarding_tokens WHERE user_id = {marker}",
            (user_id,),
        )

        # Deactivate
        connection.execute(
            f"UPDATE users SET is_active = 0, updated_at = {marker} WHERE id = {marker}",
            (database.now_iso(), user_id),
        )

        record_audit_event(
            connection=connection,
            actor_user_id=admin_user_id,
            action="USER_DEACTIVATED",
            entity_type="user",
            entity_id=user_id,
            before={
                "username": user_dict["username"],
                "email": user_dict["email"],
                "is_active": user_dict.get("is_active", 1),
            },
            after={"status": "DEACTIVATED", "deactivated_by": admin_user_id},
        )
        connection.commit()

    return {"id": user_id, "username": user_dict["username"], "status": "DEACTIVATED"}


def reactivate_user(user_id: str, admin_user_id: str) -> dict:
    """Explicitly reactivates a previously deactivated user account."""
    marker = database._placeholder()
    with database.get_connection() as connection:
        user_row = connection.execute(
            f"SELECT id, username, email, is_active FROM users WHERE id = {marker}",
            (user_id,),
        ).fetchone()
        if not user_row:
            raise LookupError("User not found.")
        user_dict = dict(user_row)
        if user_dict.get("is_active") == 1:
            return {"id": user_id, "username": user_dict["username"], "status": "ALREADY_ACTIVE"}

        connection.execute(
            f"UPDATE users SET is_active = 1, updated_at = {marker} WHERE id = {marker}",
            (database.now_iso(), user_id),
        )

        record_audit_event(
            connection=connection,
            actor_user_id=admin_user_id,
            action="USER_REACTIVATED",
            entity_type="user",
            entity_id=user_id,
            before={
                "username": user_dict["username"],
                "email": user_dict["email"],
                "is_active": 0,
            },
            after={"status": "ACTIVE", "reactivated_by": admin_user_id},
        )
        connection.commit()

    return {"id": user_id, "username": user_dict["username"], "status": "ACTIVE"}


def create_assignment(manager_id: str, employee_id: str, requested_by: str) -> dict:
    if manager_id == employee_id:
        raise ValueError("A user cannot be assigned to themselves.")
    marker = database._placeholder()
    assignment_id = secrets.token_urlsafe(18)
    with database.get_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO manager_employee_assignments
                (id, manager_id, employee_id, requested_by, created_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (assignment_id, manager_id, employee_id, requested_by, database.now_iso()),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=requested_by,
            action="ASSIGNMENT_CREATED",
            entity_type="manager_employee_assignment",
            entity_id=assignment_id,
            after={"manager_id": manager_id, "employee_id": employee_id, "status": "PENDING"},
            correlation_id=assignment_id,
        )
        connection.commit()

    with database.get_connection() as connection:
        admin_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (requested_by,),
        ).fetchone()
        emp_info = connection.execute(
            f"SELECT username, email FROM users WHERE id={database._placeholder()}",
            (employee_id,),
        ).fetchone()
    admin_name = admin_info["username"] if admin_info else "Administrator"
    emp_name = emp_info["username"] if emp_info else "Employee"
    emp_email = emp_info["email"] if emp_info else ""

    create_notification(
        manager_id,
        "ASSIGNMENT_PENDING",
        f"Employee {emp_name} assigned by Admin {admin_name}",
        f"Admin {admin_name} assigned employee {emp_name} ({emp_email}) to you for review and approval.",
        "assignment",
        assignment_id,
    )
    return {"id": assignment_id, "status": "PENDING"}


def review_assignment(
    assignment_id: str,
    manager_id: str,
    decision: str,
    reason: Optional[str] = None,
) -> dict:
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("Assignment decision must be APPROVED or REJECTED.")
    if decision == "REJECTED" and not (reason or "").strip():
        raise ValueError("A rejection reason is required.")

    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT manager_id, employee_id, requested_by
            FROM manager_employee_assignments
            WHERE id={marker} AND status='PENDING'
            """,
            (assignment_id,),
        ).fetchone()
        if not row or row["manager_id"] != manager_id:
            raise LookupError("Pending assignment was not found for this Manager.")
        connection.execute(
            f"""
            UPDATE manager_employee_assignments
            SET status={marker}, reviewed_by={marker}, review_reason={marker}, reviewed_at={marker}
            WHERE id={marker}
            """,
            (decision, manager_id, reason, database.now_iso(), assignment_id),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=manager_id,
            action="ASSIGNMENT_APPROVED" if decision == "APPROVED" else "ASSIGNMENT_REJECTED",
            entity_type="manager_employee_assignment",
            entity_id=assignment_id,
            before={"status": "PENDING"},
            after={"status": decision, "reason": reason},
            correlation_id=assignment_id,
        )
        connection.commit()

    with database.get_connection() as connection:
        mgr_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (row["manager_id"],),
        ).fetchone()
        emp_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (row["employee_id"],),
        ).fetchone()
    mgr_name = mgr_info["username"] if mgr_info else "Manager"
    emp_name = emp_info["username"] if emp_info else "Employee"

    event = "ASSIGNMENT_APPROVED" if decision == "APPROVED" else "ASSIGNMENT_REJECTED"
    if decision == "APPROVED":
        create_notification(
            row["requested_by"],
            event,
            f"Assignment approved by Manager {mgr_name}",
            f"Manager {mgr_name} approved the assignment of employee {emp_name}.",
            "assignment",
            assignment_id,
        )
        create_notification(
            row["employee_id"],
            event,
            f"Manager {mgr_name} assigned",
            f"Manager {mgr_name} approved and is now your active approving manager for petty cash requests.",
            "assignment",
            assignment_id,
        )
    else:
        create_notification(
            row["requested_by"],
            event,
            f"Assignment rejected by Manager {mgr_name}",
            reason or f"Manager {mgr_name} rejected the assignment of employee {emp_name}.",
            "assignment",
            assignment_id,
        )
    return {"id": assignment_id, "status": decision, "reason": reason}


def list_assignments(user_id: str, role: str) -> list[dict]:
    marker = database._placeholder()
    if role == "Manager":
        clause = f"AND a.manager_id={marker}"
        params = (user_id,)
    elif role == "Employee":
        clause = f"AND a.employee_id={marker}"
        params = (user_id,)
    else:
        clause = ""
        params = ()
    with database.get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT a.id, a.manager_id, m.username AS manager_username, m.email AS manager_email,
                   a.employee_id, e.username AS employee_username, e.email AS employee_email,
                   a.status, a.review_reason, a.created_at, a.created_at AS assigned_at, a.reviewed_at
            FROM manager_employee_assignments a
            JOIN users m ON m.id=a.manager_id
            JOIN users e ON e.id=a.employee_id
            WHERE 1=1 {clause}
            ORDER BY a.created_at DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]
