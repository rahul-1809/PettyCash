"""Observability and production operations module.

Provides:
- Contextual correlation IDs across requests and background tasks
- JSON structured logging with sensitive data redaction
- In-memory metrics tracking for API latency, throughput, and business indicators
- In-memory error tracking buffer for post-mortem debugging
- ASGI middleware for automated request tracing and response header injection
"""

import datetime
import json
import logging
import re
import secrets
import threading
import time
import traceback
import uuid
from collections import defaultdict, deque
from contextvars import ContextVar
from typing import Any, Dict, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# Context variable for request correlation ID
_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

SENSITIVE_KEY_PATTERNS = {
    "password", "token", "password_hash", "new_password",
    "authorization", "secret", "credentials", "api_key",
    "access_token", "refresh_token", "private_key",
}

BEARER_PATTERN = re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE)


def get_correlation_id() -> str:
    """Retrieve the current request's correlation ID or empty string."""
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str):
    """Set the correlation ID for the current context."""
    return _correlation_id_ctx.set(correlation_id)


def redact_sensitive_data(data: Any) -> Any:
    """Recursively scrub sensitive keys and credential patterns from objects."""
    if isinstance(data, dict):
        scrubbed = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEY_PATTERNS):
                scrubbed[key] = "[REDACTED]"
            else:
                scrubbed[key] = redact_sensitive_data(value)
        return scrubbed
    elif isinstance(data, (list, tuple)):
        scrubbed_list = [redact_sensitive_data(item) for item in data]
        return type(data)(scrubbed_list)
    elif isinstance(data, str):
        # Scrub Bearer tokens in strings
        return BEARER_PATTERN.sub("Bearer [REDACTED]", data)
    return data


class JSONLogFormatter(logging.Formatter):
    """Formats log records as single-line JSON with correlation IDs and redaction."""

    def format(self, record: logging.LogRecord) -> str:
        # Correlation ID from record attribute or context
        corr_id = getattr(record, "correlation_id", None) or get_correlation_id() or None
        
        # Build structured log payload
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
        }

        if corr_id:
            log_entry["correlation_id"] = corr_id

        # Attach any extra attributes supplied via extra={...}
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "correlation_id",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extras:
            log_entry["extra"] = redact_sensitive_data(extras)

        # Exception traceback formatting
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str)


class ErrorTracker:
    """Thread-safe ring buffer capturing recent production errors."""

    def __init__(self, max_size: int = 100):
        self._max_size = max_size
        self._errors: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def record_error(
        self,
        error_type: str,
        message: str,
        status_code: int = 500,
        path: Optional[str] = None,
        method: Optional[str] = None,
        correlation_id: Optional[str] = None,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cid = correlation_id or get_correlation_id() or secrets.token_urlsafe(12)
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "correlation_id": cid,
            "error_type": error_type,
            "message": redact_sensitive_data(message),
            "status_code": status_code,
            "path": path,
            "method": method,
            "stack_trace": stack_trace,
            "context": redact_sensitive_data(context or {}),
        }
        with self._lock:
            self._errors.append(entry)
        return entry

    def get_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._errors)
        items.reverse()  # Newest first
        return items[:limit]

    def clear(self):
        with self._lock:
            self._errors.clear()


class MetricsCollector:
    """Thread-safe aggregator for request latencies, status counts, and error tracking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._total_requests = 0
        self._status_counts = {"2xx": 0, "4xx": 0, "5xx": 0, "other": 0}
        self._endpoint_metrics: Dict[str, Dict[str, Any]] = {}

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        endpoint_key = f"{method.upper()} {path}"
        with self._lock:
            self._total_requests += 1

            if 200 <= status_code < 300:
                self._status_counts["2xx"] += 1
            elif 400 <= status_code < 500:
                self._status_counts["4xx"] += 1
            elif 500 <= status_code < 600:
                self._status_counts["5xx"] += 1
            else:
                self._status_counts["other"] += 1

            metrics = self._endpoint_metrics.setdefault(endpoint_key, {
                "count": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "min_duration_ms": float("inf"),
                "max_duration_ms": 0.0,
                "last_duration_ms": 0.0,
                "errors": 0,
            })

            metrics["count"] += 1
            metrics["total_duration_ms"] += duration_ms
            metrics["avg_duration_ms"] = round(metrics["total_duration_ms"] / metrics["count"], 2)
            metrics["min_duration_ms"] = round(min(metrics["min_duration_ms"], duration_ms), 2)
            metrics["max_duration_ms"] = round(max(metrics["max_duration_ms"], duration_ms), 2)
            metrics["last_duration_ms"] = round(duration_ms, 2)
            if status_code >= 400:
                metrics["errors"] += 1

    def get_api_metrics(self) -> Dict[str, Any]:
        with self._lock:
            endpoints = {k: dict(v) for k, v in self._endpoint_metrics.items()}
            status_copy = dict(self._status_counts)
            total = self._total_requests

        return {
            "total_requests": total,
            "status_distribution": status_copy,
            "endpoints": endpoints,
        }

    def reset(self):
        with self._lock:
            self._total_requests = 0
            self._status_counts = {"2xx": 0, "4xx": 0, "5xx": 0, "other": 0}
            self._endpoint_metrics.clear()


# Global singleton instances
global_error_tracker = ErrorTracker(max_size=200)
global_metrics_collector = MetricsCollector()
logger = logging.getLogger("petty_cash.app")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Starlette middleware to manage correlation IDs, trace requests, and capture metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or f"corr-{secrets.token_urlsafe(12)}"
        )
        set_correlation_id(correlation_id)

        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Record metrics
            global_metrics_collector.record_request(method, path, response.status_code, duration_ms)

            # Inject correlation ID and security headers (F-11)
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Log request outcome
            log_data = {
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else None,
            }
            if response.status_code >= 500:
                logger.error(
                    f"{method} {path} failed with status {response.status_code}",
                    extra=log_data,
                )
            elif response.status_code >= 400:
                logger.warning(
                    f"{method} {path} returned client error {response.status_code}",
                    extra=log_data,
                )
            else:
                logger.info(
                    f"{method} {path} completed with status {response.status_code}",
                    extra=log_data,
                )

            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            global_metrics_collector.record_request(method, path, 500, duration_ms)
            stack = traceback.format_exc()

            global_error_tracker.record_error(
                error_type=exc.__class__.__name__,
                message=str(exc),
                status_code=500,
                path=path,
                method=method,
                correlation_id=correlation_id,
                stack_trace=stack,
            )

            logger.critical(
                f"Unhandled exception during {method} {path}: {str(exc)}",
                exc_info=True,
                extra={"correlation_id": correlation_id, "path": path, "method": method},
            )

            err_response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error occurred.",
                    "correlation_id": correlation_id,
                },
            )
            err_response.headers["X-Correlation-ID"] = correlation_id
            return err_response


_RATE_LIMIT_STORE = defaultdict(list)
_RATE_LIMIT_WINDOW = 60.0  # seconds
_RATE_LIMIT_MAX_REQUESTS = 300  # generous 300 req/min per client

_LOGIN_ATTEMPTS = defaultdict(list)
_LOGIN_LOCKOUTS = {}
_LOGIN_WINDOW = 300.0  # 5 minutes
_LOGIN_MAX_FAILED_ATTEMPTS = 5
_LOGIN_LOCKOUT_DURATION = 900.0  # 15 minutes


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window rate limiting to prevent server / database saturation and brute-force attacks."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if (
            path.startswith("/health")
            or path.startswith("/static")
            or path.startswith("/docs")
            or path.startswith("/openapi")
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        client_key = request.client.host if request.client else "127.0.0.1"
        auth_header = request.headers.get("Authorization")
        if auth_header:
            client_key = f"auth:{auth_header[-16:]}"

        now = time.monotonic()

        # Dedicated login brute-force and lockout protection (F-12)
        if path == "/api/auth/login" and request.method == "POST":
            login_key = f"login:{client_key}"
            if login_key in _LOGIN_LOCKOUTS:
                lockout_until = _LOGIN_LOCKOUTS[login_key]
                if now < lockout_until:
                    retry_after = max(1, int(lockout_until - now))
                    logger.warning(f"Login attempt rejected due to active lockout for {login_key}")
                    return JSONResponse(
                        status_code=429,
                        content={"detail": f"Account temporarily locked due to multiple failed login attempts. Retry in {retry_after} seconds."},
                        headers={"Retry-After": str(retry_after)},
                    )
                else:
                    _LOGIN_LOCKOUTS.pop(login_key, None)

            response = await call_next(request)
            if response.status_code in (400, 401):
                attempts = [t for t in _LOGIN_ATTEMPTS[login_key] if now - t < _LOGIN_WINDOW]
                attempts.append(now)
                _LOGIN_ATTEMPTS[login_key] = attempts
                if len(attempts) >= _LOGIN_MAX_FAILED_ATTEMPTS:
                    _LOGIN_LOCKOUTS[login_key] = now + _LOGIN_LOCKOUT_DURATION
                    logger.warning(f"Client {login_key} locked out after {len(attempts)} failed attempts.")
            elif response.status_code == 200:
                _LOGIN_ATTEMPTS.pop(login_key, None)
            return response

        history = _RATE_LIMIT_STORE[client_key]
        _RATE_LIMIT_STORE[client_key] = [t for t in history if now - t < _RATE_LIMIT_WINDOW]
        history = _RATE_LIMIT_STORE[client_key]

        if len(history) >= _RATE_LIMIT_MAX_REQUESTS:
            logger.warning(f"Rate limit exceeded for client {client_key} on {path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."},
                headers={"Retry-After": "10"},
            )

        history.append(now)
        return await call_next(request)


def setup_observability(log_level: str = "INFO"):
    """Configure structured JSON logging for the application and root logger."""
    root_logger = logging.getLogger()
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    # Remove existing handlers to prevent duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    root_logger.addHandler(handler)
    logger.setLevel(level)
