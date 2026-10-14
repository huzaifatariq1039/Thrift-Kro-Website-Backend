import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import (
    AuthAccount,
    AuthActionToken,
    AuthSecurityEvent,
    AuthSession,
    AuthThrottle,
)
from app.models.user import User


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


ACCESS_TOKEN_MINUTES = _bounded_env_int("AUTH_ACCESS_TOKEN_MINUTES", 15, 5, 15)
REFRESH_TOKEN_DAYS = _bounded_env_int("AUTH_REFRESH_TOKEN_DAYS", 30, 1, 90)
EMAIL_VERIFICATION_HOURS = 24
PASSWORD_RESET_MINUTES = 30


class AuthenticationError(ValueError):
    pass


class RateLimitExceeded(AuthenticationError):
    def __init__(self, retry_after: int):
        super().__init__("Too many authentication attempts")
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True)
class AuthContext:
    user: User
    account: AuthAccount
    session: AuthSession
    claims: dict[str, Any]


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def hash_secret(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def privacy_hash(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return hash_secret(normalized) if normalized else None


def record_security_event(
    db: Session,
    event_type: str,
    success: bool,
    *,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuthSecurityEvent(
            user_id=user_id,
            event_type=event_type,
            success=success,
            ip_hash=privacy_hash(ip_address),
            user_agent_hash=privacy_hash(user_agent),
            details=details or {},
        )
    )


def ensure_auth_account(
    db: Session,
    user_id: uuid.UUID,
    *,
    email_verified: bool = False,
    lock: bool = False,
) -> AuthAccount:
    query = db.query(AuthAccount).filter(AuthAccount.user_id == user_id)
    if lock:
        query = query.with_for_update()
    account = query.one_or_none()
    if account is None:
        now = utcnow()
        account = AuthAccount(
            user_id=user_id,
            auth_version=1,
            email_verified_at=now if email_verified else None,
        )
        db.add(account)
        db.flush()
    elif email_verified and account.email_verified_at is None:
        account.email_verified_at = utcnow()
    return account


def consume_rate_limit(
    db: Session,
    *,
    scope: str,
    key: str,
    limit: int,
    window_seconds: int,
    block_seconds: int,
) -> None:
    now = utcnow()
    key_hash = hash_secret(key.strip().lower())
    db.execute(
        insert(AuthThrottle)
        .values(
            scope=scope,
            key_hash=key_hash,
            window_started_at=now,
            attempts=0,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["scope", "key_hash"])
    )
    throttle = (
        db.query(AuthThrottle)
        .filter(AuthThrottle.scope == scope, AuthThrottle.key_hash == key_hash)
        .with_for_update()
        .one()
    )

    if throttle.blocked_until and _normalize_datetime(throttle.blocked_until) > now:
        retry_after = int((_normalize_datetime(throttle.blocked_until) - now).total_seconds())
        db.commit()
        raise RateLimitExceeded(retry_after)

    window_age = (now - _normalize_datetime(throttle.window_started_at)).total_seconds()
    if window_age >= window_seconds:
        throttle.window_started_at = now
        throttle.attempts = 0
        throttle.blocked_until = None

    throttle.attempts += 1
    throttle.updated_at = now
    blocked = throttle.attempts > limit
    if blocked:
        throttle.blocked_until = now + timedelta(seconds=block_seconds)
    db.commit()

    if blocked:
        raise RateLimitExceeded(block_seconds)


def clear_rate_limit(db: Session, *, scope: str, key: str) -> None:
    db.query(AuthThrottle).filter(
        AuthThrottle.scope == scope,
        AuthThrottle.key_hash == hash_secret(key.strip().lower()),
    ).delete(synchronize_session=False)
    db.commit()


def _encode_access_token(user_id: uuid.UUID, session_id: uuid.UUID, auth_version: int) -> str:
    now = utcnow()
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    claims = {
        "sub": str(user_id),
        "sid": str(session_id),
        "ver": auth_version,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _new_session(
    user_id: uuid.UUID,
    *,
    family_id: uuid.UUID | None,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[AuthSession, str]:
    now = utcnow()
    raw_refresh_token = secrets.token_urlsafe(48)
    session = AuthSession(
        id=uuid.uuid4(),
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        refresh_token_hash=hash_secret(raw_refresh_token),
        ip_hash=privacy_hash(ip_address),
        user_agent_hash=privacy_hash(user_agent),
        created_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    return session, raw_refresh_token


def issue_session(
    db: Session,
    user: User,
    *,
    ip_address: str | None,
    user_agent: str | None,
    event_type: str = "login_succeeded",
) -> TokenPair:
    account = ensure_auth_account(db, user.id, lock=True)
    session, raw_refresh_token = _new_session(
        user.id,
        family_id=None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    account.last_login_at = utcnow()
    db.add(session)
    record_security_event(
        db,
        event_type,
        True,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"session_id": str(session.id)},
    )
    db.commit()
    return TokenPair(
        access_token=_encode_access_token(user.id, session.id, account.auth_version),
        refresh_token=raw_refresh_token,
        expires_in=ACCESS_TOKEN_MINUTES * 60,
    )


def validate_access_token(db: Session, token: str) -> AuthContext:
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if claims.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        user_id = uuid.UUID(claims["sub"])
        session_id = uuid.UUID(claims["sid"])
        auth_version = int(claims["ver"])
    except (JWTError, KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired access token") from exc

    session = db.get(AuthSession, session_id)
    account = db.get(AuthAccount, user_id)
    user = db.get(User, user_id)
    now = utcnow()
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or _normalize_datetime(session.expires_at) <= now
        or account is None
        or account.auth_version != auth_version
        or user is None
        or not user.is_active
    ):
        raise AuthenticationError("Access session is no longer valid")
    return AuthContext(user=user, account=account, session=session, claims=claims)


def rotate_refresh_token(
    db: Session,
    raw_refresh_token: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenPair:
    now = utcnow()
    session = (
        db.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == hash_secret(raw_refresh_token))
        .with_for_update()
        .one_or_none()
    )
    if session is None:
        record_security_event(
            db,
            "refresh_failed",
            False,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "unknown_token"},
        )
        db.commit()
        raise AuthenticationError("Invalid refresh token")

    account = ensure_auth_account(db, session.user_id, lock=True)
    user = db.get(User, session.user_id)
    if session.revoked_at is not None:
        if session.revoke_reason == "rotated":
            db.query(AuthSession).filter(
                AuthSession.family_id == session.family_id,
                AuthSession.revoked_at.is_(None),
            ).update(
                {"revoked_at": now, "revoke_reason": "refresh_reuse"},
                synchronize_session=False,
            )
            account.auth_version += 1
            record_security_event(
                db,
                "refresh_reuse_detected",
                False,
                user_id=session.user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"session_family": str(session.family_id)},
            )
            db.commit()
        raise AuthenticationError("Refresh token has been revoked")

    if _normalize_datetime(session.expires_at) <= now or user is None or not user.is_active:
        session.revoked_at = now
        session.revoke_reason = "expired" if user is not None else "invalid_user"
        record_security_event(
            db,
            "refresh_failed",
            False,
            user_id=session.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": session.revoke_reason},
        )
        db.commit()
        raise AuthenticationError("Refresh token is expired or invalid")

    session.revoked_at = now
    session.revoke_reason = "rotated"
    session.last_used_at = now
    replacement, new_raw_token = _new_session(
        session.user_id,
        family_id=session.family_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(replacement)
    record_security_event(
        db,
        "refresh_rotated",
        True,
        user_id=session.user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"previous_session_id": str(session.id), "session_id": str(replacement.id)},
    )
    db.commit()
    return TokenPair(
        access_token=_encode_access_token(user.id, replacement.id, account.auth_version),
        refresh_token=new_raw_token,
        expires_in=ACCESS_TOKEN_MINUTES * 60,
    )


def revoke_session(
    db: Session,
    context: AuthContext,
    *,
    reason: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    if context.session.revoked_at is None:
        context.session.revoked_at = utcnow()
        context.session.revoke_reason = reason
    record_security_event(
        db,
        "session_revoked",
        True,
        user_id=context.user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"session_id": str(context.session.id), "reason": reason},
    )
    db.commit()


def revoke_all_sessions(
    db: Session,
    user_id: uuid.UUID,
    *,
    reason: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    now = utcnow()
    account = ensure_auth_account(db, user_id, lock=True)
    account.auth_version += 1
    db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    ).update(
        {"revoked_at": now, "revoke_reason": reason},
        synchronize_session=False,
    )
    record_security_event(
        db,
        "all_sessions_revoked",
        True,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"reason": reason},
    )
    db.commit()


def create_action_token(
    db: Session,
    user_id: uuid.UUID,
    purpose: str,
) -> str:
    now = utcnow()
    ttl = (
        timedelta(hours=EMAIL_VERIFICATION_HOURS)
        if purpose == "verify_email"
        else timedelta(minutes=PASSWORD_RESET_MINUTES)
    )
    db.query(AuthActionToken).filter(
        AuthActionToken.user_id == user_id,
        AuthActionToken.purpose == purpose,
        AuthActionToken.consumed_at.is_(None),
    ).update({"consumed_at": now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(48)
    db.add(
        AuthActionToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_secret(raw_token),
            created_at=now,
            expires_at=now + ttl,
        )
    )
    return raw_token


def consume_action_token(db: Session, raw_token: str, purpose: str) -> tuple[User, AuthAccount]:
    now = utcnow()
    action = (
        db.query(AuthActionToken)
        .filter(
            AuthActionToken.token_hash == hash_secret(raw_token),
            AuthActionToken.purpose == purpose,
        )
        .with_for_update()
        .one_or_none()
    )
    if (
        action is None
        or action.consumed_at is not None
        or _normalize_datetime(action.expires_at) <= now
    ):
        raise AuthenticationError("Action token is invalid or expired")
    user = db.get(User, action.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Action token is invalid or expired")
    action.consumed_at = now
    return user, ensure_auth_account(db, user.id, lock=True)
