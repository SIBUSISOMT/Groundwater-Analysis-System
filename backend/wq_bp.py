"""
wq_bp.py — HydroCore Water Quality Blueprint
=============================================
Sampling stations, indicator readings, compliance checks, trend analysis,
CCME-WQI, ion balance, Piper/Stiff diagrams, Mann-Kendall, LSI, eutrophication,
AMD assessment, seasonal analysis, pollution load, Blue Drop scoring, and alerts.
All routes are org-scoped via JWT claims and require authentication.
"""

import io
import logging
from datetime import datetime, date

import pandas as pd
from flask import Blueprint, g, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity
from functools import wraps
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from auth import verify_jwt_claims
from wq_calculations import (
    compute_ccme_wqi, compute_ion_balance_error, compute_mann_kendall,
    compute_lsi, compute_trophic_state_index, compute_piper_data,
    compute_stiff_data, compute_blue_drop_score,
)
from wq_alerts import dispatch_alert

logger = logging.getLogger(__name__)

wq_bp = Blueprint('wq', __name__)

_db = None


def init_wq(db):
    global _db
    _db = db


def _q(sql, params=None, fetch=True, commit=False):
    return _db.execute_query(sql, params, fetch=fetch, commit=commit)


# ── Auth guard ────────────────────────────────────────────────────────────────

def require_wq_auth(roles=None):
    """Decorator: require valid JWT; optionally restrict to given roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            claims, err = verify_jwt_claims(roles)
            if err:
                return err
            g.wq_user_id = int(get_jwt_identity())
            g.wq_org_id  = int(claims.get('org_id', 1))
            g.wq_role    = claims.get('role', 'viewer')
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val):
    try:
        return float(val) if val is not None and str(val).strip() not in ('', 'nan', 'NaN', 'NaT') else None
    except (ValueError, TypeError):
        return None


def _compute_compliance(measured_val, lower_std, upper_std):
    """Return (is_compliant, flag) based on indicator thresholds."""
    if measured_val is None:
        return None, None
    has_limit = (lower_std is not None) or (upper_std is not None)
    if not has_limit:
        return None, None
    if lower_std is not None and measured_val < lower_std:
        return False, 'BELOW'
    if upper_std is not None and measured_val > upper_std:
        return False, 'ABOVE'
    return True, None


def _fetch_indicators():
    """Return list of indicator dicts (cached-ish — small table, no caching needed)."""
    rows = _q(
        "SELECT indicator_id, indicator_code, indicator_name, unit, lower_std, upper_std, std_reference, display_order "
        "FROM dbo.WQ_Indicators ORDER BY display_order"
    )
    if not rows:
        return []
    return [
        {
            'id': r[0], 'code': r[1], 'name': r[2], 'unit': r[3],
            'lower_std': r[4], 'upper_std': r[5], 'reference': r[6], 'display_order': r[7]
        }
        for r in rows
    ]


def _header_to_code_map():
    """Build dict: normalised header string → indicator_code for Excel parsing."""
    result = {}
    for ind in _fetch_indicators():
        name_lc = ind['name'].lower().strip()
        code     = ind['code']
        result[name_lc] = code
        if ind['unit']:
            result[f"{name_lc} ({ind['unit'].lower()})"] = code
        # also by code itself (uppercase and lowercase)
        result[code.lower()] = code
    return result


def _teal_fill():
    return PatternFill('solid', fgColor='0D9488')


def _header_font():
    return Font(color='FFFFFF', bold=True, size=10)


def _thin_border():
    s = Side(border_style='thin', color='CCCCCC')
    return Border(left=s, right=s, top=s, bottom=s)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/dashboard', methods=['GET'])
@require_wq_auth()
def wq_dashboard():
    """Summary KPIs + latest trend data for the current organisation."""
    org = g.wq_org_id
    try:
        # Total active stations
        r_stations = _q(
            "SELECT COUNT(*) FROM dbo.WQ_Stations WHERE org_id=? AND is_active=1", [org]
        )
        total_stations = r_stations[0][0] if r_stations else 0

        # Total reading events
        r_readings = _q(
            "SELECT COUNT(*) FROM dbo.WQ_Readings WHERE org_id=?", [org]
        )
        total_readings = r_readings[0][0] if r_readings else 0

        # Latest reading date
        r_latest = _q(
            "SELECT MAX(r.reading_date) FROM dbo.WQ_Readings r WHERE r.org_id=?", [org]
        )
        latest_date = str(r_latest[0][0]) if r_latest and r_latest[0][0] else None

        # Compliance rate last 90 days
        r_comp = _q(
            """
            SELECT
                COUNT(CASE WHEN m.is_compliant = 1 THEN 1 END)  AS ok,
                COUNT(CASE WHEN m.is_compliant IS NOT NULL THEN 1 END) AS total
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings r ON r.reading_id = m.reading_id
            WHERE r.org_id = ?
              AND r.reading_date >= DATEADD(day, -90, CAST(GETDATE() AS DATE))
            """, [org]
        )
        if r_comp and r_comp[0][1]:
            compliance_rate = round(r_comp[0][0] / r_comp[0][1] * 100, 1)
            compliant_count = r_comp[0][0]
            total_meas      = r_comp[0][1]
        else:
            compliance_rate = None
            compliant_count = 0
            total_meas      = 0

        # Non-compliant flags last 30 days
        r_alerts = _q(
            """
            SELECT TOP 5
                s.station_name, i.indicator_name, i.unit, m.measured_val, m.flag,
                r.reading_date
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings    r ON r.reading_id    = m.reading_id
            JOIN dbo.WQ_Stations    s ON s.station_id    = r.station_id
            JOIN dbo.WQ_Indicators  i ON i.indicator_id  = m.indicator_id
            WHERE r.org_id = ?
              AND m.is_compliant = 0
              AND r.reading_date >= DATEADD(day, -30, CAST(GETDATE() AS DATE))
            ORDER BY r.reading_date DESC
            """, [org]
        )
        alerts = []
        if r_alerts:
            for row in r_alerts:
                alerts.append({
                    'station': row[0], 'indicator': row[1], 'unit': row[2],
                    'value': row[3], 'flag': row[4], 'date': str(row[5])
                })

        # EC trend (last 12 readings across all stations)
        r_trend = _q(
            """
            SELECT TOP 12 r.reading_date, AVG(m.measured_val) AS avg_ec
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.org_id = ? AND i.indicator_code = 'EC' AND m.measured_val IS NOT NULL
            GROUP BY r.reading_date
            ORDER BY r.reading_date DESC
            """, [org]
        )
        ec_trend = []
        if r_trend:
            for row in reversed(r_trend):
                ec_trend.append({'date': str(row[0]), 'value': round(row[1], 2)})

        return jsonify({
            'success': True,
            'kpis': {
                'total_stations': total_stations,
                'total_readings': total_readings,
                'latest_date': latest_date,
                'compliance_rate': compliance_rate,
                'compliant_count': compliant_count,
                'total_measured': total_meas,
            },
            'alerts': alerts,
            'ec_trend': ec_trend,
        })
    except Exception as exc:
        logger.exception('WQ dashboard error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Stations ──────────────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/stations', methods=['GET'])
@require_wq_auth()
def list_stations():
    org = g.wq_org_id
    try:
        rows = _q(
            """
            SELECT s.station_id, s.station_code, s.station_name, s.description,
                   s.latitude, s.longitude, s.is_active, s.created_at,
                   COUNT(r.reading_id) AS reading_count
            FROM dbo.WQ_Stations s
            LEFT JOIN dbo.WQ_Readings r ON r.station_id = s.station_id
            WHERE s.org_id = ?
            GROUP BY s.station_id, s.station_code, s.station_name, s.description,
                     s.latitude, s.longitude, s.is_active, s.created_at
            ORDER BY s.station_name
            """, [org]
        )
        stations = []
        if rows:
            for r in rows:
                stations.append({
                    'id': r[0], 'code': r[1], 'name': r[2], 'description': r[3],
                    'lat': float(r[4]) if r[4] is not None else None,
                    'lng': float(r[5]) if r[5] is not None else None,
                    'active': bool(r[6]), 'created_at': str(r[7]),
                    'reading_count': r[8],
                })
        return jsonify({'success': True, 'stations': stations})
    except Exception as exc:
        logger.exception('WQ list_stations error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@wq_bp.route('/api/wq/stations', methods=['POST'])
@require_wq_auth(roles=['admin', 'analyst'])
def create_station():
    org = g.wq_org_id
    data = request.get_json(force=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return jsonify({'success': False, 'error': 'Station code and name are required.'}), 400
    try:
        _q(
            """
            INSERT INTO dbo.WQ_Stations (station_code, station_name, description, latitude, longitude, org_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [code, name, data.get('description'), _safe_float(data.get('lat')),
             _safe_float(data.get('lng')), org],
            fetch=False, commit=True
        )
        new_row = _q(
            "SELECT TOP 1 station_id FROM dbo.WQ_Stations WHERE station_code=? AND org_id=? ORDER BY station_id DESC",
            [code, org]
        )
        new_id = new_row[0][0] if new_row else None
        return jsonify({'success': True, 'station_id': new_id}), 201
    except Exception as exc:
        msg = str(exc)
        if '2601' in msg or '2627' in msg:
            return jsonify({'success': False, 'error': f"Station code '{code}' already exists."}), 409
        logger.exception('WQ create_station error')
        return jsonify({'success': False, 'error': msg}), 500


@wq_bp.route('/api/wq/stations/<int:station_id>', methods=['PUT'])
@require_wq_auth(roles=['admin', 'analyst'])
def update_station(station_id):
    org = g.wq_org_id
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Station name is required.'}), 400
    try:
        _q(
            """
            UPDATE dbo.WQ_Stations
            SET station_name=?, description=?, latitude=?, longitude=?, is_active=?
            WHERE station_id=? AND org_id=?
            """,
            [name, data.get('description'), _safe_float(data.get('lat')),
             _safe_float(data.get('lng')), 1 if data.get('active', True) else 0,
             station_id, org],
            fetch=False, commit=True
        )
        return jsonify({'success': True})
    except Exception as exc:
        logger.exception('WQ update_station error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@wq_bp.route('/api/wq/stations/<int:station_id>', methods=['DELETE'])
@require_wq_auth(roles=['admin'])
def delete_station(station_id):
    org = g.wq_org_id
    try:
        _q(
            "DELETE FROM dbo.WQ_Stations WHERE station_id=? AND org_id=?",
            [station_id, org], fetch=False, commit=True
        )
        return jsonify({'success': True})
    except Exception as exc:
        msg = str(exc)
        if 'FK_WQR_Station' in msg or 'REFERENCE' in msg.upper():
            return jsonify({'success': False, 'error': 'Station has readings attached. Delete readings first.'}), 409
        logger.exception('WQ delete_station error')
        return jsonify({'success': False, 'error': msg}), 500


# ── Indicators ────────────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/indicators', methods=['GET'])
@require_wq_auth()
def list_indicators():
    try:
        return jsonify({'success': True, 'indicators': _fetch_indicators()})
    except Exception as exc:
        logger.exception('WQ list_indicators error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Readings list + delete ────────────────────────────────────────────────────

@wq_bp.route('/api/wq/readings', methods=['GET'])
@require_wq_auth()
def list_readings():
    org         = g.wq_org_id
    station_id  = request.args.get('station_id', type=int)
    date_from   = request.args.get('date_from')
    date_to     = request.args.get('date_to')
    page        = request.args.get('page', 1, type=int)
    per_page    = min(request.args.get('per_page', 20, type=int), 100)

    where_clauses = ['r.org_id = ?']
    params        = [org]
    if station_id:
        where_clauses.append('r.station_id = ?')
        params.append(station_id)
    if date_from:
        where_clauses.append('r.reading_date >= ?')
        params.append(date_from)
    if date_to:
        where_clauses.append('r.reading_date <= ?')
        params.append(date_to)

    where_sql = ' AND '.join(where_clauses)
    offset    = (page - 1) * per_page

    try:
        count_row = _q(
            f"SELECT COUNT(*) FROM dbo.WQ_Readings r WHERE {where_sql}", params
        )
        total = count_row[0][0] if count_row else 0

        rows = _q(
            f"""
            SELECT r.reading_id, r.reading_date, s.station_name, s.station_code,
                   r.source_file, r.created_at,
                   COUNT(m.meas_id) AS meas_count,
                   SUM(CASE WHEN m.is_compliant = 0 THEN 1 ELSE 0 END) AS fails
            FROM dbo.WQ_Readings r
            JOIN dbo.WQ_Stations s ON s.station_id = r.station_id
            LEFT JOIN dbo.WQ_Measurements m ON m.reading_id = r.reading_id
            WHERE {where_sql}
            GROUP BY r.reading_id, r.reading_date, s.station_name, s.station_code,
                     r.source_file, r.created_at
            ORDER BY r.reading_date DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            params + [offset, per_page]
        )
        readings = []
        if rows:
            for row in rows:
                readings.append({
                    'id': row[0], 'date': str(row[1]), 'station': row[2],
                    'station_code': row[3], 'source_file': row[4],
                    'created_at': str(row[5]), 'meas_count': row[6], 'fails': row[7] or 0
                })
        return jsonify({
            'success': True, 'readings': readings,
            'total': total, 'page': page, 'per_page': per_page
        })
    except Exception as exc:
        logger.exception('WQ list_readings error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@wq_bp.route('/api/wq/readings/<int:reading_id>', methods=['DELETE'])
@require_wq_auth(roles=['admin', 'analyst'])
def delete_reading(reading_id):
    org = g.wq_org_id
    try:
        check = _q(
            "SELECT reading_id FROM dbo.WQ_Readings WHERE reading_id=? AND org_id=?",
            [reading_id, org]
        )
        if not check:
            return jsonify({'success': False, 'error': 'Reading not found.'}), 404
        _q("DELETE FROM dbo.WQ_Readings WHERE reading_id=?", [reading_id], fetch=False, commit=True)
        return jsonify({'success': True})
    except Exception as exc:
        logger.exception('WQ delete_reading error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Reading detail (all measurements for one event) ───────────────────────────

@wq_bp.route('/api/wq/readings/<int:reading_id>/measurements', methods=['GET'])
@require_wq_auth()
def reading_measurements(reading_id):
    org = g.wq_org_id
    try:
        check = _q(
            "SELECT reading_id FROM dbo.WQ_Readings WHERE reading_id=? AND org_id=?",
            [reading_id, org]
        )
        if not check:
            return jsonify({'success': False, 'error': 'Reading not found.'}), 404
        rows = _q(
            """
            SELECT i.indicator_code, i.indicator_name, i.unit, i.lower_std, i.upper_std,
                   m.measured_val, m.is_compliant, m.flag
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE m.reading_id = ?
            ORDER BY i.display_order
            """, [reading_id]
        )
        measurements = []
        if rows:
            for r in rows:
                measurements.append({
                    'code': r[0], 'name': r[1], 'unit': r[2],
                    'lower_std': r[3], 'upper_std': r[4],
                    'value': r[5], 'compliant': bool(r[6]) if r[6] is not None else None,
                    'flag': r[7],
                })
        return jsonify({'success': True, 'measurements': measurements})
    except Exception as exc:
        logger.exception('WQ reading_measurements error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Compliance matrix ─────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/compliance', methods=['GET'])
@require_wq_auth()
def compliance_matrix():
    """
    Returns a 2-D compliance matrix: rows = indicators, cols = recent reading events.
    Each cell: {value, compliant, flag}.  Used for the heatmap visualisation.
    """
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    limit      = min(request.args.get('limit', 8, type=int), 20)

    where_clauses = ['r.org_id = ?']
    params        = [org]
    if station_id:
        where_clauses.append('r.station_id = ?')
        params.append(station_id)
    where_sql = ' AND '.join(where_clauses)

    try:
        date_rows = _q(
            f"""
            SELECT TOP {limit} r.reading_id, r.reading_date, s.station_name
            FROM dbo.WQ_Readings r
            JOIN dbo.WQ_Stations s ON s.station_id = r.station_id
            WHERE {where_sql}
            ORDER BY r.reading_date DESC
            """, params
        )
        if not date_rows:
            return jsonify({'success': True, 'cols': [], 'rows': []})

        reading_ids  = [str(row[0]) for row in date_rows]
        col_labels   = [{'id': row[0], 'date': str(row[1]), 'station': row[2]} for row in date_rows]

        meas_rows = _q(
            f"""
            SELECT m.reading_id, i.indicator_code, i.indicator_name, i.unit,
                   m.measured_val, m.is_compliant, m.flag
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Indicators   i ON i.indicator_id  = m.indicator_id
            JOIN dbo.WQ_Readings     r ON r.reading_id    = m.reading_id
            WHERE m.reading_id IN ({','.join(['?']*len(reading_ids))})
            ORDER BY i.display_order
            """, reading_ids
        )

        # Build dict: indicator_code → {reading_id → cell}
        ind_map  = {}
        ind_meta = {}
        if meas_rows:
            for mr in meas_rows:
                rid, code, name, unit, val, comp, flag = mr
                if code not in ind_map:
                    ind_map[code]  = {}
                    ind_meta[code] = {'code': code, 'name': name, 'unit': unit}
                ind_map[code][rid] = {
                    'value': round(val, 4) if val is not None else None,
                    'compliant': bool(comp) if comp is not None else None,
                    'flag': flag,
                }

        matrix_rows = []
        for code, cells in ind_map.items():
            row_cells = [cells.get(int(col['id'])) for col in col_labels]
            matrix_rows.append({
                'indicator': ind_meta[code],
                'cells': row_cells,
            })

        return jsonify({'success': True, 'cols': col_labels, 'rows': matrix_rows})
    except Exception as exc:
        logger.exception('WQ compliance_matrix error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Trend series ──────────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/trend', methods=['GET'])
@require_wq_auth()
def wq_trend():
    """Time-series of a single indicator for one (or all) stations."""
    org          = g.wq_org_id
    indicator_code = request.args.get('indicator', 'EC')
    station_id   = request.args.get('station_id', type=int)
    date_from    = request.args.get('date_from')
    date_to      = request.args.get('date_to')

    where_clauses = ['r.org_id = ?', 'i.indicator_code = ?']
    params        = [org, indicator_code]
    if station_id:
        where_clauses.append('r.station_id = ?')
        params.append(station_id)
    if date_from:
        where_clauses.append('r.reading_date >= ?')
        params.append(date_from)
    if date_to:
        where_clauses.append('r.reading_date <= ?')
        params.append(date_to)
    where_sql = ' AND '.join(where_clauses)

    try:
        rows = _q(
            f"""
            SELECT r.reading_date, s.station_name, m.measured_val, m.is_compliant, m.flag,
                   i.upper_std, i.lower_std, i.unit
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id    = m.reading_id
            JOIN dbo.WQ_Stations   s ON s.station_id    = r.station_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id  = m.indicator_id
            WHERE {where_sql} AND m.measured_val IS NOT NULL
            ORDER BY r.reading_date ASC
            """, params
        )

        series = []
        upper_std = lower_std = unit = None
        if rows:
            for row in rows:
                if upper_std is None:
                    upper_std = row[5]
                    lower_std = row[6]
                    unit      = row[7]
                series.append({
                    'date':      str(row[0]),
                    'station':   row[1],
                    'value':     round(row[2], 4),
                    'compliant': bool(row[3]) if row[3] is not None else None,
                    'flag':      row[4],
                })

        return jsonify({
            'success': True,
            'indicator_code': indicator_code,
            'unit': unit,
            'upper_std': upper_std,
            'lower_std': lower_std,
            'series': series,
        })
    except Exception as exc:
        logger.exception('WQ trend error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Excel upload ──────────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/upload', methods=['POST'])
@require_wq_auth(roles=['admin', 'analyst'])
def wq_upload():
    """
    Accept an Excel file (.xlsx).  Expected format (generated by /api/wq/template):
      Row 1 : headers — 'Reading Date', 'Station Name', <indicator names>
      Row 2+: data rows
    Each row becomes one WQ_Readings record + measurements per indicator column found.
    """
    org     = g.wq_org_id
    user_id = g.wq_user_id

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file attached.'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Only .xlsx / .xls files are accepted.'}), 400

    try:
        df = pd.read_excel(f, header=0, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]

        # Map column index → indicator
        header_map = _header_to_code_map()
        col_to_code = {}
        for col in df.columns:
            norm = col.lower().strip()
            if norm in header_map:
                col_to_code[col] = header_map[norm]

        if not col_to_code:
            return jsonify({'success': False, 'error': 'No recognisable indicator columns found. Please use the provided template.'}), 400

        # Pre-fetch org stations → name lookup
        st_rows = _q(
            "SELECT station_name, station_id FROM dbo.WQ_Stations WHERE org_id=? AND is_active=1",
            [org]
        )
        station_lookup = {r[0].strip().lower(): r[1] for r in st_rows} if st_rows else {}

        # Pre-fetch indicators → thresholds + metadata for alert dispatch
        ind_rows = _q(
            "SELECT indicator_code, indicator_id, lower_std, upper_std, indicator_name, unit, risk_class "
            "FROM dbo.WQ_Indicators"
        )
        ind_lookup = {}
        if ind_rows:
            for r in ind_rows:
                ind_lookup[r[0]] = {
                    'id': r[1], 'lower': r[2], 'upper': r[3],
                    'name': r[4], 'unit': r[5], 'risk_class': r[6],
                }

        inserted  = 0
        skipped   = 0
        errors    = []

        for row_i, row in df.iterrows():
            human_row = row_i + 2  # Excel row number

            # Reading date
            raw_date = str(row.get('Reading Date', '') or '').strip()
            if not raw_date or raw_date.lower() in ('nan', 'reading date'):
                continue
            try:
                reading_date = pd.to_datetime(raw_date, dayfirst=False).date()
            except Exception:
                errors.append(f"Row {human_row}: unrecognised date '{raw_date}'")
                skipped += 1
                continue

            # Station
            raw_station = str(row.get('Station Name', '') or '').strip()
            if not raw_station or raw_station.lower() == 'nan':
                errors.append(f"Row {human_row}: station name is blank.")
                skipped += 1
                continue
            station_id = station_lookup.get(raw_station.lower())
            if not station_id:
                errors.append(f"Row {human_row}: station '{raw_station}' not found.")
                skipped += 1
                continue

            # Insert or find reading event
            existing = _q(
                "SELECT reading_id FROM dbo.WQ_Readings WHERE station_id=? AND reading_date=?",
                [station_id, reading_date]
            )
            if existing:
                reading_id = existing[0][0]
            else:
                _q(
                    "INSERT INTO dbo.WQ_Readings (station_id, reading_date, source_file, uploaded_by, org_id) VALUES (?,?,?,?,?)",
                    [station_id, reading_date, f.filename, user_id, org],
                    fetch=False, commit=True
                )
                new_r = _q(
                    "SELECT TOP 1 reading_id FROM dbo.WQ_Readings WHERE station_id=? AND reading_date=?",
                    [station_id, reading_date]
                )
                reading_id = new_r[0][0]

            # Measurements
            for col, code in col_to_code.items():
                raw_val = _safe_float(row.get(col))
                ind     = ind_lookup.get(code)
                if not ind:
                    continue
                compliant, flag = _compute_compliance(raw_val, ind['lower'], ind['upper'])

                ex_m = _q(
                    "SELECT meas_id FROM dbo.WQ_Measurements m JOIN dbo.WQ_Indicators i ON i.indicator_id=m.indicator_id "
                    "WHERE m.reading_id=? AND i.indicator_code=?",
                    [reading_id, code]
                )
                if ex_m:
                    _q(
                        "UPDATE dbo.WQ_Measurements SET measured_val=?, is_compliant=?, flag=?, quality_flag='Approved' "
                        "WHERE meas_id=?",
                        [raw_val, compliant, flag, ex_m[0][0]],
                        fetch=False, commit=True
                    )
                else:
                    _q(
                        "INSERT INTO dbo.WQ_Measurements "
                        "(reading_id, indicator_id, measured_val, is_compliant, flag, quality_flag) "
                        "VALUES (?,?,?,?,?,'Approved')",
                        [reading_id, ind['id'], raw_val, compliant, flag],
                        fetch=False, commit=True
                    )

                # Dispatch alerts for health-risk non-compliant measurements
                if compliant is False and ind.get('risk_class') == 'health' and flag:
                    threshold = ind['upper'] if flag == 'ABOVE' else ind['lower']
                    try:
                        dispatch_alert(
                            db_query_fn    = _q,
                            org_id         = org,
                            reading_id     = reading_id,
                            indicator_id   = ind['id'],
                            indicator_code = code,
                            indicator_name = ind['name'],
                            unit           = ind['unit'] or '',
                            measured_val   = raw_val,
                            threshold_value= threshold,
                            threshold_type = flag,
                            station_name   = raw_station,
                            reading_date   = str(reading_date),
                        )
                    except Exception:
                        logger.exception('Alert dispatch failed for %s reading_id=%s', code, reading_id)

            inserted += 1

        return jsonify({
            'success': True,
            'inserted': inserted,
            'skipped': skipped,
            'errors': errors[:20],
        })
    except Exception as exc:
        logger.exception('WQ upload error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Upload template download ──────────────────────────────────────────────────

@wq_bp.route('/api/wq/template', methods=['GET'])
@require_wq_auth()
def wq_template():
    """Return a blank Excel upload template with correct headers."""
    try:
        indicators = _fetch_indicators()
        wb = Workbook()
        ws = wb.active
        ws.title = 'Water Quality Data'

        header_fill = _teal_fill()
        header_font = _header_font()

        headers = ['Reading Date', 'Station Name']
        for ind in indicators:
            label = ind['name'] + (f" ({ind['unit']})" if ind['unit'] else '')
            headers.append(label)

        for ci, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.fill   = header_fill
            cell.font   = header_font
            cell.alignment = Alignment(horizontal='center', wrap_text=True)
            cell.border = _thin_border()
            ws.column_dimensions[get_column_letter(ci)].width = max(len(h) + 4, 16)

        ws.row_dimensions[1].height = 28

        # Sample row
        ws.cell(row=2, column=1, value='2024-01-15')
        ws.cell(row=2, column=2, value='Station A')
        for ci in range(3, len(headers) + 1):
            ws.cell(row=2, column=ci, value='')

        # Notes row
        note_cell = ws.cell(
            row=3, column=1,
            value='NOTE: Date format YYYY-MM-DD. Station Name must match an existing station exactly.'
        )
        note_cell.font = Font(italic=True, color='888888', size=9)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='water_quality_upload_template.xlsx',
        )
    except Exception as exc:
        logger.exception('WQ template error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Data export ───────────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/export', methods=['GET'])
@require_wq_auth()
def wq_export():
    """Export all readings (filtered by station/date) as a flat Excel sheet."""
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')

    where_clauses = ['r.org_id = ?']
    params        = [org]
    if station_id:
        where_clauses.append('r.station_id = ?')
        params.append(station_id)
    if date_from:
        where_clauses.append('r.reading_date >= ?')
        params.append(date_from)
    if date_to:
        where_clauses.append('r.reading_date <= ?')
        params.append(date_to)
    where_sql = ' AND '.join(where_clauses)

    try:
        rows = _q(
            f"""
            SELECT r.reading_date, s.station_name, s.station_code,
                   i.indicator_code, i.indicator_name, i.unit,
                   m.measured_val, m.is_compliant, m.flag
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Stations   s ON s.station_id   = r.station_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE {where_sql}
            ORDER BY r.reading_date DESC, s.station_name, i.display_order
            """, params
        )

        indicators = _fetch_indicators()
        ind_codes  = [i['code'] for i in indicators]

        wb  = Workbook()
        ws  = wb.active
        ws.title = 'WQ Export'

        fill = _teal_fill()
        hdr_font = _header_font()

        fixed_headers = ['Reading Date', 'Station Name', 'Station Code']
        all_headers   = fixed_headers + [
            i['name'] + (f" ({i['unit']})" if i['unit'] else '') for i in indicators
        ] + ['Compliance Status']

        for ci, h in enumerate(all_headers, start=1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.fill   = fill
            cell.font   = hdr_font
            cell.alignment = Alignment(horizontal='center')
            ws.column_dimensions[get_column_letter(ci)].width = max(len(h) + 2, 14)

        # Pivot: group by (date, station)
        from collections import defaultdict
        pivot = defaultdict(dict)
        pivot_meta = {}
        if rows:
            for row in rows:
                date_, sname, scode, icode, _, _, val, comp, flag = row
                key = (str(date_), sname, scode)
                pivot[key][icode] = (val, bool(comp) if comp is not None else None)
                pivot_meta[key] = True

        row_i = 2
        for key in sorted(pivot.keys()):
            date_, sname, scode = key
            ws.cell(row=row_i, column=1, value=date_)
            ws.cell(row=row_i, column=2, value=sname)
            ws.cell(row=row_i, column=3, value=scode)
            cell_data  = pivot[key]
            all_comp   = [v[1] for v in cell_data.values() if v[1] is not None]
            overall    = 'Compliant' if all_comp and all(all_comp) else ('Non-Compliant' if any(c is False for c in all_comp) else 'No Standard')
            for ci, ind in enumerate(indicators, start=4):
                pair = cell_data.get(ind['code'])
                ws.cell(row=row_i, column=ci, value=pair[0] if pair else None)
            ws.cell(row=row_i, column=len(fixed_headers) + len(indicators) + 1, value=overall)
            row_i += 1

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'wq_export_{date.today().isoformat()}.xlsx',
        )
    except Exception as exc:
        logger.exception('WQ export error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Quality flag bulk PATCH ───────────────────────────────────────────────────

@wq_bp.route('/api/wq/measurements/quality-flags', methods=['PATCH'])
@require_wq_auth(roles=['admin', 'analyst'])
def patch_quality_flags():
    """
    Bulk-update quality_flag on a set of measurement IDs.
    Body: {meas_ids: [int], quality_flag: str}
    Valid flags: Approved | Preliminary | Estimated | Questionable | Rejected
    """
    org  = g.wq_org_id
    data = request.get_json(force=True) or {}
    meas_ids = data.get('meas_ids', [])
    new_flag = (data.get('quality_flag') or '').strip()

    VALID_FLAGS = {'Approved', 'Preliminary', 'Estimated', 'Questionable', 'Rejected'}
    if new_flag not in VALID_FLAGS:
        return jsonify({'success': False, 'error': f"Invalid flag. Must be one of: {', '.join(VALID_FLAGS)}"}), 400
    if not meas_ids or not isinstance(meas_ids, list):
        return jsonify({'success': False, 'error': 'meas_ids must be a non-empty list.'}), 400

    try:
        placeholders = ','.join(['?'] * len(meas_ids))
        _q(
            f"""
            UPDATE dbo.WQ_Measurements
            SET quality_flag = ?
            WHERE meas_id IN ({placeholders})
              AND reading_id IN (SELECT reading_id FROM dbo.WQ_Readings WHERE org_id = ?)
            """,
            [new_flag] + list(meas_ids) + [org],
            fetch=False, commit=True
        )
        return jsonify({'success': True, 'updated': len(meas_ids)})
    except Exception as exc:
        logger.exception('WQ patch_quality_flags error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── CCME Water Quality Index ──────────────────────────────────────────────────

@wq_bp.route('/api/wq/wqi', methods=['GET'])
@require_wq_auth()
def wq_wqi():
    """
    Compute CCME-WQI for a station over a date range.
    Query: station_id (required), date_from, date_to, approved_only (1|0, default 1)
    """
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')
    approved_only = request.args.get('approved_only', '1') != '0'

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    try:
        # Verify station belongs to org
        st_check = _q("SELECT station_id FROM dbo.WQ_Stations WHERE station_id=? AND org_id=?", [station_id, org])
        if not st_check:
            return jsonify({'success': False, 'error': 'Station not found.'}), 404

        where_extra = ''
        params = [station_id]
        if date_from:
            where_extra += ' AND r.reading_date >= ?'
            params.append(date_from)
        if date_to:
            where_extra += ' AND r.reading_date <= ?'
            params.append(date_to)

        rows = _q(
            f"""
            SELECT i.indicator_code, m.measured_val, i.lower_std, i.upper_std,
                   m.quality_flag, m.is_censored
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? {where_extra}
            """,
            params
        )

        measurements = []
        if rows:
            for row in rows:
                measurements.append({
                    'indicator_code': row[0],
                    'measured_val':   row[1],
                    'lower_std':      row[2],
                    'upper_std':      row[3],
                    'quality_flag':   row[4],
                    'is_censored':    bool(row[5]) if row[5] is not None else False,
                })

        result = compute_ccme_wqi(measurements, approved_only=approved_only)
        return jsonify({'success': True, 'wqi': result})
    except Exception as exc:
        logger.exception('WQ wqi error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Ion Balance Error ─────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/readings/<int:reading_id>/ion-balance', methods=['GET'])
@require_wq_auth()
def reading_ion_balance(reading_id):
    """Compute charge balance error for one reading event."""
    org = g.wq_org_id
    try:
        check = _q("SELECT reading_id FROM dbo.WQ_Readings WHERE reading_id=? AND org_id=?", [reading_id, org])
        if not check:
            return jsonify({'success': False, 'error': 'Reading not found.'}), 404

        rows = _q(
            """
            SELECT i.indicator_code, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE m.reading_id = ? AND m.measured_val IS NOT NULL AND m.is_censored = 0
            """,
            [reading_id]
        )
        conc = {r[0]: r[1] for r in rows} if rows else {}
        result = compute_ion_balance_error(conc)

        # Cache IBE in WQ_Readings
        if result['IBE_pct'] is not None:
            _q(
                "UPDATE dbo.WQ_Readings SET ion_balance_error_pct=? WHERE reading_id=?",
                [result['IBE_pct'], reading_id],
                fetch=False, commit=True
            )

        return jsonify({'success': True, 'ion_balance': result})
    except Exception as exc:
        logger.exception('WQ ion_balance error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Blue Drop Scoring ─────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/blue-drop', methods=['GET'])
@require_wq_auth()
def wq_blue_drop():
    """
    Compute Blue Drop compliance score for the organisation.
    Query: date_from, date_to  (optional)
    """
    org       = g.wq_org_id
    date_from = request.args.get('date_from')
    date_to   = request.args.get('date_to')

    where_extra = ''
    params = [org]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT i.blue_drop_category,
                   COUNT(*) AS total_tests,
                   SUM(CASE WHEN m.is_compliant = 1 THEN 1 ELSE 0 END) AS passed
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.org_id = ?
              AND i.blue_drop_category IS NOT NULL
              AND m.is_compliant IS NOT NULL
              AND m.quality_flag = 'Approved'
              {where_extra}
            GROUP BY i.blue_drop_category
            """,
            params
        )

        compliance_by_category = {}
        category_counts = {}
        if rows:
            for row in rows:
                cat, total, passed = row
                if cat and total > 0:
                    compliance_by_category[cat] = round(passed / total * 100.0, 1)
                    category_counts[cat] = {'total': total, 'passed': passed}

        result = compute_blue_drop_score(compliance_by_category)
        result['category_counts'] = category_counts
        return jsonify({'success': True, 'blue_drop': result})
    except Exception as exc:
        logger.exception('WQ blue_drop error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Alert Config CRUD ─────────────────────────────────────────────────────────

@wq_bp.route('/api/wq/alerts/config', methods=['GET'])
@require_wq_auth()
def list_alert_configs():
    org = g.wq_org_id
    try:
        rows = _q(
            """
            SELECT ac.alert_id, i.indicator_name, i.unit, s.station_name,
                   ac.threshold_type, ac.threshold_value, ac.alert_email,
                   ac.alert_whatsapp, ac.is_active, ac.created_at
            FROM dbo.WQ_Alert_Config ac
            JOIN dbo.WQ_Indicators i ON i.indicator_id = ac.indicator_id
            LEFT JOIN dbo.WQ_Stations s ON s.station_id = ac.station_id
            WHERE ac.org_id = ?
            ORDER BY ac.created_at DESC
            """,
            [org]
        )
        configs = []
        if rows:
            for r in rows:
                configs.append({
                    'id': r[0], 'indicator': r[1], 'unit': r[2],
                    'station': r[3] or 'All stations',
                    'threshold_type': r[4], 'threshold_value': r[5],
                    'alert_email': r[6], 'alert_whatsapp': r[7],
                    'is_active': bool(r[8]), 'created_at': str(r[9]),
                })
        return jsonify({'success': True, 'configs': configs})
    except Exception as exc:
        logger.exception('WQ list_alert_configs error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@wq_bp.route('/api/wq/alerts/config', methods=['POST'])
@require_wq_auth(roles=['admin', 'analyst'])
def create_alert_config():
    org  = g.wq_org_id
    data = request.get_json(force=True) or {}

    indicator_id    = data.get('indicator_id')
    station_id      = data.get('station_id') or None
    threshold_type  = (data.get('threshold_type') or '').strip().upper()
    threshold_value = _safe_float(data.get('threshold_value'))
    alert_email     = (data.get('alert_email') or '').strip() or None
    alert_whatsapp  = (data.get('alert_whatsapp') or '').strip() or None

    if not indicator_id:
        return jsonify({'success': False, 'error': 'indicator_id is required.'}), 400
    if threshold_type not in ('ABOVE', 'BELOW', 'HEALTH'):
        return jsonify({'success': False, 'error': "threshold_type must be ABOVE, BELOW, or HEALTH."}), 400
    if threshold_value is None:
        return jsonify({'success': False, 'error': 'threshold_value is required.'}), 400
    if not alert_email and not alert_whatsapp:
        return jsonify({'success': False, 'error': 'At least one of alert_email or alert_whatsapp is required.'}), 400

    try:
        _q(
            """
            INSERT INTO dbo.WQ_Alert_Config
                (org_id, indicator_id, station_id, threshold_type, threshold_value,
                 alert_email, alert_whatsapp)
            VALUES (?,?,?,?,?,?,?)
            """,
            [org, indicator_id, station_id, threshold_type, threshold_value,
             alert_email, alert_whatsapp],
            fetch=False, commit=True
        )
        new_row = _q(
            "SELECT TOP 1 alert_id FROM dbo.WQ_Alert_Config WHERE org_id=? ORDER BY alert_id DESC",
            [org]
        )
        return jsonify({'success': True, 'alert_id': new_row[0][0] if new_row else None}), 201
    except Exception as exc:
        logger.exception('WQ create_alert_config error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@wq_bp.route('/api/wq/alerts/config/<int:alert_id>', methods=['DELETE'])
@require_wq_auth(roles=['admin'])
def delete_alert_config(alert_id):
    org = g.wq_org_id
    try:
        _q(
            "DELETE FROM dbo.WQ_Alert_Config WHERE alert_id=? AND org_id=?",
            [alert_id, org], fetch=False, commit=True
        )
        return jsonify({'success': True})
    except Exception as exc:
        logger.exception('WQ delete_alert_config error')
        return jsonify({'success': False, 'error': str(exc)}), 500


@wq_bp.route('/api/wq/alerts/log', methods=['GET'])
@require_wq_auth()
def alert_log():
    org      = g.wq_org_id
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    offset   = (page - 1) * per_page
    try:
        total_row = _q("SELECT COUNT(*) FROM dbo.WQ_Alert_Log WHERE org_id=?", [org])
        total     = total_row[0][0] if total_row else 0

        rows = _q(
            """
            SELECT al.log_id, i.indicator_name, al.measured_val,
                   al.channel, al.recipient, al.status, al.dispatched_at,
                   s.station_name
            FROM dbo.WQ_Alert_Log al
            JOIN dbo.WQ_Indicators i ON i.indicator_id = al.indicator_id
            JOIN dbo.WQ_Readings   r ON r.reading_id   = al.reading_id
            JOIN dbo.WQ_Stations   s ON s.station_id   = r.station_id
            WHERE al.org_id = ?
            ORDER BY al.dispatched_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            [org, offset, per_page]
        )
        logs = []
        if rows:
            for r in rows:
                logs.append({
                    'id': r[0], 'indicator': r[1], 'value': r[2],
                    'channel': r[3], 'recipient': r[4], 'status': r[5],
                    'dispatched_at': str(r[6]), 'station': r[7],
                })
        return jsonify({'success': True, 'logs': logs, 'total': total, 'page': page})
    except Exception as exc:
        logger.exception('WQ alert_log error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Piper Diagram ──────────────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/piper', methods=['GET'])
@require_wq_auth()
def analytics_piper():
    """
    Return Piper diagram data for one or more stations / readings.
    Query: station_id (repeat for multiple), date_from, date_to
    Each reading event becomes one point.
    """
    org        = g.wq_org_id
    station_ids = request.args.getlist('station_id', type=int)
    date_from   = request.args.get('date_from')
    date_to     = request.args.get('date_to')

    where_clauses = ['r.org_id = ?']
    params        = [org]
    if station_ids:
        placeholders = ','.join(['?'] * len(station_ids))
        where_clauses.append(f'r.station_id IN ({placeholders})')
        params.extend(station_ids)
    if date_from:
        where_clauses.append('r.reading_date >= ?')
        params.append(date_from)
    if date_to:
        where_clauses.append('r.reading_date <= ?')
        params.append(date_to)
    where_sql = ' AND '.join(where_clauses)

    try:
        rows = _q(
            f"""
            SELECT r.reading_id, r.reading_date, s.station_name,
                   i.indicator_code, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Stations   s ON s.station_id   = r.station_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE {where_sql}
              AND i.indicator_code IN ('CA','MG','NA','K','HCO3','CO3','CL','SO4')
              AND m.measured_val IS NOT NULL
              AND m.is_censored = 0
              AND m.quality_flag = 'Approved'
            ORDER BY r.reading_date
            """,
            params
        )

        # Group by reading_id
        from collections import defaultdict
        readings_map = defaultdict(lambda: {'date': None, 'station': None, 'conc': {}})
        if rows:
            for row in rows:
                rid, rdate, sname, code, val = row
                readings_map[rid]['date']    = str(rdate)
                readings_map[rid]['station'] = sname
                readings_map[rid]['conc'][code] = val

        points = []
        for rid, info in readings_map.items():
            piper = compute_piper_data(info['conc'])
            points.append({
                'reading_id': rid,
                'date':       info['date'],
                'station':    info['station'],
                **piper,
            })

        return jsonify({'success': True, 'points': points})
    except Exception as exc:
        logger.exception('WQ analytics_piper error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Stiff Diagram ──────────────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/stiff', methods=['GET'])
@require_wq_auth()
def analytics_stiff():
    """
    Return Stiff diagram polygon data for recent readings.
    Query: station_id (repeat), date_from, date_to, limit (max 10)
    """
    org         = g.wq_org_id
    station_ids = request.args.getlist('station_id', type=int)
    date_from   = request.args.get('date_from')
    date_to     = request.args.get('date_to')
    limit       = min(request.args.get('limit', 5, type=int), 10)

    where_clauses = ['r.org_id = ?']
    params        = [org]
    if station_ids:
        placeholders = ','.join(['?'] * len(station_ids))
        where_clauses.append(f'r.station_id IN ({placeholders})')
        params.extend(station_ids)
    if date_from:
        where_clauses.append('r.reading_date >= ?')
        params.append(date_from)
    if date_to:
        where_clauses.append('r.reading_date <= ?')
        params.append(date_to)
    where_sql = ' AND '.join(where_clauses)

    try:
        reading_rows = _q(
            f"""
            SELECT TOP {limit} r.reading_id, r.reading_date, s.station_name
            FROM dbo.WQ_Readings r
            JOIN dbo.WQ_Stations s ON s.station_id = r.station_id
            WHERE {where_sql}
            ORDER BY r.reading_date DESC
            """,
            params
        )
        if not reading_rows:
            return jsonify({'success': True, 'diagrams': []})

        reading_ids = [r[0] for r in reading_rows]
        reading_meta = {r[0]: {'date': str(r[1]), 'station': r[2]} for r in reading_rows}

        meas_rows = _q(
            f"""
            SELECT m.reading_id, i.indicator_code, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE m.reading_id IN ({','.join(['?']*len(reading_ids))})
              AND i.indicator_code IN ('CA','MG','NA','K','HCO3','CO3','CL','SO4')
              AND m.measured_val IS NOT NULL AND m.is_censored = 0
            """,
            reading_ids
        )

        from collections import defaultdict
        conc_map = defaultdict(dict)
        if meas_rows:
            for rid, code, val in meas_rows:
                conc_map[rid][code] = val

        diagrams = []
        for rid in reading_ids:
            meta = reading_meta[rid]
            label = f"{meta['station']} — {meta['date']}"
            stiff = compute_stiff_data(conc_map[rid], label=label)
            stiff['reading_id'] = rid
            stiff['date']       = meta['date']
            stiff['station']    = meta['station']
            diagrams.append(stiff)

        return jsonify({'success': True, 'diagrams': diagrams})
    except Exception as exc:
        logger.exception('WQ analytics_stiff error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Mann-Kendall Trend ─────────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/mann-kendall', methods=['GET'])
@require_wq_auth()
def analytics_mann_kendall():
    """
    Mann-Kendall trend test for one indicator at one station.
    Query: station_id (required), indicator (code, default EC), date_from, date_to
    """
    org            = g.wq_org_id
    station_id     = request.args.get('station_id', type=int)
    indicator_code = request.args.get('indicator', 'EC')
    date_from      = request.args.get('date_from')
    date_to        = request.args.get('date_to')

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    where_extra = ''
    params = [station_id, org, indicator_code]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT r.reading_date, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? AND r.org_id = ? AND i.indicator_code = ?
              AND m.measured_val IS NOT NULL AND m.is_censored = 0
              AND m.quality_flag = 'Approved'
              {where_extra}
            ORDER BY r.reading_date
            """,
            params
        )

        dates  = [r[0] for r in rows] if rows else []
        values = [r[1] for r in rows] if rows else []

        result = compute_mann_kendall(dates, values)
        result['indicator_code'] = indicator_code
        return jsonify({'success': True, 'mann_kendall': result})
    except Exception as exc:
        logger.exception('WQ analytics_mann_kendall error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Langelier Saturation Index ─────────────────────────────────────

@wq_bp.route('/api/wq/analytics/lsi', methods=['GET'])
@require_wq_auth()
def analytics_lsi():
    """
    LSI and RSI for each reading at a station.
    Query: station_id (required), date_from, date_to
    Requires: PH, TEMP, TDS (or EC→TDS conversion), CA, ALK measurements.
    """
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    where_extra = ''
    params = [station_id, org]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT r.reading_id, r.reading_date, i.indicator_code, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? AND r.org_id = ?
              AND i.indicator_code IN ('PH','TEMP','TDS','EC','CA','ALK','HARD')
              AND m.measured_val IS NOT NULL
              {where_extra}
            ORDER BY r.reading_date
            """,
            params
        )

        from collections import defaultdict
        reading_vals = defaultdict(dict)
        reading_dates = {}
        if rows:
            for rid, rdate, code, val in rows:
                reading_vals[rid][code] = val
                reading_dates[rid] = str(rdate)

        results = []
        for rid, vals in reading_vals.items():
            pH   = vals.get('PH')
            temp = vals.get('TEMP', 20.0)
            tds  = vals.get('TDS') or (vals.get('EC', 0) * 0.64 if vals.get('EC') else None)
            ca   = vals.get('CA')
            alk  = vals.get('ALK') or (vals.get('HARD', 0) * 0.5 if vals.get('HARD') else None)

            if pH is None or tds is None or ca is None or alk is None:
                results.append({
                    'reading_id': rid, 'date': reading_dates[rid],
                    'lsi': None, 'error': 'Missing required parameters (PH, TDS/EC, CA, ALK/HARD)'
                })
                continue

            lsi_data = compute_lsi(pH, temp or 20.0, tds, ca, alk)
            results.append({
                'reading_id': rid,
                'date':       reading_dates[rid],
                **lsi_data,
            })

        return jsonify({'success': True, 'lsi_series': results})
    except Exception as exc:
        logger.exception('WQ analytics_lsi error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Eutrophication ─────────────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/eutrophication', methods=['GET'])
@require_wq_auth()
def analytics_eutrophication():
    """
    Carlson TSI for each reading at a station.
    Query: station_id (required), date_from, date_to
    Uses: TP (µg/L), CHLA (µg/L), SECCHI (m)
    """
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    where_extra = ''
    params = [station_id, org]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT r.reading_id, r.reading_date, i.indicator_code, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? AND r.org_id = ?
              AND i.indicator_code IN ('TP','CHLA','SECCHI')
              AND m.measured_val IS NOT NULL
              {where_extra}
            ORDER BY r.reading_date
            """,
            params
        )

        from collections import defaultdict
        rv = defaultdict(dict)
        rd = {}
        if rows:
            for rid, rdate, code, val in rows:
                rv[rid][code] = val
                rd[rid] = str(rdate)

        results = []
        for rid, vals in rv.items():
            tsi = compute_trophic_state_index(
                tp_ug_L    = vals.get('TP'),
                chl_a_ug_L = vals.get('CHLA'),
                secchi_m   = vals.get('SECCHI'),
            )
            results.append({'reading_id': rid, 'date': rd[rid], **tsi})

        return jsonify({'success': True, 'eutrophication': results})
    except Exception as exc:
        logger.exception('WQ analytics_eutrophication error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: AMD Assessment ─────────────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/amd', methods=['GET'])
@require_wq_auth()
def analytics_amd():
    """
    Acid Mine Drainage (AMD) indicators for a station.
    Flags readings as AMD-suspect based on SA Witwatersrand criteria.
    pH ≤ 4, EC > 500 mS/m, SO4 > 1000 mg/L, Fe(total) > 10 mg/L
    """
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    where_extra = ''
    params = [station_id, org]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT r.reading_id, r.reading_date, i.indicator_code, m.measured_val
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? AND r.org_id = ?
              AND i.indicator_code IN ('PH','EC','SO4','FE','FE2','FE3','TOTAL_ACID','MN','AS')
              AND m.measured_val IS NOT NULL
              {where_extra}
            ORDER BY r.reading_date
            """,
            params
        )

        from collections import defaultdict
        rv = defaultdict(dict)
        rd = {}
        if rows:
            for rid, rdate, code, val in rows:
                rv[rid][code] = val
                rd[rid] = str(rdate)

        # AMD flagging thresholds (SA Witwatersrand Goldfields baseline)
        AMD_THRESHOLDS = {
            'PH':  ('<=', 4.0,    'Acidic — AMD indicator'),
            'EC':  ('>=', 500.0,  'Very high EC — AMD indicator'),
            'SO4': ('>=', 1000.0, 'High sulphate — AMD indicator'),
            'FE':  ('>=', 10.0,   'Elevated iron — AMD indicator'),
        }

        results = []
        for rid, vals in rv.items():
            flags = []
            for code, (op, threshold, desc) in AMD_THRESHOLDS.items():
                v = vals.get(code)
                if v is None:
                    continue
                if op == '<=' and v <= threshold:
                    flags.append({'indicator': code, 'value': v, 'threshold': threshold, 'note': desc})
                elif op == '>=' and v >= threshold:
                    flags.append({'indicator': code, 'value': v, 'threshold': threshold, 'note': desc})

            amd_risk = 'High' if len(flags) >= 3 else ('Moderate' if len(flags) >= 2 else ('Low' if len(flags) >= 1 else 'None'))

            results.append({
                'reading_id':  rid,
                'date':        rd[rid],
                'parameters':  vals,
                'amd_flags':   flags,
                'amd_risk':    amd_risk,
                'is_amd_suspect': len(flags) >= 2,
            })

        return jsonify({'success': True, 'amd': results})
    except Exception as exc:
        logger.exception('WQ analytics_amd error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Seasonal Comparison ───────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/seasonal', methods=['GET'])
@require_wq_auth()
def analytics_seasonal():
    """
    Compare mean values per indicator between Wet and Dry seasons.
    SA Wet season = Oct–Apr, Dry = May–Sep.
    Query: station_id (required), date_from, date_to
    """
    org        = g.wq_org_id
    station_id = request.args.get('station_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    where_extra = ''
    params = [station_id, org]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT i.indicator_code, i.indicator_name, i.unit,
                   CASE WHEN MONTH(r.reading_date) IN (10,11,12,1,2,3,4)
                        THEN 'Wet' ELSE 'Dry' END AS season,
                   AVG(m.measured_val)  AS mean_val,
                   MIN(m.measured_val)  AS min_val,
                   MAX(m.measured_val)  AS max_val,
                   COUNT(m.meas_id)     AS n
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? AND r.org_id = ?
              AND m.measured_val IS NOT NULL
              AND m.quality_flag IN ('Approved', 'Estimated')
              {where_extra}
            GROUP BY i.indicator_code, i.indicator_name, i.unit,
                     CASE WHEN MONTH(r.reading_date) IN (10,11,12,1,2,3,4)
                          THEN 'Wet' ELSE 'Dry' END
            ORDER BY i.display_order
            """,
            params
        )

        from collections import defaultdict
        by_indicator = defaultdict(lambda: {'wet': None, 'dry': None, 'name': None, 'unit': None})
        if rows:
            for code, name, unit, season, mean, mn, mx, n in rows:
                by_indicator[code]['name'] = name
                by_indicator[code]['unit'] = unit
                entry = {'mean': round(mean, 4) if mean is not None else None,
                         'min': round(mn, 4) if mn is not None else None,
                         'max': round(mx, 4) if mx is not None else None,
                         'n': n}
                if season == 'Wet':
                    by_indicator[code]['wet'] = entry
                else:
                    by_indicator[code]['dry'] = entry

        results = [
            {'code': code, 'name': v['name'], 'unit': v['unit'],
             'wet': v['wet'], 'dry': v['dry']}
            for code, v in by_indicator.items()
        ]

        return jsonify({'success': True, 'seasonal': results})
    except Exception as exc:
        logger.exception('WQ analytics_seasonal error')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Analytics: Pollution Load ─────────────────────────────────────────────────

@wq_bp.route('/api/wq/analytics/pollution-load', methods=['GET'])
@require_wq_auth()
def analytics_pollution_load():
    """
    Calculate pollution load (kg/day) for each reading that has a flow rate.
    Load = concentration (mg/L) × flow (m³/s) × 86.4
    Query: station_id (required), indicator (code, default TDS), date_from, date_to
    """
    org            = g.wq_org_id
    station_id     = request.args.get('station_id', type=int)
    indicator_code = request.args.get('indicator', 'TDS')
    date_from      = request.args.get('date_from')
    date_to        = request.args.get('date_to')

    if not station_id:
        return jsonify({'success': False, 'error': 'station_id is required.'}), 400

    where_extra = ''
    params = [station_id, org, indicator_code]
    if date_from:
        where_extra += ' AND r.reading_date >= ?'
        params.append(date_from)
    if date_to:
        where_extra += ' AND r.reading_date <= ?'
        params.append(date_to)

    try:
        rows = _q(
            f"""
            SELECT r.reading_id, r.reading_date, r.flow_rate_m3s,
                   m.measured_val, i.unit
            FROM dbo.WQ_Measurements m
            JOIN dbo.WQ_Readings   r ON r.reading_id   = m.reading_id
            JOIN dbo.WQ_Indicators i ON i.indicator_id = m.indicator_id
            WHERE r.station_id = ? AND r.org_id = ?
              AND i.indicator_code = ?
              AND m.measured_val IS NOT NULL
              {where_extra}
            ORDER BY r.reading_date
            """,
            params
        )

        results = []
        if rows:
            for rid, rdate, flow, val, unit in rows:
                load_kg_day = None
                if flow is not None and flow > 0 and val is not None:
                    load_kg_day = round(val * flow * 86.4, 2)
                results.append({
                    'reading_id':   rid,
                    'date':         str(rdate),
                    'concentration': val,
                    'unit':          unit,
                    'flow_m3s':     flow,
                    'load_kg_day':  load_kg_day,
                })

        return jsonify({
            'success':        True,
            'indicator_code': indicator_code,
            'series':         results,
            'note':           'Load (kg/day) = Concentration (mg/L) × Flow (m³/s) × 86.4. Requires flow_rate_m3s on each reading.',
        })
    except Exception as exc:
        logger.exception('WQ analytics_pollution_load error')
        return jsonify({'success': False, 'error': str(exc)}), 500
