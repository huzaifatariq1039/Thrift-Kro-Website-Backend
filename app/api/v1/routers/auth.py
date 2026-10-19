from datetime import datetime, timezone
import os
from uuid import UUID

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import func
from sqlalchemy.orm import Session

import app.crud.user as crud_user
from app.api.deps import get_current_auth_context, get_db
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.auth import AuthSession
from app.models.user import User
from app.schemas.auth import (
    ActionTokenRequest,
    AuthMessageResponse,
    AuthTokenResponse,
    EmailActionRequest,
    PasswordResetConfirmRequest,
    RefreshTokenRequest,
    SessionResponse,
)
from app.schemas.user import GoogleAuthRequest, PublicUserCreate, UserResponse
from app.services.auth_email import send_auth_action_email
from app.services.auth_lifecycle import (
    AuthContext,
    AuthenticationError,
    RateLimitExceeded,
    clear_rate_limit,
    consume_action_token,
    consume_rate_limit,
    create_action_token,
    ensure_auth_account,
    issue_session,
    record_security_event,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    utcnow,
    REFRESH_TOKEN_DAYS,
)
from app.services.provider_resilience import (
    ProviderCircuitBreaker,
    ProviderCircuitOpenError,
    RetryPolicy,
    call_with_resilience,
    is_transient_requests_error,
)


router = APIRouter()
_DUMMY_PASSWORD_HASH = get_password_hash("InvalidPassword1!")
_GOOGLE_IDENTITY_CIRCUIT = ProviderCircuitBreaker(
    "google_identity",
    failure_threshold=5,
    recovery_seconds=30,
)
_GOOGLE_RETRY_POLICY = RetryPolicy(max_attempts=2, base_delay_seconds=0.1)
_REFRESH_COOKIE_NAME = "thrift_kro_refresh"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


class _BoundedGoogleRequest(google_requests.Request):
    """Cap certificate-fetch latency used while validating Google ID tokens."""

    def __call__(
        self,
        url,
        method="GET",
        body=None,
        headers=None,
        timeout=5,
        **kwargs,
    ):
        bounded_timeout = min(timeout, 5) if isinstance(timeout, (int, float)) else 5
        return super().__call__(
            url=url,
            method=method,
            body=body,
            headers=headers,
            timeout=bounded_timeout,
            **kwargs,
        )


def _request_identity(request: Request) -> tuple[str, str]:
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")[:512]
    return ip_address, user_agent


def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()


def _consume_limit(db: Session, **kwargs) -> None:
    try:
        consume_rate_limit(db, **kwargs)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def _token_response(pair, *, expose_refresh_token: bool = True) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token if expose_refresh_token else None,
        expires_in=pair.expires_in,
    )


def _remember_session(request: Request) -> bool:
    return request.headers.get("x-remember-session", "").strip().lower() == "true"


def _uses_cookie_session(request: Request) -> bool:
    return request.headers.get("x-session-transport", "").strip().lower() == "cookie"


def _refresh_cookie_secure() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def _set_refresh_cookie(response: Response, request: Request, refresh_token: str) -> None:
    secure = _refresh_cookie_secure()
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60 if _remember_session(request) else None,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path=_REFRESH_COOKIE_PATH,
    )


def _delete_refresh_cookie(response: Response) -> None:
    secure = _refresh_cookie_secure()
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path=_REFRESH_COOKIE_PATH,
    )


def _invalid_refresh_response() -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Invalid refresh token"},
    )
    _delete_refresh_cookie(response)
    return response


def _fetch_google_userinfo(access_token: str) -> dict:
    def request_userinfo() -> dict:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    return call_with_resilience(
        request_userinfo,
        circuit=_GOOGLE_IDENTITY_CIRCUIT,
        retry_if=is_transient_requests_error,
        policy=_GOOGLE_RETRY_POLICY,
    )


def _is_transient_google_error(exc: Exception) -> bool:
    return isinstance(exc, TransportError) or is_transient_requests_error(exc)


def _verify_google_id_token(raw_token: str) -> dict:
    return call_with_resilience(
        lambda: id_token.verify_oauth2_token(
            raw_token,
            _BoundedGoogleRequest(),
            settings.GOOGLE_CLIENT_ID,
        ),
        circuit=_GOOGLE_IDENTITY_CIRCUIT,
        retry_if=_is_transient_google_error,
        policy=_GOOGLE_RETRY_POLICY,
    )


def _deliver_action_email(
    db: Session,
    user: User,
    purpose: str,
    token: str,
    *,
    ip_address: str,
    user_agent: str,
) -> None:
    delivered = send_auth_action_email(user.email, purpose, token)
    record_security_event(
        db,
        "auth_email_delivery",
        delivered,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"purpose": purpose},
    )
    db.commit()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user: PublicUserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="register_ip",
        key=ip_address,
        limit=5,
        window_seconds=3600,
        block_seconds=3600,
    )
    db_user = _get_user_by_email(db, str(user.email))
    if db_user:
        record_security_event(
            db,
            "registration_failed",
            False,
            user_id=db_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "email_exists"},
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = crud_user.create_user(db=db, user=user)
    ensure_auth_account(db, db_user.id, email_verified=False)
    raw_token = create_action_token(db, db_user.id, "verify_email")
    record_security_event(
        db,
        "registration_succeeded",
        True,
        user_id=db_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    _deliver_action_email(
        db,
        db_user,
        "verify_email",
        raw_token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return db_user


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    response_model_exclude_none=True,
)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    email = form_data.username.strip().lower()
    _consume_limit(
        db,
        scope="login_ip",
        key=ip_address,
        limit=100,
        window_seconds=900,
        block_seconds=900,
    )
    _consume_limit(
        db,
        scope="login_account",
        key=email,
        limit=5,
        window_seconds=900,
        block_seconds=900,
    )

    user = _get_user_by_email(db, email)
    password_hash = user.hashed_password if user and user.hashed_password else _DUMMY_PASSWORD_HASH
    password_matches = verify_password(form_data.password, password_hash)
    if user is None or not user.hashed_password or not password_matches:
        record_security_event(
            db,
            "login_failed",
            False,
            user_id=user.id if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        record_security_event(
            db,
            "login_failed",
            False,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "inactive"},
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Account is inactive")

    clear_rate_limit(db, scope="login_account", key=email)
    account = ensure_auth_account(db, user.id)
    if account.email_verified_at is None:
        record_security_event(
            db,
            "login_failed",
            False,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "email_unverified"},
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Email verification is required")

    pair = issue_session(
        db,
        user,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    cookie_session = _uses_cookie_session(request)
    if cookie_session:
        _set_refresh_cookie(response, request, pair.refresh_token)
    return _token_response(pair, expose_refresh_token=not cookie_session)


@router.post(
    "/google",
    response_model=AuthTokenResponse,
    response_model_exclude_none=True,
)
def google_auth(
    body: GoogleAuthRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="google_ip",
        key=ip_address,
        limit=30,
        window_seconds=900,
        block_seconds=900,
    )
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    try:
        if body.id_token.count(".") == 2:
            idinfo = _verify_google_id_token(body.id_token)
        else:
            idinfo = _fetch_google_userinfo(body.id_token)
    except ProviderCircuitOpenError as exc:
        record_security_event(
            db,
            "google_login_failed",
            False,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "provider_unavailable"},
        )
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Google authentication is temporarily unavailable",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except (requests.RequestException, TransportError) as exc:
        provider_unavailable = _is_transient_google_error(exc)
        reason = "provider_unavailable" if provider_unavailable else "invalid_provider_token"
        record_security_event(
            db,
            "google_login_failed",
            False,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": reason},
        )
        db.commit()
        raise HTTPException(
            status_code=503 if provider_unavailable else 401,
            detail=(
                "Google authentication is temporarily unavailable"
                if provider_unavailable
                else "Invalid Google token"
            ),
        ) from exc
    except ValueError as exc:
        record_security_event(
            db,
            "google_login_failed",
            False,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "invalid_provider_token"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    google_id = idinfo.get("sub")
    email = idinfo.get("email")
    email_verified_value = idinfo.get("email_verified", idinfo.get("verified_email", False))
    email_verified = email_verified_value is True or str(email_verified_value).lower() == "true"
    if not google_id or not email or not email_verified:
        raise HTTPException(status_code=401, detail="Google email must be verified")

    user = crud_user.get_user_by_google_id(db, google_id=google_id)
    if not user:
        user = _get_user_by_email(db, email)
        if user:
            crud_user.link_google_account(db, user=user, google_id=google_id)
        else:
            user = crud_user.create_google_user(
                db,
                email=email,
                full_name=idinfo.get("name", "Google User"),
                google_id=google_id,
                avatar_url=idinfo.get("picture"),
                role=body.role,
            )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    ensure_auth_account(db, user.id, email_verified=True)
    db.commit()
    pair = issue_session(
        db,
        user,
        ip_address=ip_address,
        user_agent=user_agent,
        event_type="google_login_succeeded",
    )
    cookie_session = _uses_cookie_session(request)
    if cookie_session:
        _set_refresh_cookie(response, request, pair.refresh_token)
    return _token_response(pair, expose_refresh_token=not cookie_session)


@router.post(
    "/refresh",
    response_model=AuthTokenResponse,
    response_model_exclude_none=True,
)
def refresh_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="refresh_ip",
        key=ip_address,
        limit=60,
        window_seconds=900,
        block_seconds=900,
    )
    raw_refresh_token = (
        body.refresh_token
        if body is not None
        else request.cookies.get(_REFRESH_COOKIE_NAME)
    )
    if not raw_refresh_token:
        return _invalid_refresh_response()
    try:
        pair = rotate_refresh_token(
            db,
            raw_refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except AuthenticationError:
        return _invalid_refresh_response()
    cookie_session = _uses_cookie_session(request) and body is None
    if cookie_session:
        _set_refresh_cookie(response, request, pair.refresh_token)
    return _token_response(pair, expose_refresh_token=not cookie_session)


@router.post("/logout", response_model=AuthMessageResponse)
def logout(
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    revoke_session(
        db,
        context,
        reason="logout",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _delete_refresh_cookie(response)
    return AuthMessageResponse(message="Signed out")


@router.post("/logout-all", response_model=AuthMessageResponse)
def logout_all(
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    revoke_all_sessions(
        db,
        context.user.id,
        reason="logout_all",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _delete_refresh_cookie(response)
    return AuthMessageResponse(message="All sessions signed out")


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == context.user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.created_at.desc())
        .all()
    )
    return [
        SessionResponse(
            id=session.id,
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_used_at=session.last_used_at,
            current=session.id == context.session.id,
        )
        for session in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=AuthMessageResponse)
def delete_session(
    session_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        session.revoke_reason = "user_revoked"
    ip_address, user_agent = _request_identity(request)
    record_security_event(
        db,
        "session_revoked",
        True,
        user_id=context.user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"session_id": str(session.id), "reason": "user_revoked"},
    )
    db.commit()
    return AuthMessageResponse(message="Session revoked")


@router.post("/email-verification/request", response_model=AuthMessageResponse)
def request_email_verification(
    body: EmailActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="verify_ip",
        key=ip_address,
        limit=10,
        window_seconds=3600,
        block_seconds=3600,
    )
    _consume_limit(
        db,
        scope="verify_email",
        key=str(body.email),
        limit=3,
        window_seconds=3600,
        block_seconds=3600,
    )
    user = _get_user_by_email(db, str(body.email))
    if user:
        account = ensure_auth_account(db, user.id)
        if account.email_verified_at is None:
            raw_token = create_action_token(db, user.id, "verify_email")
            record_security_event(
                db,
                "email_verification_requested",
                True,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.commit()
            _deliver_action_email(
                db,
                user,
                "verify_email",
                raw_token,
                ip_address=ip_address,
                user_agent=user_agent,
            )
    return AuthMessageResponse(
        message="If the account needs verification, a message has been sent"
    )


@router.post("/email-verification/confirm", response_model=AuthMessageResponse)
def confirm_email_verification(
    body: ActionTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="verify_confirm_ip",
        key=ip_address,
        limit=30,
        window_seconds=3600,
        block_seconds=3600,
    )
    try:
        user, account = consume_action_token(db, body.token, "verify_email")
    except AuthenticationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Verification token is invalid or expired") from exc
    account.email_verified_at = utcnow()
    record_security_event(
        db,
        "email_verified",
        True,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return AuthMessageResponse(message="Email verified")


@router.post("/password-reset/request", response_model=AuthMessageResponse)
def request_password_reset(
    body: EmailActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="reset_ip",
        key=ip_address,
        limit=10,
        window_seconds=3600,
        block_seconds=3600,
    )
    _consume_limit(
        db,
        scope="reset_email",
        key=str(body.email),
        limit=3,
        window_seconds=3600,
        block_seconds=3600,
    )
    user = _get_user_by_email(db, str(body.email))
    if user and user.is_active:
        raw_token = create_action_token(db, user.id, "reset_password")
        record_security_event(
            db,
            "password_reset_requested",
            True,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        _deliver_action_email(
            db,
            user,
            "reset_password",
            raw_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    return AuthMessageResponse(
        message="If the account exists, a password reset message has been sent"
    )


@router.post("/password-reset/confirm", response_model=AuthMessageResponse)
def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_address, user_agent = _request_identity(request)
    _consume_limit(
        db,
        scope="reset_confirm_ip",
        key=ip_address,
        limit=30,
        window_seconds=3600,
        block_seconds=3600,
    )
    try:
        user, account = consume_action_token(db, body.token, "reset_password")
    except AuthenticationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired") from exc

    now = utcnow()
    user.hashed_password = get_password_hash(body.new_password)
    account.password_changed_at = now
    account.auth_version += 1
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
    ).update(
        {"revoked_at": now, "revoke_reason": "password_reset"},
        synchronize_session=False,
    )
    record_security_event(
        db,
        "password_reset_completed",
        True,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return AuthMessageResponse(message="Password reset completed")
