"""
auth.py — Enterprise authentication & authorisation for HydroCore
=================================================================
Security features:
  • JWT access tokens (15 min) — sent in Authorization header
  • Refresh tokens (7 days) — httpOnly cookie, rotated on every use
  • bcrypt password hashing (cost factor 12)
  • Role-based access control: admin | analyst | viewer
  • Rate limiting on login endpoint
  • Account lockout after MAX_FAILED_ATTEMPTS consecutive failures
  • Full audit trail (AuditLog table)
  • Refresh-token revocation on logout / password change / deactivation
  • Token-reuse detection (refresh token replay attack mitigation)
"""

import os
import hashlib
import logging
import re
import secrets
import time as _time
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import pyotp
from flask import Blueprint, g, jsonify, make_response, request
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    verify_jwt_in_request,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# ── Tuneable constants ────────────────────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES     = 15
ACCESS_TOKEN_MINS   = 15
REFRESH_TOKEN_DAYS  = 7

# Set by init_auth()
_db      = None
_limiter = None

# ── MFA session store (in-memory, server-local) ───────────────────────────────
_mfa_sessions: dict = {}  # { session_id: { user_id, expires } }

def _create_mfa_session(user_id: int) -> str:
    sid = secrets.token_urlsafe(32)
    _mfa_sessions[sid] = {'user_id': user_id, 'expires': _time.time() + 300}
    # Cleanup stale sessions
    stale = [k for k, v in _mfa_sessions.items() if v['expires'] < _time.time()]
    for k in stale:
        _mfa_sessions.pop(k, None)
    return sid

def _consume_mfa_session(sid: str):
    entry = _mfa_sessions.pop(sid, None)
    if not entry or entry['expires'] < _time.time():
        return None
    return entry['user_id']


# ═════════════════════════════════════════════════════════════════════════════
# Initialisation
# ═════════════════════════════════════════════════════════════════════════════

def init_auth(app, db, limiter):
    """
    Wire up JWT and the rate-limiter.  Call once during app startup, before
    any request is served.
    """
    global _db, _limiter
    _db      = db
    _limiter = limiter

    # JWT secret — persisted to a file so server restarts don't invalidate tokens.
    # In production, override with the JWT_SECRET_KEY environment variable.
    _jwt_secret = os.getenv("JWT_SECRET_KEY")
    if not _jwt_secret:
        _secret_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.jwt_secret')
        if os.path.exists(_secret_file):
            with open(_secret_file, 'r') as _f:
                _jwt_secret = _f.read().strip()
        else:
            _jwt_secret = secrets.token_hex(64)
            with open(_secret_file, 'w') as _f:
                _f.write(_jwt_secret)
    app.config.setdefault("JWT_SECRET_KEY", _jwt_secret)
    app.config["JWT_ACCESS_TOKEN_EXPIRES"]  = timedelta(minutes=ACCESS_TOKEN_MINS)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=REFRESH_TOKEN_DAYS)
    # Tokens are sent in the Authorization header only (cookies handled manually)
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["JWT_HEADER_NAME"]    = "Authorization"
    app.config["JWT_HEADER_TYPE"]    = "Bearer"

    jwt = JWTManager(app)
    return jwt


# ═════════════════════════════════════════════════════════════════════════════
# Database helpers (all private — only called from within this module)
# ═════════════════════════════════════════════════════════════════════════════

def _q(query, params=None, fetch=True, commit=False):
    """Thin wrapper around db.execute_query with sensible defaults."""
    return _db.execute_query(query, params, fetch=fetch, commit=commit)


def _get_user_by_email(email: str):
    try:
        rows = _q(
            "SELECT user_id, username, email, password_hash, role, is_active,"
            "       failed_login_attempts, locked_until, must_change_password, [plan], org_id,"
            "       totp_enabled, totp_secret, is_system_admin, setup_completed"
            " FROM dbo.Users WHERE LOWER(email) = LOWER(?)",
            (email,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "user_id": r[0], "username": r[1], "email": r[2],
            "password_hash": r[3], "role": r[4], "is_active": bool(r[5]),
            "failed_login_attempts": r[6], "locked_until": r[7],
            "must_change_password": bool(r[8]),
            "plan": r[9] or "basic", "org_id": r[10] or 1,
            "totp_enabled": bool(r[11]) if r[11] is not None else False,
            "totp_secret": r[12],
            "is_system_admin": bool(r[13]) if r[13] is not None else False,
            "setup_completed": bool(r[14]) if r[14] is not None else True,
        }
    except Exception:
        rows = _q(
            "SELECT user_id, username, email, password_hash, role, is_active,"
            "       failed_login_attempts, locked_until, must_change_password"
            " FROM dbo.Users WHERE LOWER(email) = LOWER(?)",
            (email,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "user_id": r[0], "username": r[1], "email": r[2],
            "password_hash": r[3], "role": r[4], "is_active": bool(r[5]),
            "failed_login_attempts": r[6], "locked_until": r[7],
            "must_change_password": bool(r[8]),
            "plan": "basic", "org_id": 1,
            "totp_enabled": False, "totp_secret": None,
            "is_system_admin": False, "setup_completed": True,
        }


def _get_user_by_id(user_id: int):
    try:
        rows = _q(
            "SELECT user_id, username, email, role, is_active, must_change_password, [plan], org_id,"
            "       totp_enabled, is_system_admin, setup_completed"
            " FROM dbo.Users WHERE user_id = ?",
            (user_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "user_id": r[0], "username": r[1], "email": r[2],
            "role": r[3], "is_active": bool(r[4]),
            "must_change_password": bool(r[5]),
            "plan": r[6] or "basic", "org_id": r[7] or 1,
            "totp_enabled": bool(r[8]) if r[8] is not None else False,
            "is_system_admin": bool(r[9]) if r[9] is not None else False,
            "setup_completed": bool(r[10]) if r[10] is not None else True,
        }
    except Exception:
        rows = _q(
            "SELECT user_id, username, email, role, is_active, must_change_password"
            " FROM dbo.Users WHERE user_id = ?",
            (user_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "user_id": r[0], "username": r[1], "email": r[2],
            "role": r[3], "is_active": bool(r[4]),
            "must_change_password": bool(r[5]),
            "plan": "basic", "org_id": 1,
            "totp_enabled": False,
            "is_system_admin": False, "setup_completed": True,
        }


def _increment_failed_attempts(user_id: int):
    _q(
        """UPDATE dbo.Users
           SET failed_login_attempts = failed_login_attempts + 1,
               locked_until = CASE
                   WHEN (failed_login_attempts + 1) >= ?
                   THEN DATEADD(MINUTE, ?, GETDATE())
                   ELSE locked_until
               END
           WHERE user_id = ?""",
        (MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES, user_id),
        fetch=False,
    )


def _reset_failed_attempts(user_id: int):
    _q(
        "UPDATE dbo.Users"
        " SET failed_login_attempts = 0, locked_until = NULL, last_login = GETDATE()"
        " WHERE user_id = ?",
        (user_id,), fetch=False,
    )


def _store_refresh_token(user_id: int, token_hash: str, ip: str, ua: str):
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)
    _q(
        "INSERT INTO dbo.RefreshTokens (user_id, token_hash, expires_at, ip_address, user_agent)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, token_hash, expires,
         (ip or "")[:45], (ua or "")[:500]),
        fetch=False,
    )


def _is_refresh_token_valid(token_hash: str) -> bool:
    rows = _q(
        "SELECT 1 FROM dbo.RefreshTokens"
        " WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > GETDATE()",
        (token_hash,),
    )
    return bool(rows)


def _revoke_refresh_token(token_hash: str):
    _q(
        "UPDATE dbo.RefreshTokens SET revoked_at = GETDATE() WHERE token_hash = ?",
        (token_hash,), fetch=False,
    )


def _revoke_all_user_tokens(user_id: int):
    _q(
        "UPDATE dbo.RefreshTokens SET revoked_at = GETDATE()"
        " WHERE user_id = ? AND revoked_at IS NULL",
        (user_id,), fetch=False,
    )


def _audit(user_id, action: str, resource: str = None,
           details: str = None, success: bool = True):
    """Write one row to AuditLog.  Never raises — failures are logged only."""
    try:
        ip = (request.remote_addr or "")[:45] if request else ""
        ua = (request.headers.get("User-Agent", "") if request else "")[:500]
        _q(
            "INSERT INTO dbo.AuditLog"
            " (user_id, action, resource, details, ip_address, user_agent, success)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, action[:100],
             (resource or "")[:255],
             (str(details) if details else "")[:1000],
             ip, ua, 1 if success else 0),
            fetch=False,
        )
    except Exception as exc:
        logger.warning("Audit log write failed: %s", exc)


def _generate_account_setup_token(user_id: int) -> tuple:
    """Generate a new setup token + TOTP secret, store them on the user, return both."""
    setup_token   = secrets.token_urlsafe(48)
    totp_secret   = pyotp.random_base32()
    expires       = datetime.now(timezone.utc) + timedelta(hours=72)
    try:
        _q(
            "UPDATE dbo.Users SET account_setup_token = ?, setup_token_expires = ?,"
            " totp_secret = ?, totp_enabled = 0, is_active = 0, setup_completed = 0"
            " WHERE user_id = ?",
            (setup_token, expires, totp_secret, user_id), fetch=False,
        )
    except Exception as exc:
        logger.error('_generate_account_setup_token failed: %s', exc)
        raise
    return setup_token, totp_secret


def _validate_password(password: str):
    """
    Returns an error string if the password doesn't meet policy, else None.
    Policy: ≥8 chars, at least one uppercase, lowercase, digit, special char.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]", password):
        return "Password must contain at least one special character."
    return None


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _set_refresh_cookie(response, raw_token: str):
    is_prod = os.getenv("FLASK_ENV", "development") == "production"
    response.set_cookie(
        "hydrocore_refresh",
        raw_token,
        httponly=True,
        secure=is_prod,
        samesite="Strict",
        max_age=REFRESH_TOKEN_DAYS * 24 * 3600,
        path="/api/auth/refresh",   # only sent to the refresh endpoint
    )


def _clear_refresh_cookie(response):
    response.set_cookie(
        "hydrocore_refresh", "",
        expires=0, httponly=True, path="/api/auth/refresh",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Access-control decorator
# ═════════════════════════════════════════════════════════════════════════════

def require_auth(roles=None):
    """
    Decorator to protect Flask routes with JWT authentication.

    Usage::

        @app.route("/api/data")
        @require_auth()                          # any authenticated user
        def get_data(): ...

        @app.route("/api/upload", methods=["POST"])
        @require_auth(roles=["admin", "analyst"])
        def upload(): ...

    Sets ``g.current_user_id``, ``g.current_user_role``, ``g.current_username``
    for use inside the route function.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                verify_jwt_in_request()
            except Exception:
                return jsonify({
                    "success": False,
                    "error": "Authentication required. Please log in.",
                    "error_code": "UNAUTHORIZED",
                }), 401

            claims   = get_jwt()
            user_id  = int(get_jwt_identity())
            role     = claims.get("role", "viewer")
            username = claims.get("username", "")

            if roles and role not in roles:
                _audit(user_id, "ACCESS_DENIED", request.path,
                       f"Role '{role}' not in {roles}", success=False)
                return jsonify({
                    "success": False,
                    "error": "You do not have permission to perform this action.",
                    "error_code": "FORBIDDEN",
                }), 403

            g.current_user_id   = user_id
            g.current_user_role = role
            g.current_username  = username
            g.current_user_plan = claims.get("plan", "basic")
            g.current_user_org_id = int(claims.get("org_id", 1))
            return f(*args, **kwargs)

        return decorated
    return decorator


# ═════════════════════════════════════════════════════════════════════════════
# Auth endpoints
# ═════════════════════════════════════════════════════════════════════════════

@auth_bp.route("/api/auth/setup", methods=["POST"])
def setup_first_admin():
    """
    One-time bootstrap: creates the very first admin account.
    Permanently disabled once any user exists.
    """
    rows = _q("SELECT COUNT(*) FROM dbo.Users")
    if rows and rows[0][0] > 0:
        return jsonify({"success": False, "error": "System already configured."}), 403

    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    org_name = (data.get("org_name") or "Default").strip()

    if not all([username, email, password]):
        return jsonify({"success": False,
                        "error": "username, email and password are required."}), 400

    err = _validate_password(password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    # Create the default organization first (gracefully handle missing table)
    org_id = 1
    try:
        org_rows = _q("SELECT TOP 1 org_id FROM dbo.Organizations")
        if org_rows:
            org_id = org_rows[0][0]
        else:
            org_result = _q(
                "INSERT INTO dbo.Organizations (name, [plan]) OUTPUT INSERTED.org_id VALUES (?, 'pro')",
                (org_name,), fetch=True, commit=True,
            )
            if org_result:
                org_id = org_result[0][0]
    except Exception:
        org_id = 1  # Organizations table not yet created — use default

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    try:
        result = _q(
            "INSERT INTO dbo.Users (username, email, password_hash, role, org_id)"
            " OUTPUT INSERTED.user_id VALUES (?, ?, ?, 'admin', ?)",
            (username, email, pw_hash, org_id),
            fetch=True, commit=True,
        )
    except Exception:
        result = _q(
            "INSERT INTO dbo.Users (username, email, password_hash, role)"
            " OUTPUT INSERTED.user_id VALUES (?, ?, ?, 'admin')",
            (username, email, pw_hash),
            fetch=True, commit=True,
        )
    if not result:
        return jsonify({"success": False, "error": "Failed to create admin user."}), 500

    _audit(result[0][0], "SETUP", "auth", f"First admin '{username}' created in org {org_id}")
    return jsonify({
        "success": True,
        "message": f"Admin user '{username}' created. You can now log in.",
        "org_id": org_id,
    }), 201


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    """Authenticate a user and return an access token + refresh cookie."""
    data     = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"success": False,
                        "error": "Email and password are required."}), 400

    user = _get_user_by_email(email)

    # Always same error to prevent user-enumeration
    GENERIC_ERR = "Invalid email or password."

    if not user:
        _audit(None, "LOGIN_FAILED", "auth",
               f"Unknown email: {email}", success=False)
        return jsonify({"success": False, "error": GENERIC_ERR}), 401

    # Account lockout check
    if user["locked_until"]:
        lu = user["locked_until"]
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lu:
            remaining = max(1, int((lu - datetime.now(timezone.utc)).total_seconds() / 60))
            return jsonify({
                "success": False,
                "error": (f"Account locked due to too many failed attempts. "
                          f"Try again in {remaining} minute(s)."),
                "error_code": "ACCOUNT_LOCKED",
            }), 423

    # Password check
    try:
        valid = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
    except Exception:
        valid = False

    if not valid:
        _increment_failed_attempts(user["user_id"])
        _audit(user["user_id"], "LOGIN_FAILED", "auth", "Wrong password", success=False)
        attempts_left = max(0, MAX_FAILED_ATTEMPTS - (user["failed_login_attempts"] + 1))
        msg = GENERIC_ERR
        if attempts_left == 0:
            msg = (f"Account locked for {LOCKOUT_MINUTES} minutes "
                   "due to too many failed attempts.")
        elif attempts_left <= 2:
            msg = f"{GENERIC_ERR} {attempts_left} attempt(s) remaining."
        return jsonify({"success": False, "error": msg}), 401

    if not user["is_active"]:
        _audit(user["user_id"], "LOGIN_FAILED", "auth", "Inactive account", success=False)
        return jsonify({
            "success": False,
            "error": "Account deactivated. Contact your administrator.",
        }), 403

    # Org-level suspension check
    if not user.get("is_system_admin") and user.get("org_id"):
        try:
            org_rows = _q(
                "SELECT is_active FROM dbo.Organizations WHERE org_id = ?",
                (user["org_id"],),
            )
            if org_rows and not org_rows[0][0]:
                _audit(user["user_id"], "LOGIN_FAILED", "auth",
                       "Organisation suspended", success=False)
                return jsonify({
                    "success": False,
                    "error": "Your organisation has been suspended. Contact HydroCore support.",
                    "error_code": "ORG_SUSPENDED",
                }), 403
        except Exception:
            pass  # If the check fails, don't block login

    # Account setup not completed
    if not user.get('setup_completed', True):
        return jsonify({
            'success': False,
            'error': 'Your account has not been activated yet. Please check your email for the setup link.',
            'error_code': 'SETUP_PENDING',
        }), 403

    # 2FA required
    if user.get('totp_enabled') and user.get('totp_secret'):
        mfa_sid = _create_mfa_session(user['user_id'])
        _audit(user['user_id'], 'LOGIN_2FA_PENDING', 'auth', 'Password correct, 2FA required')
        return jsonify({'success': True, 'requires_2fa': True, 'mfa_session_id': mfa_sid}), 200

    # Success
    _reset_failed_attempts(user["user_id"])

    claims        = {"role": user["role"], "username": user["username"],
                     "plan": user.get("plan", "basic"), "org_id": user.get("org_id", 1),
                     "is_system_admin": user.get("is_system_admin", False)}
    access_token  = create_access_token(identity=str(user["user_id"]), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(user["user_id"]))

    _store_refresh_token(
        user["user_id"], _hash_token(refresh_token),
        request.remote_addr, request.headers.get("User-Agent", ""),
    )
    _audit(user["user_id"], "LOGIN", "auth", "Successful login")

    response = make_response(jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "user_id":              user["user_id"],
            "username":             user["username"],
            "email":                user["email"],
            "role":                 user["role"],
            "plan":                 user.get("plan", "basic"),
            "org_id":               user.get("org_id", 1),
            "must_change_password": user["must_change_password"],
            "is_system_admin":      user.get("is_system_admin", False),
        },
    }))
    _set_refresh_cookie(response, refresh_token)
    return response, 200


@auth_bp.route("/api/auth/refresh", methods=["POST"])
def refresh():
    """
    Exchange a refresh token for a new access token.
    Token is accepted from the X-Refresh-Token header (per-tab sessionStorage)
    or the legacy httpOnly cookie (fallback for single-user flows).
    The refresh token is rotated on every call.
    """
    raw_token = (
        request.headers.get("X-Refresh-Token")
        or request.cookies.get("hydrocore_refresh")
    )
    if not raw_token:
        return jsonify({"success": False, "error": "No session found.",
                        "error_code": "UNAUTHORIZED"}), 401

    # Decode to extract user_id without going through JWTManager (avoids issues
    # when no Authorization header is present)
    try:
        decoded = decode_token(raw_token)
        if decoded.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        user_id = int(decoded["sub"])
    except Exception as exc:
        logger.warning("Refresh token decode failed: %s", exc)
        return jsonify({"success": False, "error": "Invalid session.",
                        "error_code": "UNAUTHORIZED"}), 401

    token_hash = _hash_token(raw_token)

    # Revocation / replay-attack check
    if not _is_refresh_token_valid(token_hash):
        # Token is expired, revoked, or from a duplicated browser tab.
        # Return 401 so the tab re-authenticates — do NOT revoke all sessions,
        # which would incorrectly log out other valid tabs sharing the same user.
        _audit(user_id, "TOKEN_INVALID", "auth",
               "Refresh token not found or revoked", success=False)
        response = make_response(jsonify({
            "success": False,
            "error": "Session expired. Please log in again.",
            "error_code": "UNAUTHORIZED",
        }))
        _clear_refresh_cookie(response)
        return response, 401

    user = _get_user_by_id(user_id)
    if not user or not user["is_active"]:
        _revoke_refresh_token(token_hash)
        response = make_response(jsonify({
            "success": False, "error": "Account inactive.",
            "error_code": "UNAUTHORIZED",
        }))
        _clear_refresh_cookie(response)
        return response, 401

    # Rotate
    _revoke_refresh_token(token_hash)

    claims            = {"role": user["role"], "username": user["username"],
                         "plan": user.get("plan", "basic"), "org_id": user.get("org_id", 1),
                         "is_system_admin": user.get("is_system_admin", False)}
    new_access_token  = create_access_token(identity=str(user_id), additional_claims=claims)
    new_refresh_token = create_refresh_token(identity=str(user_id))

    _store_refresh_token(
        user_id, _hash_token(new_refresh_token),
        request.remote_addr, request.headers.get("User-Agent", ""),
    )

    response = make_response(jsonify({
        "success": True,
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "user": {
            "user_id":              user["user_id"],
            "username":             user["username"],
            "email":                user["email"],
            "role":                 user["role"],
            "plan":                 user.get("plan", "basic"),
            "org_id":               user.get("org_id", 1),
            "must_change_password": user["must_change_password"],
            "is_system_admin":      user.get("is_system_admin", False),
        },
    }))
    _set_refresh_cookie(response, new_refresh_token)
    return response, 200


@auth_bp.route("/api/auth/logout", methods=["POST"])
@require_auth()
def logout():
    """Revoke the refresh token and clear the cookie."""
    raw_token = (
        request.headers.get("X-Refresh-Token")
        or request.cookies.get("hydrocore_refresh")
    )
    if raw_token:
        _revoke_refresh_token(_hash_token(raw_token))

    _audit(g.current_user_id, "LOGOUT", "auth")

    response = make_response(jsonify({"success": True,
                                      "message": "Logged out successfully."}))
    _clear_refresh_cookie(response)
    return response, 200


@auth_bp.route("/api/auth/me", methods=["GET"])
@require_auth()
def get_me():
    """Return the current user's profile."""
    user = _get_user_by_id(g.current_user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found."}), 404
    return jsonify({"success": True, "user": user}), 200


@auth_bp.route("/api/auth/change-password", methods=["POST"])
@require_auth()
def change_password():
    """Allow a user to change their own password."""
    data             = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password     = data.get("new_password") or ""

    if not current_password or not new_password:
        return jsonify({"success": False,
                        "error": "current_password and new_password are required."}), 400

    err = _validate_password(new_password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    rows = _q("SELECT password_hash FROM dbo.Users WHERE user_id = ?",
              (g.current_user_id,))
    if not rows:
        return jsonify({"success": False, "error": "User not found."}), 404

    if not bcrypt.checkpw(current_password.encode(), rows[0][0].encode()):
        _audit(g.current_user_id, "CHANGE_PASSWORD_FAILED", "auth",
               "Wrong current password", success=False)
        return jsonify({"success": False,
                        "error": "Current password is incorrect."}), 401

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()
    _q("UPDATE dbo.Users SET password_hash = ?, must_change_password = 0"
       " WHERE user_id = ?",
       (new_hash, g.current_user_id), fetch=False)

    # Revoke all refresh tokens — forces re-login on all other devices
    _revoke_all_user_tokens(g.current_user_id)
    _audit(g.current_user_id, "CHANGE_PASSWORD", "auth", "Password changed")

    response = make_response(jsonify({
        "success": True,
        "message": "Password changed. Please log in again.",
    }))
    _clear_refresh_cookie(response)
    return response, 200


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    """Public self-registration — creates a Basic-plan Viewer account, then auto-logs in."""
    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not all([username, email, password]):
        return jsonify({"success": False,
                        "error": "username, email and password are required."}), 400

    err = _validate_password(password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    existing = _q(
        "SELECT 1 FROM dbo.Users WHERE LOWER(email) = ? OR LOWER(username) = ?",
        (email, username.lower()),
    )
    if existing:
        return jsonify({"success": False,
                        "error": "Username or email already exists."}), 409

    # Assign to the default org (first org in the system)
    default_org = _q("SELECT TOP 1 org_id FROM dbo.Organizations ORDER BY org_id")
    org_id = default_org[0][0] if default_org else 1

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    result  = _q(
        "INSERT INTO dbo.Users (username, email, password_hash, role, [plan], org_id)"
        " OUTPUT INSERTED.user_id VALUES (?, ?, ?, 'viewer', 'basic', ?)",
        (username, email, pw_hash, org_id),
        fetch=True, commit=True,
    )
    if not result:
        return jsonify({"success": False, "error": "Registration failed."}), 500

    new_id = result[0][0]
    _audit(new_id, "REGISTER", "auth", f"Self-registered: {username} in org {org_id}")

    # Auto-login after registration
    claims        = {"role": "viewer", "username": username, "plan": "basic"}
    access_token  = create_access_token(identity=str(new_id), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(new_id))
    _store_refresh_token(
        new_id, _hash_token(refresh_token),
        request.remote_addr, request.headers.get("User-Agent", ""),
    )

    response = make_response(jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "user_id":              new_id,
            "username":             username,
            "email":                email,
            "role":                 "viewer",
            "plan":                 "basic",
            "must_change_password": False,
        },
    }))
    _set_refresh_cookie(response, refresh_token)
    return response, 201


# ─── Admin: User Management ───────────────────────────────────────────────────

@auth_bp.route("/api/auth/users", methods=["GET"])
@require_auth(roles=["admin"])
def list_users():
    plan_col = True
    extra_cols = True
    try:
        rows = _q(
            "SELECT user_id, username, email, role, is_active,"
            "       created_at, last_login, failed_login_attempts, locked_until, [plan],"
            "       setup_completed, totp_enabled"
            " FROM dbo.Users WHERE org_id = ? AND is_system_admin = 0 ORDER BY created_at DESC",
            (g.current_user_org_id,),
        )
    except Exception:
        try:
            rows = _q(
                "SELECT user_id, username, email, role, is_active,"
                "       created_at, last_login, failed_login_attempts, locked_until, [plan],"
                "       setup_completed, totp_enabled"
                " FROM dbo.Users WHERE is_system_admin = 0 ORDER BY created_at DESC",
            )
        except Exception:
            extra_cols = False
            try:
                rows = _q(
                    "SELECT user_id, username, email, role, is_active,"
                    "       created_at, last_login, failed_login_attempts, locked_until, [plan]"
                    " FROM dbo.Users ORDER BY created_at DESC",
                )
            except Exception:
                plan_col = False
                extra_cols = False
                rows = _q(
                    "SELECT user_id, username, email, role, is_active,"
                    "       created_at, last_login, failed_login_attempts, locked_until"
                    " FROM dbo.Users ORDER BY created_at DESC",
                )
    users = []
    for r in (rows or []):
        users.append({
            "user_id":               r[0],
            "username":              r[1],
            "email":                 r[2],
            "role":                  r[3],
            "is_active":             bool(r[4]),
            "created_at":            str(r[5]) if r[5] else None,
            "last_login":            str(r[6]) if r[6] else None,
            "failed_login_attempts": r[7],
            "locked_until":          str(r[8]) if r[8] else None,
            "plan":                  (r[9] if plan_col else None) or "basic",
            "setup_completed":       bool(r[10]) if (extra_cols and len(r) > 10 and r[10] is not None) else True,
            "totp_enabled":          bool(r[11]) if (extra_cols and len(r) > 11 and r[11] is not None) else False,
        })
    return jsonify({"success": True, "users": users, "count": len(users)}), 200


@auth_bp.route("/api/auth/users", methods=["POST"])
@require_auth(roles=["admin"])
def create_user():
    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    role     = (data.get("role") or "viewer").lower()
    plan     = (data.get("plan") or "basic").lower()

    if not all([username, email]):
        return jsonify({"success": False,
                        "error": "username and email are required."}), 400
    if role not in ("admin", "analyst", "viewer"):
        return jsonify({"success": False,
                        "error": "Role must be admin, analyst or viewer."}), 400
    if plan not in ("basic", "pro"):
        plan = "basic"

    existing = _q(
        "SELECT 1 FROM dbo.Users WHERE LOWER(email) = ? OR LOWER(username) = ?",
        (email, username.lower()),
    )
    if existing:
        return jsonify({"success": False,
                        "error": "Username or email already exists."}), 409

    # Generate a temporary unusable password hash — user sets real password via setup email
    temp_hash     = bcrypt.hashpw(secrets.token_hex(32).encode(), bcrypt.gensalt(rounds=12)).decode()
    setup_token   = secrets.token_urlsafe(48)
    totp_secret   = pyotp.random_base32()
    token_expires = datetime.now(timezone.utc) + timedelta(hours=72)

    try:
        result = _q(
            "INSERT INTO dbo.Users"
            " (username, email, password_hash, role, [plan], created_by, org_id,"
            "  is_active, totp_secret, totp_enabled, account_setup_token, setup_token_expires, setup_completed)"
            " OUTPUT INSERTED.user_id VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, 0)",
            (username, email, temp_hash, role, plan, g.current_user_id, g.current_user_org_id,
             totp_secret, setup_token, token_expires),
            fetch=True, commit=True,
        )
    except Exception:
        try:
            result = _q(
                "INSERT INTO dbo.Users"
                " (username, email, password_hash, role, [plan], created_by,"
                "  is_active, totp_secret, totp_enabled, account_setup_token, setup_token_expires, setup_completed)"
                " OUTPUT INSERTED.user_id VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, 0)",
                (username, email, temp_hash, role, plan, g.current_user_id,
                 totp_secret, setup_token, token_expires),
                fetch=True, commit=True,
            )
        except Exception:
            result = _q(
                "INSERT INTO dbo.Users (username, email, password_hash, role)"
                " OUTPUT INSERTED.user_id VALUES (?, ?, ?, ?)",
                (username, email, temp_hash, role),
                fetch=True, commit=True,
            )
    if not result:
        return jsonify({"success": False, "error": "Failed to create user."}), 500

    new_id = result[0][0]
    _audit(g.current_user_id, "CREATE_USER", f"user:{new_id}",
           f"Created {role}/{plan} '{username}' in org {g.current_user_org_id}")

    from email_service import send_user_setup_email
    sent = send_user_setup_email(email, username, setup_token, g.current_username)

    return jsonify({
        "success": True,
        "message": f"User '{username}' created. Setup email {'sent to ' + email if sent else 'could not be sent — check SMTP config.'}",
        "user_id":     new_id,
        "setup_token": setup_token if not sent else None,
    }), 201


def _assert_same_org(target_id: int):
    """Return 404 if target user doesn't exist (org check optional — falls back gracefully)."""
    try:
        rows = _q("SELECT 1 FROM dbo.Users WHERE user_id = ? AND org_id = ?",
                  (target_id, g.current_user_org_id))
    except Exception:
        rows = _q("SELECT 1 FROM dbo.Users WHERE user_id = ?", (target_id,))
    if not rows:
        return jsonify({"success": False, "error": "User not found."}), 404
    return None


@auth_bp.route("/api/auth/users/<int:target_id>", methods=["PUT"])
@require_auth(roles=["admin"])
def update_user(target_id):
    err = _assert_same_org(target_id)
    if err:
        return err
    data    = request.get_json(silent=True) or {}
    updates = []
    params  = []

    if "role" in data:
        if data["role"] not in ("admin", "analyst", "viewer"):
            return jsonify({"success": False, "error": "Invalid role."}), 400
        updates.append("role = ?")
        params.append(data["role"])

    if "plan" in data:
        if data["plan"] not in ("basic", "pro"):
            return jsonify({"success": False, "error": "Plan must be basic or pro."}), 400
        updates.append("[plan] = ?")
        params.append(data["plan"])

    if "is_active" in data:
        updates.append("is_active = ?")
        params.append(1 if data["is_active"] else 0)
        if not data["is_active"]:
            _revoke_all_user_tokens(target_id)

    if data.get("unlock"):
        updates += ["failed_login_attempts = 0", "locked_until = NULL"]

    if not updates:
        return jsonify({"success": False, "error": "No valid fields to update."}), 400

    params.append(target_id)
    _q(f"UPDATE dbo.Users SET {', '.join(updates)} WHERE user_id = ?",
       params, fetch=False)
    _audit(g.current_user_id, "UPDATE_USER", f"user:{target_id}", str(data))
    return jsonify({"success": True, "message": "User updated."}), 200


@auth_bp.route("/api/auth/users/<int:target_id>", methods=["DELETE"])
@require_auth(roles=["admin"])
def delete_user(target_id):
    err = _assert_same_org(target_id)
    if err:
        return err
    if target_id == g.current_user_id:
        return jsonify({"success": False,
                        "error": "Cannot delete your own account."}), 400

    _revoke_all_user_tokens(target_id)
    _q("DELETE FROM dbo.AuditLog    WHERE user_id = ?", (target_id,), fetch=False)
    _q("DELETE FROM dbo.RefreshTokens WHERE user_id = ?", (target_id,), fetch=False)
    _q("DELETE FROM dbo.Users       WHERE user_id = ?", (target_id,), fetch=False)

    _audit(g.current_user_id, "DELETE_USER", f"user:{target_id}", "User deleted")
    return jsonify({"success": True, "message": "User deleted."}), 200


@auth_bp.route("/api/auth/users/<int:target_id>/reset-password", methods=["POST"])
@require_auth(roles=["admin"])
def admin_reset_password(target_id):
    err = _assert_same_org(target_id)
    if err:
        return err
    data         = request.get_json(silent=True) or {}
    new_password = data.get("new_password") or ""

    if not new_password:
        return jsonify({"success": False, "error": "new_password is required."}), 400

    err = _validate_password(new_password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()
    _q(
        "UPDATE dbo.Users"
        " SET password_hash = ?, must_change_password = 1,"
        "     failed_login_attempts = 0, locked_until = NULL"
        " WHERE user_id = ?",
        (new_hash, target_id), fetch=False,
    )
    _revoke_all_user_tokens(target_id)
    _audit(g.current_user_id, "ADMIN_RESET_PASSWORD", f"user:{target_id}", "")

    return jsonify({
        "success": True,
        "message": "Password reset. User must change it on next login.",
    }), 200


@auth_bp.route("/api/auth/audit-log", methods=["GET"])
@require_auth(roles=["admin"])
def get_audit_log():
    limit  = min(request.args.get("limit",  100, type=int), 500)
    offset = request.args.get("offset", 0,   type=int)

    rows = _q(
        "SELECT al.log_id, ISNULL(u.username,'system') as username,"
        "       al.action, al.resource, al.details,"
        "       al.ip_address, al.logged_at, al.success"
        " FROM dbo.AuditLog al"
        " LEFT JOIN dbo.Users u ON al.user_id = u.user_id"
        " ORDER BY al.logged_at DESC"
        " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        (offset, limit),
    )
    entries = []
    for r in (rows or []):
        entries.append({
            "log_id":    r[0], "username": r[1], "action": r[2],
            "resource":  r[3], "details":  r[4], "ip_address": r[5],
            "timestamp": str(r[6]) if r[6] else None,
            "success":   bool(r[7]),
        })
    return jsonify({"success": True, "logs": entries, "count": len(entries)}), 200


# ── 2FA verification ──────────────────────────────────────────────────────────

@auth_bp.route("/api/auth/verify-2fa", methods=["POST"])
def verify_2fa():
    data       = request.get_json(silent=True) or {}
    session_id = data.get("mfa_session_id") or ""
    code       = (data.get("totp_code") or "").strip().replace(" ", "")

    user_id = _consume_mfa_session(session_id)
    if not user_id:
        return jsonify({"success": False, "error": "Session expired. Please log in again."}), 401

    user = _get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        return jsonify({"success": False, "error": "Account inactive."}), 403

    # Get totp_secret
    try:
        rows = _q("SELECT totp_secret FROM dbo.Users WHERE user_id = ?", (user_id,))
        totp_secret = rows[0][0] if rows else None
    except Exception:
        totp_secret = None

    if not totp_secret:
        return jsonify({"success": False, "error": "2FA not configured for this account."}), 400

    totp = pyotp.TOTP(totp_secret)
    if not totp.verify(code, valid_window=1):
        _audit(user_id, "LOGIN_2FA_FAILED", "auth", "Invalid TOTP code", success=False)
        return jsonify({"success": False, "error": "Invalid verification code. Please try again."}), 401

    _reset_failed_attempts(user_id)
    claims        = {"role": user["role"], "username": user["username"],
                     "plan": user.get("plan", "basic"), "org_id": user.get("org_id", 1),
                     "is_system_admin": user.get("is_system_admin", False)}
    access_token  = create_access_token(identity=str(user_id), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(user_id))
    _store_refresh_token(user_id, _hash_token(refresh_token),
                         request.remote_addr, request.headers.get("User-Agent", ""))
    _audit(user_id, "LOGIN", "auth", "Successful login with 2FA")

    response = make_response(jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "user_id":              user["user_id"],
            "username":             user["username"],
            "email":                user["email"],
            "role":                 user["role"],
            "plan":                 user.get("plan", "basic"),
            "org_id":               user.get("org_id", 1),
            "is_system_admin":      user.get("is_system_admin", False),
            "must_change_password": user["must_change_password"],
        },
    }))
    _set_refresh_cookie(response, refresh_token)
    return response, 200


# ── Account setup (via email link) ────────────────────────────────────────────

@auth_bp.route("/api/auth/validate-setup-token", methods=["GET"])
def validate_setup_token():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"valid": False, "error": "Token required."}), 400
    try:
        rows = _q(
            "SELECT u.user_id, u.username, u.email, u.totp_secret, o.name as org_name"
            " FROM dbo.Users u"
            " LEFT JOIN dbo.Organizations o ON u.org_id = o.org_id"
            " WHERE u.account_setup_token = ? AND u.setup_token_expires > GETDATE()"
            " AND u.setup_completed = 0",
            (token,)
        )
    except Exception as exc:
        return jsonify({"valid": False, "error": str(exc)}), 500

    if not rows:
        return jsonify({"valid": False, "error": "Invalid or expired setup link. Please contact your administrator."}), 404

    r = rows[0]
    totp_uri = pyotp.TOTP(r[3]).provisioning_uri(name=r[2], issuer_name="HydroCore")
    return jsonify({
        "valid":       True,
        "username":    r[1],
        "email":       r[2],
        "org_name":    r[4] or "HydroCore",
        "totp_uri":    totp_uri,
        "totp_secret": r[3],
    }), 200


@auth_bp.route("/api/auth/complete-setup", methods=["POST"])
def complete_setup():
    data      = request.get_json(silent=True) or {}
    token     = (data.get("token") or "").strip()
    password  = data.get("password") or ""
    totp_code = (data.get("totp_code") or "").strip().replace(" ", "")

    if not token or not password or not totp_code:
        return jsonify({"success": False, "error": "token, password and totp_code are required."}), 400

    err = _validate_password(password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    try:
        rows = _q(
            "SELECT user_id, username, email, totp_secret FROM dbo.Users"
            " WHERE account_setup_token = ? AND setup_token_expires > GETDATE() AND setup_completed = 0",
            (token,)
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    if not rows:
        return jsonify({"success": False, "error": "Invalid or expired setup link."}), 400

    r = rows[0]
    user_id, username, email, totp_secret = r[0], r[1], r[2], r[3]

    totp = pyotp.TOTP(totp_secret)
    if not totp.verify(totp_code, valid_window=1):
        return jsonify({"success": False, "error": "Invalid verification code from your authenticator app."}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    try:
        _q(
            "UPDATE dbo.Users SET password_hash = ?, totp_enabled = 1, is_active = 1,"
            " setup_completed = 1, account_setup_token = NULL, setup_token_expires = NULL,"
            " failed_login_attempts = 0, locked_until = NULL"
            " WHERE user_id = ?",
            (pw_hash, user_id), fetch=False,
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    _audit(user_id, "ACCOUNT_SETUP_COMPLETE", "auth", f"User {username} completed account setup")
    return jsonify({"success": True, "message": "Account setup complete. You can now log in."}), 200


# ── Tenant-admin user management endpoints ────────────────────────────────────

@auth_bp.route("/api/auth/users/<int:target_id>/reset-2fa", methods=["POST"])
@require_auth(roles=["admin"])
def reset_user_2fa(target_id):
    err = _assert_same_org(target_id)
    if err:
        return err
    new_secret    = pyotp.random_base32()
    setup_token   = secrets.token_urlsafe(48)
    token_expires = datetime.now(timezone.utc) + timedelta(hours=72)
    try:
        _q(
            "UPDATE dbo.Users SET totp_secret = ?, totp_enabled = 0,"
            " account_setup_token = ?, setup_token_expires = ?, setup_completed = 0, is_active = 0"
            " WHERE user_id = ?",
            (new_secret, setup_token, token_expires, target_id), fetch=False,
        )
        rows = _q("SELECT username, email FROM dbo.Users WHERE user_id = ?", (target_id,))
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    if rows:
        username, email = rows[0][0], rows[0][1]
        from email_service import send_user_setup_email
        sent = send_user_setup_email(email, username, setup_token, g.current_username)
        _audit(g.current_user_id, "RESET_2FA", f"user:{target_id}", f"2FA reset by {g.current_username}")
        return jsonify({
            "success":     True,
            "message":     f"2FA reset. Setup email {'sent' if sent else 'could not be sent'}.",
            "setup_token": setup_token if not sent else None,
        }), 200
    return jsonify({"success": False, "error": "User not found."}), 404


@auth_bp.route("/api/auth/users/<int:target_id>/resend-setup", methods=["POST"])
@require_auth(roles=["admin"])
def resend_user_setup(target_id):
    err = _assert_same_org(target_id)
    if err:
        return err
    new_secret    = pyotp.random_base32()
    setup_token   = secrets.token_urlsafe(48)
    token_expires = datetime.now(timezone.utc) + timedelta(hours=72)
    try:
        _q(
            "UPDATE dbo.Users SET totp_secret = ?, account_setup_token = ?,"
            " setup_token_expires = ?, totp_enabled = 0, is_active = 0, setup_completed = 0"
            " WHERE user_id = ?",
            (new_secret, setup_token, token_expires, target_id), fetch=False,
        )
        rows = _q("SELECT username, email FROM dbo.Users WHERE user_id = ?", (target_id,))
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    if rows:
        username, email = rows[0][0], rows[0][1]
        from email_service import send_user_setup_email
        sent = send_user_setup_email(email, username, setup_token, g.current_username)
        _audit(g.current_user_id, "RESEND_SETUP", f"user:{target_id}", f"Resent by {g.current_username}")
        return jsonify({
            "success":     True,
            "message":     f"Setup email {'resent' if sent else 'could not be sent — check SMTP config.'}",
            "setup_token": setup_token if not sent else None,
        }), 200
    return jsonify({"success": False, "error": "User not found."}), 404
