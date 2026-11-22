"""Authentication primitives and persistence for secure user sessions."""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt

try:
    from backend import database
    from backend.audit_service import record_audit_event
except ImportError:
    import database
    from audit_service import record_audit_event


SESSION_TTL = timedelta(days=30)
ONBOARDING_TTL = timedelta(hours=24)

# In-memory session cache: token_hash -> (user_info, expires_at_dt, cached_at_monotonic)
_AUTH_CACHE = {}
_AUTH_CACHE_TTL = 60.0  # seconds


def clear_auth_cache(token_hash: Optional[str] = None) -> None:
    global _AUTH_CACHE
    if token_hash:
        _AUTH_CACHE.pop(token_hash, None)
    else:
        _AUTH_CACHE.clear()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def authenticate_user(email: str, password: str) -> Optional[dict]:
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT u.id, u.username, u.email, u.is_active, u.password_hash,
                   r.name AS role
            FROM users u JOIN roles r ON r.id=u.role_id
            WHERE u.email={marker}
            """,
            (email.strip().lower(),),
        ).fetchone()
    if not row or not row["is_active"] or not row["password_hash"]:
        record_audit_event(
            actor_user_id=row["id"] if row else None,
            action="AUTH_LOGIN_FAILED",
            entity_type="user",
            entity_id=row["id"] if row else None,
            after={"email": email.strip().lower(), "reason": "user_not_found_or_inactive"},
        )
        return None
    if not verify_password(password, row["password_hash"]):
        record_audit_event(
            actor_user_id=row["id"],
            action="AUTH_LOGIN_FAILED",
            entity_type="user",
            entity_id=row["id"],
            after={"email": email.strip().lower(), "reason": "invalid_password"},
        )
        return None
    result = dict(row)
    result.pop("password_hash", None)
    return result


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expiry(ttl: timedelta) -> str:
    return (datetime.now(timezone.utc) + ttl).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def create_session(user_id: str) -> str:
    raw_token = secrets.token_urlsafe(48)
    session_id = secrets.token_urlsafe(18)
    marker = database._placeholder()
    with database.get_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO user_sessions
                (id, user_id, token_hash, expires_at, created_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (session_id, user_id, hash_token(raw_token), expiry(SESSION_TTL), database.now_iso()),
        )
        connection.commit()
    return raw_token


def revoke_session(raw_token: str) -> bool:
    th = hash_token(raw_token)
    clear_auth_cache(th)
    marker = database._placeholder()
    with database.get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE user_sessions SET revoked_at={marker}
            WHERE token_hash={marker} AND revoked_at IS NULL
            """,
            (database.now_iso(), th),
        )
        connection.commit()
        return cursor.rowcount == 1


def get_authenticated_user(raw_token: str) -> Optional[dict]:
    th = hash_token(raw_token)
    now_m = time.monotonic()
    now_utc = datetime.now(timezone.utc)

    cached = _AUTH_CACHE.get(th)
    if cached:
        user_data, exp_dt, cached_at = cached
        if now_m - cached_at < _AUTH_CACHE_TTL and exp_dt > now_utc:
            return dict(user_data)
        _AUTH_CACHE.pop(th, None)

    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT u.id, u.username, u.email, u.is_active, r.name AS role, s.expires_at
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            JOIN roles r ON r.id = u.role_id
            WHERE s.token_hash={marker}
              AND s.revoked_at IS NULL
              AND u.is_active=1
            """,
            (th,),
        ).fetchone()

    if not row:
        return None

    exp_dt = parse_timestamp(row["expires_at"])
    if exp_dt <= now_utc:
        return None

    # Rolling extension: If session has less than 15 days remaining, automatically extend it
    if (exp_dt - now_utc) < timedelta(days=15):
        try:
            new_exp = expiry(SESSION_TTL)
            with database.get_connection() as conn:
                conn.execute(
                    f"UPDATE user_sessions SET expires_at={marker} WHERE token_hash={marker} AND revoked_at IS NULL",
                    (new_exp, th),
                )
                conn.commit()
            exp_dt = parse_timestamp(new_exp)
        except Exception:
            pass

    user_info = {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "is_active": row["is_active"],
        "role": row["role"],
    }
    _AUTH_CACHE[th] = (user_info, exp_dt, now_m)
    return dict(user_info)


def create_onboarding_token(user_id: str) -> str:
    raw_token = secrets.token_urlsafe(32)
    marker = database._placeholder()
    with database.get_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO onboarding_tokens
                (id, user_id, token_hash, expires_at, created_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                secrets.token_urlsafe(18),
                user_id,
                hash_token(raw_token),
                expiry(ONBOARDING_TTL),
                database.now_iso(),
            ),
        )
        connection.commit()
    return raw_token


def set_password_with_token(raw_token: str, password: str) -> dict:
    password_hash = hash_password(password)
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT user_id, expires_at FROM onboarding_tokens
            WHERE token_hash={marker} AND used_at IS NULL
            """,
            (hash_token(raw_token),),
        ).fetchone()
        if not row or parse_timestamp(row["expires_at"]) <= datetime.now(timezone.utc):
            record_audit_event(
                action="AUTH_TOKEN_FAILED",
                entity_type="onboarding_token",
                after={"reason": "token_invalid_or_expired"},
            )
            raise ValueError("Onboarding token is invalid or expired.")

        timestamp = database.now_iso()
        connection.execute(
            f"UPDATE users SET password_hash={marker}, updated_at={marker} WHERE id={marker}",
            (password_hash, timestamp, row["user_id"]),
        )
        connection.execute(
            f"UPDATE onboarding_tokens SET used_at={marker} WHERE token_hash={marker}",
            (timestamp, hash_token(raw_token)),
        )
        connection.commit()
    return {"user_id": row["user_id"]}

