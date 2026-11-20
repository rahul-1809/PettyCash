"""Notification persistence with independently configurable delivery channels."""

import logging
import os
import secrets
import smtplib
import threading
from email.message import EmailMessage
from typing import Iterable, Optional

logger = logging.getLogger("notifications")

try:
    from backend import database
except ImportError:
    import database


def _send_notification_email_async(user_id: str, title: str, message: str) -> None:
    try:
        prefs = get_preferences(user_id)
        if not prefs.get("email_enabled", 1):
            return

        marker = database._placeholder()
        with database.get_connection() as connection:
            user_row = connection.execute(
                f"SELECT email, username FROM users WHERE id = {marker}",
                (user_id,),
            ).fetchone()
            if not user_row or not user_row["email"]:
                return
            recipient_email = user_row["email"]
            recipient_name = user_row["username"] or "User"

        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", 587))
        username = os.getenv("SMTP_USERNAME")
        password = os.getenv("SMTP_PASSWORD")
        sender = os.getenv("SMTP_SENDER")

        if not all((host, username, password, sender)):
            return

        app_url = os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")
        body = (
            f"Hello {recipient_name},\n\n"
            f"{message}\n\n"
            f"Log in to PettyCash Pro to view and take action: {app_url}\n\n"
            f"---\nPettyCash Notification System"
        )
        send_email(
            recipient=recipient_email,
            subject=f"PettyCash: {title}",
            body=body,
            host=host,
            port=port,
            username=username,
            password=password,
            sender=sender,
        )
        logger.info(f"Dispatched email notification '{title}' to {recipient_email}")
    except Exception as exc:
        logger.warning(f"Failed to dispatch email notification to user {user_id}: {exc}")


def ensure_preferences(user_id: str) -> None:
    marker = database._placeholder()
    with database.get_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO notification_preferences
                (user_id, in_app_enabled, email_enabled, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker})
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, 1, 1, database.now_iso()),
        )
        connection.commit()


def create_notification(
    user_id: str,
    event_type: str,
    title: str,
    message: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> dict:
    ensure_preferences(user_id)
    notification_id = secrets.token_urlsafe(18)
    marker = database._placeholder()
    with database.get_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO notifications
                (id, user_id, event_type, title, message, entity_type, entity_id, created_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                notification_id,
                user_id,
                event_type,
                title,
                message,
                entity_type,
                entity_id,
                database.now_iso(),
            ),
        )
        connection.commit()

    if not os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TESTING"):
        try:
            threading.Thread(
                target=_send_notification_email_async,
                args=(user_id, title, message),
                daemon=True,
            ).start()
        except Exception as exc:
            logger.warning(f"Failed to spawn email thread: {exc}")

    return {"id": notification_id, "user_id": user_id, "event_type": event_type}


def list_notifications(
    user_id: str,
    unread_only: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict]:
    marker = database._placeholder()
    clause = "AND read_at IS NULL" if unread_only else ""
    pagination_clause = ""
    params = [user_id]
    if limit is not None and limit > 0:
        pagination_clause = f"LIMIT {marker} OFFSET {marker}"
        params.extend([limit, max(0, offset)])
    with database.get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, event_type, title, message, entity_type, entity_id, read_at, created_at
            FROM notifications
            WHERE user_id={marker} {clause}
            ORDER BY created_at DESC
            {pagination_clause}
            """,
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_notification_read(user_id: str, notification_id: str) -> bool:
    marker = database._placeholder()
    with database.get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE notifications SET read_at={marker}
            WHERE id={marker} AND user_id={marker} AND read_at IS NULL
            """,
            (database.now_iso(), notification_id, user_id),
        )
        connection.commit()
        return cursor.rowcount == 1


def mark_notification_unread(user_id: str, notification_id: str) -> bool:
    marker = database._placeholder()
    with database.get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE notifications SET read_at=NULL
            WHERE id={marker} AND user_id={marker} AND read_at IS NOT NULL
            """,
            (notification_id, user_id),
        )
        connection.commit()
        return cursor.rowcount == 1


def mark_all_notifications_read(user_id: str) -> int:
    marker = database._placeholder()
    with database.get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE notifications SET read_at={marker}
            WHERE user_id={marker} AND read_at IS NULL
            """,
            (database.now_iso(), user_id),
        )
        connection.commit()
        return cursor.rowcount


def get_preferences(user_id: str) -> dict:
    ensure_preferences(user_id)
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT user_id, in_app_enabled, email_enabled, updated_at
            FROM notification_preferences WHERE user_id={marker}
            """,
            (user_id,),
        ).fetchone()
    return dict(row)


def update_preferences(user_id: str, in_app_enabled: bool, email_enabled: bool) -> dict:
    ensure_preferences(user_id)
    marker = database._placeholder()
    with database.get_connection() as connection:
        connection.execute(
            f"""
            UPDATE notification_preferences
            SET in_app_enabled={marker}, email_enabled={marker}, updated_at={marker}
            WHERE user_id={marker}
            """,
            (int(in_app_enabled), int(email_enabled), database.now_iso(), user_id),
        )
        connection.commit()
    return get_preferences(user_id)


def send_email(
    recipient: str,
    subject: str,
    body: str,
    host: str,
    port: int,
    username: str,
    password: str,
    sender: str,
) -> None:
    if not all((host, username, password, sender)):
        raise RuntimeError("SMTP configuration is incomplete.")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
