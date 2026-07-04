/**
 * config.js — Shared frontend environment config.
 * Must be loaded before auth.js and every page's own script — several files
 * previously each recomputed this same backend-URL check independently.
 *
 * When served via Live Server (or any port other than Flask's 5000), API
 * calls must use the absolute backend URL instead of a relative path.
 */
window.HC_BACKEND_URL = (window.location.port === '5000' || window.location.port === '')
    ? ''
    : 'http://localhost:5000';
