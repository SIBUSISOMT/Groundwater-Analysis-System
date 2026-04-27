/**
 * auth.js — HydroCore Authentication Client
 * ==========================================
 * Loaded on every protected page BEFORE the page's own JS.
 *
 * Multi-user same-browser design:
 *   Access token  → JavaScript memory (in-memory, never persisted)
 *   Refresh token → sessionStorage (tab-isolated — each browser tab has its
 *                   own sessionStorage, so User A on Tab 1 and User B on Tab 2
 *                   never share tokens)
 *
 * The refresh token is sent to the server as the X-Refresh-Token header so the
 * backend can identify which user session to rotate — independent of any shared
 * httpOnly cookie.
 */

const HydroAuth = (function () {
    'use strict';

    // When served via Live Server (or any port other than Flask's 5000),
    // all auth API calls must use the absolute backend URL.
    const _BACKEND    = (window.location.port === '5000' || window.location.port === '') ? '' : 'http://localhost:5000';
    const _CREDS      = _BACKEND ? 'include' : 'same-origin';

    const LOGIN_PAGE  = '/frontend/public/login.html';
    const REFRESH_URL = `${_BACKEND}/api/auth/refresh`;
    const LOGOUT_URL  = `${_BACKEND}/api/auth/logout`;

    // sessionStorage keys — prefixed to avoid collisions
    const SK_AT   = 'hc_at';    // short-lived bridge after login redirect
    const SK_USER = 'hc_user';  // short-lived bridge after login redirect
    const SK_RT   = 'hc_rt';    // refresh token — tab-isolated

    let _accessToken    = null;
    let _user           = null;
    let _refreshPromise = null;

    const _realFetch = window.fetch.bind(window);

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _redirectToLogin() {
        _accessToken = null;
        _user        = null;
        sessionStorage.removeItem(SK_AT);
        sessionStorage.removeItem(SK_USER);
        sessionStorage.removeItem(SK_RT);
        window.location.href = LOGIN_PAGE;
    }

    function _storeRefreshToken(raw) {
        if (raw) sessionStorage.setItem(SK_RT, raw);
    }

    function _getRefreshToken() {
        return sessionStorage.getItem(SK_RT) || null;
    }

    async function _doRefresh() {
        const rt = _getRefreshToken();
        try {
            const headers = { 'Content-Type': 'application/json' };
            if (rt) headers['X-Refresh-Token'] = rt;

            const resp = await _realFetch(REFRESH_URL, {
                method:      'POST',
                credentials: _CREDS,
                headers,
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            if (data.success && data.access_token) {
                _accessToken = data.access_token;
                if (data.refresh_token) _storeRefreshToken(data.refresh_token);
                if (data.user) _applyUser(data.user);
                return true;
            }
            return false;
        } catch (_) {
            return false;
        }
    }

    function _refreshOnce() {
        if (!_refreshPromise) {
            _refreshPromise = _doRefresh().finally(() => { _refreshPromise = null; });
        }
        return _refreshPromise;
    }

    function _applyUser(user) {
        _user = user;
        _updateSidebarUI(user);
        _applyRoleVisibility(user.role);
    }

    function _updateSidebarUI(user) {
        const roleLabels = { admin: 'Administrator', analyst: 'Analyst', viewer: 'Viewer' };
        const initials   = (user.username || 'U').slice(0, 2).toUpperCase();
        const displayRole = user.is_system_admin ? 'System Admin' : (roleLabels[user.role] || user.role);

        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        set('userAvatar',      initials);
        set('headerUserAvatar', initials);
        set('headerUsername',  user.username);
        set('headerRole',      displayRole);
    }

    function _applyRoleVisibility(role) {
        document.querySelectorAll('[data-requires-role]').forEach(el => {
            const allowed = (el.dataset.requiresRole || '').split(' ').filter(Boolean);
            if (allowed.length && !allowed.includes(role)) el.style.display = 'none';
        });
        // data-show-for-role: show only when role matches (hidden by default via CSS)
        document.querySelectorAll('[data-show-for-role]').forEach(el => {
            const allowed = (el.dataset.showForRole || '').split(' ').filter(Boolean);
            el.style.display = (allowed.length && allowed.includes(role)) ? '' : 'none';
        });
    }

    // ── Global fetch override ─────────────────────────────────────────────────

    window.fetch = async function (url, options = {}) {
        const urlStr  = typeof url === 'string' ? url : (url.url || '');
        const apiPath = urlStr.includes('/api/') ? urlStr.slice(urlStr.indexOf('/api/')) : '';
        const isApi   = apiPath.startsWith('/api/')
            && !apiPath.startsWith('/api/auth/login')
            && !apiPath.startsWith('/api/auth/refresh')
            && !apiPath.startsWith('/api/auth/setup');

        // Proactive wait: if no token yet, block until refresh completes.
        // This prevents the race condition where script.js makes API calls
        // before HydroAuth.init() has finished its first refresh.
        if (isApi && !_accessToken) {
            await _refreshOnce();
        }

        if (isApi && _accessToken) {
            options = { ...options, headers: { ...options.headers, Authorization: `Bearer ${_accessToken}` } };
        }

        let response = await _realFetch(url, options);

        // Reactive fallback: token was stale — refresh and retry once
        if (response.status === 401 && isApi) {
            const refreshed = await _refreshOnce();
            if (refreshed && _accessToken) {
                options = { ...options, headers: { ...options.headers, Authorization: `Bearer ${_accessToken}` } };
                response = await _realFetch(url, options);
            } else {
                _redirectToLogin();
            }
        }

        return response;
    };

    // ── Public API ────────────────────────────────────────────────────────────

    async function init() {
        const path = window.location.pathname;

        if (path.includes('login.html') || path.includes('setup_account.html')) {
            document.body.style.display = 'block';
            return true;
        }

        // Fast path: token was just issued during login redirect
        const cached     = sessionStorage.getItem(SK_AT);
        const cachedUser = sessionStorage.getItem(SK_USER);
        if (cached) {
            _accessToken = cached;
            if (cachedUser) { try { _applyUser(JSON.parse(cachedUser)); } catch (_) {} }
            sessionStorage.removeItem(SK_AT);
            sessionStorage.removeItem(SK_USER);
            // Rotate now so we have a fresh token before any API call races
            const ok = await _doRefresh();
            if (!ok) { _redirectToLogin(); return false; }

            // Route system admins and protect the system admin page
            const isSystemAdminPage = path.includes('system_admin.html');
            if (_user && _user.is_system_admin && !isSystemAdminPage) {
                window.location.href = '/frontend/public/system_admin.html';
                return false;
            }
            if (_user && !_user.is_system_admin && isSystemAdminPage) {
                window.location.href = '/frontend/public/index.html';
                return false;
            }

            document.body.style.display = 'block';
            document.dispatchEvent(new CustomEvent('hydroAuthReady', { detail: { user: _user } }));
            return true;
        }

        // Normal path: attempt silent refresh using this tab's stored refresh token
        const ok = await _doRefresh();
        if (!ok) { _redirectToLogin(); return false; }

        if (_user && _user.must_change_password) {
            window.location.href = LOGIN_PAGE;
            return false;
        }

        // Route system admins and protect the system admin page
        const isSystemAdminPage = path.includes('system_admin.html');
        if (_user && _user.is_system_admin && !isSystemAdminPage) {
            window.location.href = '/frontend/public/system_admin.html';
            return false;
        }
        if (_user && !_user.is_system_admin && isSystemAdminPage) {
            window.location.href = '/frontend/public/index.html';
            return false;
        }

        document.body.style.display = 'block';
        document.dispatchEvent(new CustomEvent('hydroAuthReady', { detail: { user: _user } }));
        return true;
    }

    async function logout() {
        const rt = _getRefreshToken();
        try {
            await _realFetch(LOGOUT_URL, {
                method:      'POST',
                credentials: _CREDS,
                headers: {
                    'Content-Type': 'application/json',
                    ..._accessToken ? { Authorization: `Bearer ${_accessToken}` } : {},
                    ...rt ? { 'X-Refresh-Token': rt } : {},
                },
            });
        } catch (_) { /* always redirect */ }
        _redirectToLogin();
    }

    function getUser()        { return _user; }
    function getAccessToken() { return _accessToken; }
    function getPlan()        { return _user ? (_user.plan || 'basic') : 'basic'; }
    function isPro()          { return _user && _user.plan === 'pro'; }
    function canUpload()      { return _user && ['admin', 'analyst'].includes(_user.role) && isPro(); }
    function isAdmin()        { return _user && _user.role === 'admin'; }
    function isViewer()       { return _user && _user.role === 'viewer'; }
    function isSystemAdmin()  { return _user && _user.is_system_admin === true; }

    return { init, logout, getUser, getAccessToken, getPlan, isPro, canUpload, isAdmin, isViewer, isSystemAdmin };
})();

document.addEventListener('DOMContentLoaded', () => HydroAuth.init());
