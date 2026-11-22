"""Notification persistence with independently configurable delivery channels."""

import logging
import os
import queue
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage
from typing import Iterable, Optional

logger = logging.getLogger("petty_cash.app")

try:
    from backend import database
except ImportError:
    import database

# ── Serialized Background Email Queue & Worker ──────────────────────────────
# Protects against Gmail SMTP concurrent connection limits (HTTP 421)
# and ensures retry with exponential backoff if temporary delivery fails.

_EMAIL_QUEUE: queue.Queue = queue.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _email_worker() -> None:
    """Sequential daemon worker that processes transactional emails one at a time."""
    logger.info("PettyCash Email Worker thread started.")
    while True:
        try:
            item = _EMAIL_QUEUE.get()
            if item is None:
                break
            recipient_email, subject, body = item
            _send_email_with_retry(recipient_email, subject, body, max_retries=3)
            _EMAIL_QUEUE.task_done()
            time.sleep(0.5)  # Safe delay between messages to respect SMTP provider limits
        except Exception as exc:
            logger.error(f"Unexpected error in email worker: {exc}", exc_info=True)


def _ensure_worker_started() -> None:
    global _WORKER_STARTED
    if not _WORKER_STARTED:
        with _WORKER_LOCK:
            if not _WORKER_STARTED:
                worker_thread = threading.Thread(target=_email_worker, daemon=True, name="pettycash-email-worker")
                worker_thread.start()
                _WORKER_STARTED = True


def _send_email_with_retry(recipient_email: str, subject: str, body: str, max_retries: int = 3) -> bool:
    host = os.getenv("SMTP_HOST")
    port_raw = os.getenv("SMTP_PORT", "587")
    port = int(port_raw) if port_raw and str(port_raw).isdigit() else 587
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_SENDER")

    if not all((host, username, password, sender)):
        logger.warning(f"SMTP configuration incomplete; skipping dispatch to {recipient_email}")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            send_email(
                recipient=recipient_email,
                subject=subject,
                body=body,
                host=host,
                port=port,
                username=username,
                password=password,
                sender=sender,
            )
            logger.info(f"Successfully dispatched email '{subject}' to {recipient_email} (attempt {attempt})")
            return True
        except Exception as exc:
            logger.warning(f"Email delivery attempt {attempt}/{max_retries} failed for {recipient_email}: {exc}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.error(f"Exhausted all {max_retries} retries sending email to {recipient_email}: {exc}", exc_info=True)
    return False


def enqueue_email(recipient_email: str, subject: str, body: str) -> None:
    """Enqueue an email for guaranteed serialized asynchronous delivery."""
    if not recipient_email or not recipient_email.strip():
        return
    _ensure_worker_started()
    _EMAIL_QUEUE.put((recipient_email.strip(), subject, body))


def send_test_email(recipient_email: str, recipient_name: str = "User") -> None:
    """Synchronously send a test email to verify credentials and SMTP routing."""
    host = os.getenv("SMTP_HOST")
    port_raw = os.getenv("SMTP_PORT", "587")
    port = int(port_raw) if port_raw and str(port_raw).isdigit() else 587
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_SENDER")

    if not all((host, username, password, sender)):
        raise RuntimeError("SMTP configuration is incomplete. Check SMTP_HOST, SMTP_PORT, SMTP_USERNAME, and SMTP_PASSWORD.")

    app_url = os.getenv("APP_BASE_URL", "https://pettycash.ajassociate.online").rstrip("/")
    subject = "PettyCash Pro - Notification Delivery Test"
    body = (
        f"Hello {recipient_name},\n\n"
        f"This is a confirmation test email from PettyCash Pro.\n"
        f"Your transactional email notification channel is actively connected and functioning properly.\n\n"
        f"System URL: {app_url}\n\n"
        f"---\nPettyCash Notification System"
    )
    send_email(
        recipient=recipient_email,
        subject=subject,
        body=body,
        host=host,
        port=port,
        username=username,
        password=password,
        sender=sender,
    )


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
    """Create in-app notification and reliably enqueue email delivery if enabled."""
    ensure_preferences(user_id)
    notification_id = secrets.token_urlsafe(18)
    marker = database._placeholder()

    recipient_email = None
    recipient_name = "User"
    email_enabled = True

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
        user_row = connection.execute(
            f"""
            SELECT u.email, u.username, np.email_enabled
            FROM users u
            LEFT JOIN notification_preferences np ON np.user_id = u.id
            WHERE u.id = {marker}
            """,
            (user_id,),
        ).fetchone()
        if user_row:
            recipient_email = user_row["email"]
            recipient_name = user_row["username"] or "User"
            if user_row["email_enabled"] is not None:
                email_enabled = bool(user_row["email_enabled"])
        connection.commit()

    # Deliver via background queue if email is configured and enabled by user
    if not os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("TESTING"):
        if recipient_email and email_enabled:
            app_url = os.getenv("APP_BASE_URL", "https://pettycash.ajassociate.online").rstrip("/")
            body = (
                f"Hello {recipient_name},\n\n"
                f"{message}\n\n"
                f"Log in to PettyCash Pro to view and take action: {app_url}\n\n"
                f"---\nPettyCash Notification System"
            )
            enqueue_email(recipient_email, f"PettyCash: {title}", body)
        elif not email_enabled:
            logger.info(f"Notification email skipped for user {user_id}: email_enabled is 0 in preferences")

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

    # Use SMTP_SSL for port 465, or SMTP with STARTTLS for port 587/25
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
