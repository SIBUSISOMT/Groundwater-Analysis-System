"""
admin_bp.py — HydroCore System Administration Blueprint
=======================================================
Handles tenant (organisation) management by system administrators.
All routes require is_system_admin = 1 in the JWT claims.
"""
import secrets
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from functools import wraps

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__)

_db = None

def init_admin(db):
    global _db
    _db = db

def _q(sql, params=None, fetch=True, commit=False):
    return _db.execute_query(sql, params, fetch=fetch, commit=commit)

# ── System admin guard ────────────────────────────────────────────────────────

def require_system_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({'success': False, 'error': 'Authentication required.', 'error_code': 'UNAUTHORIZED'}), 401
        claims = get_jwt()
        if not claims.get('is_system_admin'):
            return jsonify({'success': False, 'error': 'System administrator access required.', 'error_code': 'FORBIDDEN'}), 403
        g.sysadmin_id = int(get_jwt_identity())
        return f(*args, **kwargs)
    return decorated

# ── Setup first system admin ──────────────────────────────────────────────────

@admin_bp.route('/api/admin/setup', methods=['POST'])
def setup_system_admin():
    """One-time endpoint to create the first system administrator."""
    try:
        rows = _q('SELECT COUNT(*) FROM dbo.Users WHERE is_system_admin = 1')
        if rows and rows[0][0] > 0:
            return jsonify({'success': False, 'error': 'System administrator already exists.'}), 403
    except Exception:
        pass  # Column may not exist yet

    data     = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    email    = (data.get('email') or '').strip().lower()

    if not username or not email:
        return jsonify({'success': False, 'error': 'username and email are required.'}), 400

    existing = _q('SELECT 1 FROM dbo.Users WHERE LOWER(email) = ? OR LOWER(username) = ?',
                  (email, username.lower()))
    if existing:
        return jsonify({'success': False, 'error': 'Username or email already exists.'}), 409

    import pyotp
    setup_token   = secrets.token_urlsafe(48)
    totp_secret   = pyotp.random_base32()
    token_expires = datetime.now(timezone.utc) + timedelta(hours=72)
    temp_hash     = bcrypt.hashpw(secrets.token_hex(32).encode(), bcrypt.gensalt(rounds=12)).decode()

    try:
        result = _q(
            "INSERT INTO dbo.Users"
            " (username, email, password_hash, role, is_active, is_system_admin,"
            "  totp_secret, totp_enabled, account_setup_token, setup_token_expires, setup_completed)"
            " OUTPUT INSERTED.user_id VALUES (?, ?, ?, 'admin', 0, 1, ?, 0, ?, ?, 0)",
            (username, email, temp_hash, totp_secret, setup_token, token_expires),
            fetch=True, commit=True,
        )
    except Exception as exc:
        logger.error('setup_system_admin INSERT failed: %s', exc)
        return jsonify({'success': False, 'error': 'Failed to create system administrator.'}), 500

    if not result:
        return jsonify({'success': False, 'error': 'Failed to create system administrator.'}), 500

    from email_service import send_system_admin_setup_email
    sent = send_system_admin_setup_email(email, username, setup_token)

    return jsonify({
        'success': True,
        'message': f"System administrator '{username}' created. Setup email {'sent' if sent else 'could not be sent — configure SMTP'}.",
        'setup_token': setup_token if not sent else None,  # Return token only if email failed
        'user_id': result[0][0],
    }), 201

# ── Dashboard stats ───────────────────────────────────────────────────────────

@admin_bp.route('/api/admin/stats', methods=['GET'])
@require_system_admin
def get_stats():
    try:
        orgs    = _q('SELECT COUNT(*) FROM dbo.Organizations')
        users   = _q('SELECT COUNT(*) FROM dbo.Users WHERE is_system_admin = 0')
        active  = _q('SELECT COUNT(*) FROM dbo.Organizations WHERE is_active = 1')
        pending = _q('SELECT COUNT(*) FROM dbo.Users WHERE setup_completed = 0 AND is_system_admin = 0')
        return jsonify({
            'success': True,
            'stats': {
                'total_tenants':   orgs[0][0]    if orgs    else 0,
                'total_users':     users[0][0]   if users   else 0,
                'active_tenants':  active[0][0]  if active  else 0,
                'pending_setup':   pending[0][0] if pending else 0,
            }
        }), 200
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

# ── Tenant management ─────────────────────────────────────────────────────────

@admin_bp.route('/api/admin/tenants', methods=['GET'])
@require_system_admin
def list_tenants():
    try:
        rows = _q(
            "SELECT o.org_id, o.name, o.[plan], o.is_active, o.contact_email, o.created_at,"
            "       COUNT(u.user_id) as user_count"
            " FROM dbo.Organizations o"
            " LEFT JOIN dbo.Users u ON u.org_id = o.org_id AND u.is_system_admin = 0"
            " GROUP BY o.org_id, o.name, o.[plan], o.is_active, o.contact_email, o.created_at"
            " ORDER BY o.created_at DESC"
        )
    except Exception:
        rows = _q("SELECT org_id, name, [plan], 1, NULL, GETDATE(), 0 FROM dbo.Organizations ORDER BY org_id DESC")

    tenants = []
    for r in (rows or []):
        tenants.append({
            'org_id':        r[0],
            'name':          r[1],
            'plan':          r[2] or 'basic',
            'is_active':     bool(r[3]),
            'contact_email': r[4],
            'created_at':    str(r[5]) if r[5] else None,
            'user_count':    r[6] if len(r) > 6 else 0,
        })
    return jsonify({'success': True, 'tenants': tenants, 'count': len(tenants)}), 200


@admin_bp.route('/api/admin/tenants', methods=['POST'])
@require_system_admin
def create_tenant():
    """Create a new organisation and its first admin user (tenant admin)."""
    data           = request.get_json(silent=True) or {}
    org_name       = (data.get('org_name') or '').strip()
    admin_username = (data.get('admin_username') or '').strip()
    admin_email    = (data.get('admin_email') or '').strip().lower()
    plan           = (data.get('plan') or 'basic').lower()
    contact_email  = (data.get('contact_email') or admin_email).strip().lower()

    if not org_name or not admin_username or not admin_email:
        return jsonify({'success': False, 'error': 'org_name, admin_username and admin_email are required.'}), 400
    if plan not in ('basic', 'pro'):
        plan = 'basic'

    existing_user = _q('SELECT 1 FROM dbo.Users WHERE LOWER(email) = ? OR LOWER(username) = ?',
                        (admin_email, admin_username.lower()))
    if existing_user:
        return jsonify({'success': False, 'error': 'Admin username or email already exists.'}), 409

    # Create organisation
    try:
        org_result = _q(
            "INSERT INTO dbo.Organizations (name, [plan], contact_email, is_active)"
            " OUTPUT INSERTED.org_id VALUES (?, ?, ?, 1)",
            (org_name, plan, contact_email), fetch=True, commit=True,
        )
    except Exception:
        org_result = _q(
            "INSERT INTO dbo.Organizations (name, [plan]) OUTPUT INSERTED.org_id VALUES (?, ?)",
            (org_name, plan), fetch=True, commit=True,
        )
    if not org_result:
        return jsonify({'success': False, 'error': 'Failed to create organisation.'}), 500
    org_id = org_result[0][0]

    # Create tenant admin account (inactive, pending setup)
    import pyotp
    setup_token   = secrets.token_urlsafe(48)
    totp_secret   = pyotp.random_base32()
    token_expires = datetime.now(timezone.utc) + timedelta(hours=72)
    temp_hash     = bcrypt.hashpw(secrets.token_hex(32).encode(), bcrypt.gensalt(rounds=12)).decode()

    try:
        user_result = _q(
            "INSERT INTO dbo.Users"
            " (username, email, password_hash, role, [plan], org_id, is_active,"
            "  totp_secret, totp_enabled, account_setup_token, setup_token_expires, setup_completed,"
            "  created_by)"
            " OUTPUT INSERTED.user_id VALUES (?, ?, ?, 'admin', ?, ?, 0, ?, 0, ?, ?, 0, ?)",
            (admin_username, admin_email, temp_hash, plan, org_id,
             totp_secret, setup_token, token_expires, g.sysadmin_id),
            fetch=True, commit=True,
        )
    except Exception as exc:
        logger.error('create_tenant user INSERT failed: %s', exc)
        return jsonify({'success': False, 'error': 'Organisation created but failed to create admin user.'}), 500

    if not user_result:
        return jsonify({'success': False, 'error': 'Failed to create tenant admin.'}), 500

    from email_service import send_tenant_admin_setup_email
    sent = send_tenant_admin_setup_email(admin_email, admin_username, org_name, setup_token)

    return jsonify({
        'success': True,
        'message': f"Tenant '{org_name}' created. Admin setup email {'sent to ' + admin_email if sent else 'could not be sent — configure SMTP'}.",
        'org_id':        org_id,
        'admin_user_id': user_result[0][0],
        'setup_token':   setup_token if not sent else None,
    }), 201


@admin_bp.route('/api/admin/tenants/<int:org_id>', methods=['GET'])
@require_system_admin
def get_tenant(org_id):
    try:
        org_rows = _q(
            "SELECT org_id, name, [plan], is_active, contact_email, created_at FROM dbo.Organizations WHERE org_id = ?",
            (org_id,)
        )
    except Exception:
        org_rows = _q("SELECT org_id, name, [plan], 1, NULL, NULL FROM dbo.Organizations WHERE org_id = ?", (org_id,))

    if not org_rows:
        return jsonify({'success': False, 'error': 'Tenant not found.'}), 404
    r = org_rows[0]
    org = {'org_id': r[0], 'name': r[1], 'plan': r[2] or 'basic', 'is_active': bool(r[3]),
           'contact_email': r[4], 'created_at': str(r[5]) if r[5] else None}

    try:
        user_rows = _q(
            "SELECT user_id, username, email, role, is_active, created_at, last_login,"
            "       setup_completed, totp_enabled, [plan]"
            " FROM dbo.Users WHERE org_id = ? AND is_system_admin = 0 ORDER BY created_at DESC",
            (org_id,)
        )
        users = [{'user_id': u[0], 'username': u[1], 'email': u[2], 'role': u[3],
                  'is_active': bool(u[4]), 'created_at': str(u[5]) if u[5] else None,
                  'last_login': str(u[6]) if u[6] else None,
                  'setup_completed': bool(u[7]), 'totp_enabled': bool(u[8]),
                  'plan': u[9] or 'basic'} for u in (user_rows or [])]
    except Exception:
        users = []

    return jsonify({'success': True, 'tenant': org, 'users': users}), 200


@admin_bp.route('/api/admin/tenants/<int:org_id>', methods=['PUT'])
@require_system_admin
def update_tenant(org_id):
    data    = request.get_json(silent=True) or {}
    updates = []
    params  = []

    new_is_active = data.get('is_active')          # None means not changing
    new_plan      = data['plan'] if 'plan' in data and data['plan'] in ('basic', 'pro') else None

    if 'name' in data:
        updates.append('name = ?');    params.append(data['name'].strip())
    if new_plan:
        updates.append('[plan] = ?');  params.append(new_plan)
    if new_is_active is not None:
        updates.append('is_active = ?'); params.append(1 if new_is_active else 0)
    if 'contact_email' in data:
        updates.append('contact_email = ?'); params.append(data['contact_email'])

    if not updates:
        return jsonify({'success': False, 'error': 'No valid fields.'}), 400

    params.append(org_id)
    try:
        _q(f"UPDATE dbo.Organizations SET {', '.join(updates)} WHERE org_id = ?", params, fetch=False, commit=True)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

    # ── Cascade suspension / reactivation to all org users ────────────────────
    if new_is_active is not None:
        active_val = 1 if new_is_active else 0
        try:
            _q('UPDATE dbo.Users SET is_active = ? WHERE org_id = ? AND is_system_admin = 0',
               (active_val, org_id), fetch=False, commit=True)
        except Exception:
            pass
        if not new_is_active:
            # Revoke every active session so suspended users are kicked out immediately
            _revoke_org_tokens(org_id)

    # ── Cascade plan change to all org users + force token refresh ────────────
    if new_plan:
        try:
            _q('UPDATE dbo.Users SET [plan] = ? WHERE org_id = ? AND is_system_admin = 0',
               (new_plan, org_id), fetch=False, commit=True)
        except Exception:
            pass
        # Revoke tokens so next login re-builds JWT with the updated plan claim
        _revoke_org_tokens(org_id)

    return jsonify({'success': True, 'message': 'Tenant updated.'}), 200


def _revoke_org_tokens(org_id: int):
    """Revoke all active refresh tokens for every non-sysadmin user in an org."""
    try:
        user_rows = _q(
            'SELECT user_id FROM dbo.Users WHERE org_id = ? AND is_system_admin = 0',
            (org_id,)
        )
        for r in (user_rows or []):
            try:
                _q(
                    'UPDATE dbo.RefreshTokens SET revoked_at = GETDATE()'
                    ' WHERE user_id = ? AND revoked_at IS NULL',
                    (r[0],), fetch=False, commit=True
                )
            except Exception:
                pass
    except Exception:
        pass


@admin_bp.route('/api/admin/tenants/<int:org_id>', methods=['DELETE'])
@require_system_admin
def delete_tenant(org_id):
    """Cascade-delete a tenant: all data, users, then the organisation."""
    try:
        if not _q('SELECT 1 FROM dbo.Organizations WHERE org_id = ?', (org_id,)):
            return jsonify({'success': False, 'error': 'Tenant not found.'}), 404

        user_rows = _q('SELECT user_id FROM dbo.Users WHERE org_id = ? AND is_system_admin = 0', (org_id,))
        user_ids  = [r[0] for r in (user_rows or [])]

        # Delete processed & raw data, then sources (FK order)
        try:
            _q('DELETE FROM dbo.ProcessedData WHERE org_id = ?', (org_id,), fetch=False, commit=True)
        except Exception:
            pass
        try:
            _q('DELETE FROM dbo.RawData WHERE org_id = ?', (org_id,), fetch=False, commit=True)
        except Exception:
            pass
        try:
            _q('DELETE FROM dbo.DataSources WHERE org_id = ?', (org_id,), fetch=False, commit=True)
        except Exception:
            pass

        # Revoke sessions and clear audit trail for each user
        for uid in user_ids:
            for tbl in ('dbo.RefreshTokens', 'dbo.AuditLog'):
                try:
                    _q(f'DELETE FROM {tbl} WHERE user_id = ?', (uid,), fetch=False, commit=True)
                except Exception:
                    pass

        _q('DELETE FROM dbo.Users WHERE org_id = ? AND is_system_admin = 0', (org_id,), fetch=False, commit=True)
        _q('DELETE FROM dbo.Organizations WHERE org_id = ?', (org_id,), fetch=False, commit=True)
        return jsonify({'success': True, 'message': 'Tenant and all associated data deleted.'}), 200
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/admin/tenants/<int:org_id>/resend-setup', methods=['POST'])
@require_system_admin
def resend_tenant_admin_setup(org_id):
    """Resend setup email to the tenant admin (the admin user of this org who hasn't completed setup)."""
    try:
        rows = _q(
            "SELECT u.user_id, u.username, u.email, o.name FROM dbo.Users u"
            " JOIN dbo.Organizations o ON u.org_id = o.org_id"
            " WHERE u.org_id = ? AND u.role = 'admin' AND u.is_system_admin = 0"
            " ORDER BY u.created_at ASC",
            (org_id,)
        )
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

    if not rows:
        return jsonify({'success': False, 'error': 'No tenant admin found for this organisation.'}), 404

    import pyotp
    r = rows[0]
    user_id, username, email, org_name = r[0], r[1], r[2], r[3]

    setup_token   = secrets.token_urlsafe(48)
    totp_secret   = pyotp.random_base32()
    token_expires = datetime.now(timezone.utc) + timedelta(hours=72)

    try:
        _q(
            "UPDATE dbo.Users SET account_setup_token = ?, setup_token_expires = ?,"
            " totp_secret = ?, totp_enabled = 0, is_active = 0, setup_completed = 0"
            " WHERE user_id = ?",
            (setup_token, token_expires, totp_secret, user_id), fetch=False,
        )
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

    from email_service import send_tenant_admin_setup_email
    sent = send_tenant_admin_setup_email(email, username, org_name, setup_token)

    return jsonify({
        'success': True,
        'message': f"Setup email {'resent to ' + email if sent else 'could not be sent — check SMTP config.'}",
        'setup_token': setup_token if not sent else None,
    }), 200


# ── Cross-tenant user management ──────────────────────────────────────────────

@admin_bp.route('/api/admin/users', methods=['GET'])
@require_system_admin
def list_all_users():
    """List all non-sysadmin users across every tenant."""
    try:
        rows = _q(
            "SELECT u.user_id, u.username, u.email, u.role, u.[plan], u.is_active,"
            "       u.created_at, u.last_login, u.setup_completed, u.totp_enabled,"
            "       o.org_id, o.name AS org_name"
            " FROM dbo.Users u"
            " LEFT JOIN dbo.Organizations o ON u.org_id = o.org_id"
            " WHERE u.is_system_admin = 0"
            " ORDER BY o.name, u.username"
        )
        users = [{
            'user_id':         r[0],
            'username':        r[1],
            'email':           r[2],
            'role':            r[3],
            'plan':            r[4] or 'basic',
            'is_active':       bool(r[5]),
            'created_at':      str(r[6]) if r[6] else None,
            'last_login':      str(r[7]) if r[7] else None,
            'setup_completed': bool(r[8]),
            'totp_enabled':    bool(r[9]),
            'org_id':          r[10],
            'org_name':        r[11] or 'Unknown',
        } for r in (rows or [])]
        return jsonify({'success': True, 'users': users, 'count': len(users)}), 200
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@require_system_admin
def update_user(user_id):
    """Update a tenant user's role, plan, active status, or username."""
    data    = request.get_json(silent=True) or {}
    updates = []
    params  = []

    if 'role' in data and data['role'] in ('viewer', 'analyst', 'admin'):
        updates.append('role = ?');      params.append(data['role'])
    if 'plan' in data and data['plan'] in ('basic', 'pro'):
        updates.append('[plan] = ?');    params.append(data['plan'])
    if 'is_active' in data:
        updates.append('is_active = ?'); params.append(1 if data['is_active'] else 0)
    if 'username' in data and str(data['username']).strip():
        updates.append('username = ?'); params.append(str(data['username']).strip())

    if not updates:
        return jsonify({'success': False, 'error': 'No valid fields to update.'}), 400

    params.append(user_id)
    try:
        _q(
            f"UPDATE dbo.Users SET {', '.join(updates)} WHERE user_id = ? AND is_system_admin = 0",
            params, fetch=False, commit=True,
        )
        return jsonify({'success': True, 'message': 'User updated.'}), 200
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@require_system_admin
def delete_user(user_id):
    """Delete a tenant user and revoke their sessions."""
    try:
        if not _q('SELECT 1 FROM dbo.Users WHERE user_id = ? AND is_system_admin = 0', (user_id,)):
            return jsonify({'success': False, 'error': 'User not found.'}), 404
        for tbl in ('dbo.RefreshTokens', 'dbo.AuditLog'):
            try:
                _q(f'DELETE FROM {tbl} WHERE user_id = ?', (user_id,), fetch=False, commit=True)
            except Exception:
                pass
        _q('DELETE FROM dbo.Users WHERE user_id = ? AND is_system_admin = 0', (user_id,), fetch=False, commit=True)
        return jsonify({'success': True, 'message': 'User deleted.'}), 200
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
