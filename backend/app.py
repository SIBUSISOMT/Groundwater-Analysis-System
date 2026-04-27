import os
import sys
import json
import logging
import traceback
import tempfile
from datetime import datetime, timedelta
from io import StringIO, BytesIO

import pandas as pd
import numpy as np
import pyodbc
from flask import Flask, g, jsonify, request, send_file, send_from_directory, redirect
from werkzeug.utils import secure_filename
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


app = Flask(__name__)

# ── CORS — allow Flask origin + common Live Server ports for development ──────
_allowed_origins = os.getenv(
    'ALLOWED_ORIGINS',
    'http://localhost:5000,http://127.0.0.1:5000,'
    'http://localhost:5500,http://127.0.0.1:5500,'
    'http://localhost:5501,http://127.0.0.1:5501,'
    'http://localhost:5127,http://127.0.0.1:5127'
).split(',')
CORS(app, origins=_allowed_origins, supports_credentials=True)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[])

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('groundwater_analysis.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)



class APIResponse:
    """Unified API response handler - use this for ALL responses"""
    
    @staticmethod
    def success(data=None, message="Success", status_code=200):
        """Return successful response"""
        return jsonify({
            'success': True,
            'status': 'success',
            'message': message,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }), status_code
    
    @staticmethod
    def created(data, message="Resource created successfully"):
        """Return 201 Created response"""
        return APIResponse.success(data, message, 201)
    
    @staticmethod
    def error(error_code, message, details=None, status_code=400):
        """Return error response with proper HTTP status"""
        return jsonify({
            'success': False,
            'status': 'error',
            'error_code': error_code,
            'message': message,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }), status_code
    
    @staticmethod
    def bad_request(error_code, message, details=None):
        """Return 400 Bad Request"""
        return APIResponse.error(error_code, message, details, 400)
    
    @staticmethod
    def not_found(error_code, message, details=None):
        """Return 404 Not Found"""
        return APIResponse.error(error_code, message, details, 404)
    
    @staticmethod
    def server_error(error_code, message, details=None):
        """Return 500 Internal Server Error"""
        return APIResponse.error(error_code, message, details, 500)

# Fixed Database class with all required methods
# Replace your current Database class (lines 83-206) with this:

class Database:
    """SQL Server database connection and query handler"""
    
    def __init__(self, server, database, username=None, password=None):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.connection_string = self._build_connection_string()
    
    def _build_connection_string(self):
        """Build ODBC connection string"""
        if self.username and self.password:
            # SQL Authentication
            return (f'Driver={{ODBC Driver 17 for SQL Server}};'
                   f'Server={self.server};'
                   f'Database={self.database};'
                   f'UID={self.username};'
                   f'PWD={self.password}')
        else:
            # Windows Authentication
            return (f'Driver={{ODBC Driver 17 for SQL Server}};'
                   f'Server={self.server};'
                   f'Database={self.database};'
                   f'Trusted_Connection=yes;')
    
    def connect(self):
        """Create database connection"""
        try:
            conn = pyodbc.connect(self.connection_string)
            conn.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
            conn.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def execute_query(self, query, params=None, fetch=True, commit=False):
        """Execute query and return results"""
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if fetch:
                results = cursor.fetchall()
                if commit:
                    conn.commit()
                return results
            else:
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def insert_raw_data(self, values):
        """Insert data into RawData table"""
        query = """
        INSERT INTO dbo.RawData (
            source_id, catchment_id, measurement_date, category,
            original_sheet_name, org_id,
            recharge_inches, recharge_converted, average_recharge,
            recharge_stdev, drought_index_recharge, recharge_deviation,
            baseflow_value, average_baseflow, baseflow_stdev,
            standardized_baseflow, baseflow_deviation,
            gw_level, average_gw_level, gw_level_stdev,
            standardized_gw_level, gw_level_deviation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            values.get('source_id'),
            values.get('catchment_id'),
            values.get('measurement_date'),
            values.get('category'),
            values.get('original_sheet_name'),
            values.get('org_id'),
            values.get('recharge_inches'),
            values.get('recharge_converted'),
            values.get('average_recharge'),
            values.get('recharge_stdev'),
            values.get('drought_index_recharge'),
            values.get('recharge_deviation'),
            values.get('baseflow_value'),
            values.get('average_baseflow'),
            values.get('baseflow_stdev'),
            values.get('standardized_baseflow'),
            values.get('baseflow_deviation'),
            values.get('gw_level'),
            values.get('average_gw_level'),
            values.get('gw_level_stdev'),
            values.get('standardized_gw_level'),
            values.get('gw_level_deviation')
        )

        try:
            self.execute_query(query, params, fetch=False)
            logger.debug(f"Inserted raw data record for {values.get('category')}")
        except Exception as e:
            logger.error(f"Error inserting raw data: {e}")
            raise
    
    def get_catchment_id(self, catchment_name):
        """Get catchment ID by name"""
        query = "SELECT catchment_id FROM dbo.Catchments WHERE catchment_name = ?"
        try:
            results = self.execute_query(query, (catchment_name,))
            if results:
                return results[0][0]
            return None
        except Exception as e:
            logger.error(f"Error getting catchment ID: {e}")
            return None
    
    # ADD THESE MISSING METHODS:
    
    def create_data_source(self, file_name, category, subcatchment_name=None,
                           uploaded_by=None, org_id=None):
        """Create data source record"""
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor()

            logger.info(f"Attempting INSERT: file_name={file_name}, category={category}, "
                        f"subcatchment={subcatchment_name}, org_id={org_id}")

            cursor.execute("""
                INSERT INTO dbo.DataSources
                    (file_name, category, subcatchment_name, processing_status, uploaded_by, org_id)
                OUTPUT INSERTED.source_id
                VALUES (?, ?, ?, 'Processing', ?, ?)
            """, (file_name, category, subcatchment_name, uploaded_by, org_id))

            # Fetch the returned source_id
            result = cursor.fetchone()

            logger.info(f"INSERT OUTPUT result: {result}")

            if result and result[0] is not None:
                source_id = int(result[0])
                conn.commit()
                logger.info(f"Successfully created data source: {source_id}")
                return source_id
            else:
                logger.error(f"INSERT did not return a source_id. Result: {result}")
                conn.rollback()
                return None

        except Exception as e:
            logger.error(f"Error creating data source: {e}")
            logger.error(traceback.format_exc())
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()
    
    def update_data_source_status(self, source_id, status, error_message=None, 
                                   records_processed=None, date_range=None):
        """Update data source processing status"""
        if date_range:
            query = """
            UPDATE dbo.DataSources 
            SET processing_status = ?, 
                error_message = ?, 
                records_processed = ?,
                date_range_start = ?,
                date_range_end = ?,
                updated_at = GETDATE()
            WHERE source_id = ?
            """
            params = (status, error_message, records_processed, 
                     date_range[0], date_range[1], source_id)
        else:
            query = """
            UPDATE dbo.DataSources 
            SET processing_status = ?, 
                error_message = ?, 
                records_processed = ?,
                updated_at = GETDATE()
            WHERE source_id = ?
            """
            params = (status, error_message, records_processed, source_id)
        
        try:
            self.execute_query(query, params, fetch=False, commit=True)
            logger.info(f"Updated source {source_id} status to: {status}")
        except Exception as e:
            logger.error(f"Error updating data source status: {e}")
# Initialize database connection (configure these values)
DB_CONFIG = {
    'server': os.getenv('DB_SERVER', 'localhost'),
    'database': os.getenv('DB_NAME', 'GroundwaterAnalysis'),
    'username': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

db = Database(**DB_CONFIG)

import re as _re

def _exec(query, params=None, **kw):
    """
    Thin wrapper around db.execute_query that gracefully handles the case where
    the tenant-isolation migration hasn't been applied yet (org_id / uploaded_by
    columns missing).  Strips those clauses and retries so read routes stay
    functional.  Write routes (INSERT with org_id) must NOT use this helper.
    """
    try:
        return db.execute_query(query, params, **kw)
    except Exception as e:
        err = str(e)
        if '42S22' not in err:
            raise
        missing = err.lower()
        if 'org_id' in missing or 'uploaded_by' in missing:
            q = query
            # Strip WHERE / AND org_id filter (org_id is always the 1st param)
            q = _re.sub(r'WHERE\s+(?:\w+\.)?org_id\s*=\s*\?', 'WHERE 1=1', q, flags=_re.IGNORECASE)
            q = _re.sub(r'AND\s+(?:\w+\.)?org_id\s*=\s*\?',   '',           q, flags=_re.IGNORECASE)
            # Strip LEFT JOIN on dbo.Users via uploaded_by and the username column
            q = _re.sub(r'LEFT\s+JOIN\s+dbo\.Users\s+\w+\s+ON\s+\w+\.uploaded_by\s*=\s*\w+\.\w+', '', q, flags=_re.IGNORECASE)
            q = _re.sub(r',?\s*ISNULL\(\w+\.username\s*,\s*\'system\'\)\s+as\s+uploaded_by_username', '', q, flags=_re.IGNORECASE)
            # Remove the org_id param (always first in params)
            p = list(params)[1:] if params else None
            logger.warning("Tenant migration pending — running without org_id/uploaded_by filter")
            return db.execute_query(q, p if p else None, **kw)
        raise

# ── Auth initialisation ────────────────────────────────────────────────────────
from auth import auth_bp, init_auth, require_auth, _audit as audit_log
init_auth(app, db, limiter)
app.register_blueprint(auth_bp)

# ── System admin blueprint ─────────────────────────────────────────────────────
from admin_bp import admin_bp as _admin_bp, init_admin as _init_admin
_init_admin(db)
app.register_blueprint(_admin_bp)

# ── Serve frontend static files from Flask (same origin as API) ───────────────
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')

@app.route('/')
def root():
    return redirect('/frontend/public/login.html')

@app.route('/frontend/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(_FRONTEND_DIR, filename)

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(_IMAGES_DIR, filename)

# ── CORS + Security headers ────────────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    # Re-enforce CORS on every response (including 4xx/5xx that Flask-CORS may miss)
    origin = request.headers.get('Origin', '')
    if origin in _allowed_origins:
        response.headers['Access-Control-Allow-Origin']      = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods']     = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers']     = (
            'Content-Type, Authorization, X-Refresh-Token'
        )

    response.headers['X-Content-Type-Options']  = 'nosniff'
    response.headers['X-Frame-Options']          = 'SAMEORIGIN'
    response.headers['X-XSS-Protection']         = '1; mode=block'
    response.headers['Referrer-Policy']           = 'strict-origin-when-cross-origin'
    if os.getenv('FLASK_ENV') == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Handle pre-flight OPTIONS requests (needed for cross-origin POST/PUT/DELETE)
@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        origin = request.headers.get('Origin', '')
        if origin in _allowed_origins:
            from flask import make_response as _mr
            resp = _mr('', 204)
            resp.headers['Access-Control-Allow-Origin']      = origin
            resp.headers['Access-Control-Allow-Credentials'] = 'true'
            resp.headers['Access-Control-Allow-Methods']     = 'GET, POST, PUT, DELETE, OPTIONS'
            resp.headers['Access-Control-Allow-Headers']     = (
                'Content-Type, Authorization, X-Refresh-Token'
            )
            resp.headers['Access-Control-Max-Age']           = '600'
            return resp

# ============================================================================
# CUSTOM EXCEPTION CLASS
# ============================================================================

class ValidationError(Exception):
    """Custom exception for validation errors with structured error information"""
    def __init__(self, code, user_message, technical_details=None, guidance=None, found_data=None):
        self.code = code
        self.user_message = user_message
        self.technical_details = technical_details
        self.guidance = guidance or []
        self.found_data = found_data or {}
        super().__init__(self.user_message)

# ============================================================================
# ERROR RESPONSE GENERATOR
# ============================================================================

def parse_date_param(date_str):
    """
    Convert a date string (YYYY-MM-DD from browser input) to a Python date object.
    Passing a date object to pyodbc is safer than a raw string because it bypasses
    SQL Server's session-level DATEFORMAT setting, preventing intermittent parse failures.
    Returns None if the string is empty or invalid.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except ValueError:
        logger.warning(f"Could not parse date parameter: {date_str!r}")
        return None


def get_error_response(error_code, user_message, details=None, guidance=None, found_data=None):
    """Generate standardized error response"""
    return {
        'error': user_message,
        'error_code': error_code,
        'technical_details': details,
        'guidance': guidance or [],
        'found_data': found_data or {},
        'timestamp': datetime.now().isoformat()
    }

# ============================================================================
# FILE VALIDATION FUNCTION
# ============================================================================

def validate_file(file, max_size=100*1024*1024):
    """Validate uploaded file"""
    if not file:
        return False, get_error_response(
            error_code='NO_FILE',
            user_message='No file was selected for upload.',
            guidance=['1. Click on the upload area', '2. Choose an Excel file (.xlsx or .xls)', '3. Try uploading again']
        )
    
    if not file.filename:
        return False, get_error_response(
            error_code='NO_FILENAME',
            user_message='The selected file has no name.',
            guidance=['Select a valid Excel file with a proper filename']
        )
    
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        file_ext = file.filename.split('.')[-1].upper() if '.' in file.filename else 'UNKNOWN'
        return False, get_error_response(
            error_code='INVALID_FILE_TYPE',
            user_message=f'File type "{file_ext}" is not supported.',
            details=f'Expected .xlsx or .xls, got {file.filename}',
            guidance=['✓ Supported formats: .xlsx (Excel 2007+) and .xls (Excel 97-2003)'],
            found_data={'file_name': file.filename, 'file_extension': file_ext}
        )
    
    return True, None

# ============================================================================
# USER INPUT VALIDATION
# ============================================================================

def validate_user_inputs(category, subcatchment):
    """Validate user selections"""
    if not category or category.strip() == '':
        return False, get_error_response(
            error_code='MISSING_CATEGORY',
            user_message='No data category was selected.',
            guidance=['1. Select a data category from the dropdown:',
                     '   • Recharge', '   • Baseflow', '   • GWLevel']
        )
    
    if not subcatchment or subcatchment.strip() == '':
        return False, get_error_response(
            error_code='MISSING_SUBCATCHMENT',
            user_message='No catchment/subcatchment was selected.',
            guidance=['1. Select a catchment from the dropdown']
        )
    
    return True, None

# ============================================================================
# COLUMN MAPPING FOR EACH CATEGORY
# ============================================================================

COLUMN_MAPPING = {
    'recharge': {
        'measurement_date': 'measurement date',
        'recharge_inches': 'recharge (inches)',
        'recharge_converted': 'recharge',
        'average_recharge': 'average recharge',
        'recharge_stdev': 'stdev',
        'drought_index_recharge': 'drought index - recharge',
        'recharge_deviation': 'recharge deviation'
    },
    'baseflow': {
        'measurement_date': 'measurement date',
        'baseflow_value': 'baseflow value',
        'average_baseflow': 'average baseflow',
        'baseflow_stdev': 'stdev',
        'standardized_baseflow': 'standardized baseflow',
        'baseflow_deviation': 'baseflow deviation'
    },
    'gwlevel': {
        'measurement_date': 'measurement date',
        'gw_level': 'gw level',
        'average_gw_level': 'average gw level',
        'gw_level_stdev': 'stdev',
        'standardized_gw_level': 'standardized gw level',
        'gw_level_deviation': 'gw level deviation'
    }
}

# ============================================================================
# TENANT ISOLATION HELPERS
# ============================================================================

def _get_source_access(source_id):
    """Return (org_id, uploaded_by) for a source, or None if not found."""
    try:
        rows = db.execute_query(
            "SELECT org_id, uploaded_by FROM dbo.DataSources WHERE source_id = ?",
            (source_id,)
        )
        if not rows:
            return None
        return rows[0][0], rows[0][1]
    except Exception as e:
        if '42S22' in str(e) and 'org_id' in str(e).lower():
            rows = db.execute_query(
                "SELECT 1 FROM dbo.DataSources WHERE source_id = ?", (source_id,)
            )
            return (1, None) if rows else None
        raise


def _check_source_access(source_id, require_uploader=False):
    """
    Verify the current user may access a source.
    Returns a Flask error response tuple, or None if access is permitted.
    - Always 404 when the source belongs to a different org (no info leak).
    - When require_uploader=True, analysts may only act on their own uploads.
    """
    from flask import g as _g
    access = _get_source_access(source_id)
    if not access:
        return jsonify({'success': False, 'error': 'Source not found'}), 404
    source_org_id, uploaded_by = access
    if source_org_id != _g.current_user_org_id:
        return jsonify({'success': False, 'error': 'Source not found'}), 404
    if require_uploader and _g.current_user_role == 'analyst':
        if uploaded_by != _g.current_user_id:
            return jsonify({
                'success': False,
                'error': 'Analysts may only modify their own uploads.'
            }), 403
    return None


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.execute_query("SELECT 1")
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503
    

@app.route('/api/upload', methods=['POST'])
@require_auth(roles=['admin', 'analyst'])
def upload_file():
    """File upload endpoint with full processing"""
    from flask import g as _g
    if getattr(_g, 'current_user_plan', 'basic') == 'basic':
        return jsonify({
            'success': False,
            'error': 'Excel upload requires a Pro plan. Upgrade your plan to access this feature.',
            'error_code': 'PLAN_RESTRICTED',
        }), 403

    logger.info("Upload request received")
    
    try:
        if 'file' not in request.files:
            return jsonify(get_error_response(
                'NO_FILE', 'No file part in request'
            )), 400
        
        file = request.files['file']
        is_valid, error_resp = validate_file(file)
        if not is_valid:
            return jsonify(error_resp), 400
        
        category = request.form.get('category', '').strip().lower()
        subcatchment = request.form.get('subcatchment', '').strip()
        
        is_valid, error_resp = validate_user_inputs(category, subcatchment)
        if not is_valid:
            return jsonify(error_resp), 400
        
        # Validate category value
        if category not in ['recharge', 'baseflow', 'gwlevel']:
            return jsonify(get_error_response(
                'INVALID_CATEGORY',
                'Invalid category selected',
                found_data={'provided': category, 'valid': ['recharge', 'baseflow', 'gwlevel']}
            )), 400
        
        # ========== STEP 3: Save file temporarily ==========
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            filepath = tmp.name
            file.save(filepath)
            logger.info(f"File saved: {filepath}")
        
        # ========== STEP 4: Create data source record WITH SUBCATCHMENT ==========
        safe_name = secure_filename(file.filename) or 'upload.xlsx'
        try:
            source_id = db.create_data_source(
                safe_name, category, subcatchment,
                uploaded_by=g.current_user_id,
                org_id=g.current_user_org_id,
            )
            if not source_id:
                logger.error("create_data_source returned None")
                return jsonify(get_error_response(
                    'DATABASE_ERROR', 'Failed to create data source'
                )), 500

            logger.info(f"Created data source: {source_id}")
        except Exception as ds_error:
            logger.error(f"Exception in create_data_source: {ds_error}")
            logger.error(traceback.format_exc())
            return jsonify(get_error_response(
                'DATABASE_ERROR', f'Failed to create data source: {str(ds_error)}'
            )), 500
        
        # ========== STEP 5: Get catchment ID ==========
        catchment_id = db.get_catchment_id(subcatchment)
        if not catchment_id:
            db.update_data_source_status(source_id, 'Failed', 
                                        f'Catchment not found: {subcatchment}')
            return jsonify(get_error_response(
                'CATCHMENT_NOT_FOUND',
                f'Catchment "{subcatchment}" not found in database'
            )), 400
        
        logger.info(f"Using catchment: {catchment_id}")
        
        # ========== STEP 6: Read and process Excel ==========
        try:
            df = pd.read_excel(filepath, sheet_name=0)
            logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
        except Exception as e:
            logger.error(f"Excel read error: {e}")
            db.update_data_source_status(source_id, 'Failed', f'Excel read error: {e}')
            return jsonify(get_error_response(
                'EXCEL_READ_ERROR', 'Failed to read Excel file'
            )), 400
        
        # ========== STEP 7: Process rows ==========
        total_inserted = 0
        errors = []
        warnings = []
        date_range_start = None
        date_range_end = None
        
        for idx, row in df.iterrows():
            try:
                # Parse date
                raw_date = row.get('measurement date')
                if pd.isna(raw_date) or raw_date == '':
                    warnings.append({'row': idx + 2, 'issue': 'Missing date'})
                    continue
                
                try:
                    if isinstance(raw_date, str):
                        parsed_date = pd.to_datetime(raw_date)
                    else:
                        parsed_date = pd.to_datetime(raw_date)
                except:
                    warnings.append({'row': idx + 2, 'issue': f'Invalid date format: {raw_date}'})
                    continue
                
                if not parsed_date:
                    continue
                
                # Track date range
                date_str = parsed_date.strftime('%Y-%m-%d')
                if not date_range_start or date_str < date_range_start:
                    date_range_start = date_str
                if not date_range_end or date_str > date_range_end:
                    date_range_end = date_str
                
                # Safe float conversion
                def safe_float(value):
                    if pd.isna(value) or value == '' or value is None:
                        return None
                    try:
                        if isinstance(value, str):
                            value = value.strip()
                            if value == '' or value.lower() in ['nan', 'null', 'none', '#n/a', 'n/a']:
                                return None
                        return float(value)
                    except (ValueError, TypeError):
                        return None
                
                values = {
                    'source_id': source_id,
                    'catchment_id': catchment_id,
                    'measurement_date': parsed_date,
                    'category': category.lower(),
                    'original_sheet_name': subcatchment,
                    'org_id': g.current_user_org_id,
                }
                
                # ===== CATEGORY-SPECIFIC DATA EXTRACTION =====
                
                if category.lower() == 'baseflow':
                    baseflow_val = safe_float(row.get('baseflow value'))
                    
                    if baseflow_val is None:
                        logger.debug(f"Row {idx}: Missing baseflow value, skipping")
                        continue
                    
                    values.update({
                        'baseflow_value': baseflow_val,
                        'average_baseflow': safe_float(row.get('average baseflow')),
                        'baseflow_stdev': safe_float(row.get('stdev')),
                        'standardized_baseflow': safe_float(row.get('standardized baseflow')),
                        'baseflow_deviation': safe_float(row.get('baseflow deviation')),
                        # Set other category values to None
                        'recharge_inches': None,
                        'recharge_converted': None,
                        'average_recharge': None,
                        'recharge_stdev': None,
                        'drought_index_recharge': None,
                        'recharge_deviation': None,
                        'gw_level': None,
                        'average_gw_level': None,
                        'gw_level_stdev': None,
                        'standardized_gw_level': None,
                        'gw_level_deviation': None
                    })
                
                elif category.lower() == 'gwlevel':
                    gw_level = safe_float(row.get('gw level'))
                    
                    if gw_level is None:
                        logger.debug(f"Row {idx}: Missing GW level value, skipping")
                        continue
                    
                    values.update({
                        'gw_level': gw_level,
                        'average_gw_level': safe_float(row.get('average gw level')),
                        'gw_level_stdev': safe_float(row.get('stdev')),
                        'standardized_gw_level': safe_float(row.get('standardized gw level')),
                        'gw_level_deviation': safe_float(row.get('gw level deviation')),
                        # Set other category values to None
                        'recharge_inches': None,
                        'recharge_converted': None,
                        'average_recharge': None,
                        'recharge_stdev': None,
                        'drought_index_recharge': None,
                        'recharge_deviation': None,
                        'baseflow_value': None,
                        'average_baseflow': None,
                        'baseflow_stdev': None,
                        'standardized_baseflow': None,
                        'baseflow_deviation': None
                    })
                
                elif category.lower() == 'recharge':
                    recharge_inches = safe_float(row.get('recharge (inches)'))
                    
                    if recharge_inches is None:
                        logger.debug(f"Row {idx}: Missing recharge inches value, skipping")
                        continue
                    
                    values.update({
                        'recharge_inches': recharge_inches,
                        'recharge_converted': safe_float(row.get('recharge')),
                        'average_recharge': safe_float(row.get('average recharge')),
                        'recharge_stdev': safe_float(row.get('stdev')),
                        'drought_index_recharge': safe_float(row.get('drought index - recharge')),
                        'recharge_deviation': safe_float(row.get('recharge deviation')),
                        # Set other category values to None
                        'baseflow_value': None,
                        'average_baseflow': None,
                        'baseflow_stdev': None,
                        'standardized_baseflow': None,
                        'baseflow_deviation': None,
                        'gw_level': None,
                        'average_gw_level': None,
                        'gw_level_stdev': None,
                        'standardized_gw_level': None,
                        'gw_level_deviation': None
                    })
                
                # Insert record
                try:
                    db.insert_raw_data(values)
                    total_inserted += 1
                    
                    if total_inserted % 50 == 0:
                        logger.info(f"Inserted {total_inserted} records...")
                
                except Exception as insert_error:
                    error_msg = f"Row {idx + 2}: Insert failed - {str(insert_error)}"
                    logger.error(error_msg)
                    errors.append({'row': idx + 2, 'error': str(insert_error)})
                    continue
            
            except Exception as row_error:
                error_msg = f"Row {idx + 2}: Processing error - {str(row_error)}"
                logger.error(error_msg)
                errors.append({'row': idx + 2, 'error': str(row_error)})
                continue
        
        # ========== STEP 8: Finalize ==========
        if total_inserted == 0:
            error_msg = f"No records processed from {len(df)} rows"
            db.update_data_source_status(source_id, 'Failed', error_msg)
            return jsonify(get_error_response(
                'NO_RECORDS_PROCESSED',
                'No records could be processed from the file.',
                details=error_msg
            )), 400
        
        # Update status
        status = 'Completed with Errors' if errors else 'Completed'
        error_summary = f"Processed {total_inserted} records with {len(errors)} errors." if errors else None
        
        db.update_data_source_status(
            source_id, status, error_summary,
            total_inserted, (date_range_start, date_range_end)
        )
        
        # Clean up
        try:
            os.remove(filepath)
            logger.info(f"Cleaned up: {filepath}")
        except Exception as e:
            logger.warning(f"Could not delete file: {e}")
        
        # Execute post-processing
        try:
            db.execute_query("EXEC sp_ProcessRawData ?", (source_id,), fetch=False)
            logger.info(f"Stored procedure executed for source {source_id}")
        except Exception as proc_error:
            logger.warning(f"Stored procedure error: {proc_error}")
        
        return jsonify({
            'success': True,
            'message': f'{category} data uploaded successfully.',
            'processed_records': total_inserted,
            'errors': len(errors),
            'warnings': len(warnings),
            'error_details': errors if errors else None,
            'warning_details': warnings[:10] if warnings else None,
            'date_range': f"{date_range_start} to {date_range_end}",
            'source_id': source_id,
            'category': category,
            'subcatchment': subcatchment,
            'status': status
        }), 200
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        logger.error(traceback.format_exc())
        return jsonify(get_error_response(
            'UNEXPECTED_ERROR',
            'An unexpected error occurred during upload.',
            details=str(e)
        )), 500

@app.route('/api/filter-options', methods=['GET'])
@require_auth()
def get_filter_options():
    """Get available catchments and parameters with actual data"""
    try:
        # Get catchments that have data for this org
        catchment_query = """
        SELECT DISTINCT c.catchment_id, c.catchment_name
        FROM dbo.Catchments c
        INNER JOIN dbo.ProcessedData pd ON c.catchment_id = pd.catchment_id
        WHERE pd.org_id = ?
        ORDER BY c.catchment_name
        """
        catchment_results = _exec(catchment_query, (g.current_user_org_id,))

        catchments = []
        for row in catchment_results:
            catchments.append(row[1])

        # Get parameters that have data for this org
        param_query = """
        SELECT DISTINCT LOWER(parameter_type) as parameter
        FROM dbo.ProcessedData
        WHERE org_id = ?
        ORDER BY parameter
        """
        param_results = _exec(param_query, (g.current_user_org_id,))
        parameters = [row[0] for row in param_results] if param_results else []
        
        return jsonify({
            'success': True,
            'catchments': catchments if catchments else [],
            'parameters': parameters if parameters else ['recharge', 'baseflow', 'gwlevel'],
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Filter options error: {e}")
        return jsonify({
            'success': False,
            'catchments': [],
            'parameters': ['recharge', 'baseflow', 'gwlevel'],
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 200  # Return 200 with empty data rather than 500




@app.route('/api/detailed-records', methods=['GET'])
@require_auth()
def get_detailed_records():
    """Get detailed data records for reports page - NEW ENDPOINT"""
    try:
        catchment = request.args.get('catchment')
        parameter = request.args.get('parameter')
        start_date = parse_date_param(request.args.get('start_date'))
        end_date = parse_date_param(request.args.get('end_date'))
        limit = request.args.get('limit', 10000, type=int)

        # Build the query
        query = """
        SELECT
            pd.processed_id,
            pd.measurement_date,
            c.catchment_name as sub_catchment,
            pd.parameter_type as parameter,
            pd.original_value,
            pd.standardized_value as z_score,
            pd.classification,
            CASE WHEN pd.is_failure = 1 THEN 'Failure' ELSE 'Normal' END as status,
            pd.severity_level,
            pd.drought_index,
            pd.std_deviation
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE pd.org_id = ?
        """
        params = [g.current_user_org_id]

        if catchment:
            query += " AND c.catchment_name = ?"
            params.append(catchment)

        if parameter:
            query += " AND LOWER(pd.parameter_type) = ?"
            params.append(parameter.lower())

        if start_date:
            query += " AND CAST(pd.measurement_date AS DATE) >= ?"
            params.append(start_date)

        if end_date:
            query += " AND CAST(pd.measurement_date AS DATE) <= ?"
            params.append(end_date)

        query += " ORDER BY pd.measurement_date DESC"

        results = _exec(query, params if params else None)

        # Format results
        records = []
        for row in results[:limit]:
            records.append({
                'date': row[1].strftime('%Y-%m-%d') if row[1] else None,
                'sub_catchment': row[2],
                'parameter': row[3],
                'original_value': float(row[4]) if row[4] else 0,
                'z_score': float(row[5]) if row[5] else 0,
                'classification': row[6],
                'status': row[7],
                'severity': row[8],
                'drought_index': float(row[9]) if row[9] else 0,
                'std_deviation': float(row[10]) if row[10] else 0
            })
        
        return jsonify({
            'success': True,
            'records': records,
            'total': len(records),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Detailed records error: {e}")
        return jsonify({
            'success': False,
            'records': [],
            'total': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 200

@app.route('/api/data', methods=['GET'])
@require_auth()
def get_data():
    """Get processed data with optional filters - FRONTEND COMPATIBLE"""
    try:
        # Get query parameters
        catchment = request.args.get('catchment')  
        parameter = request.args.get('parameter')  
        parameter_type = request.args.get('parameter_type') 
        start_date = parse_date_param(request.args.get('start_date'))
        end_date = parse_date_param(request.args.get('end_date'))
        limit = request.args.get('limit', 10000, type=int)

        # Use whichever parameter name was provided
        if not parameter and parameter_type:
            parameter = parameter_type
        
        query = """
        SELECT
            pd.processed_id,
            pd.measurement_date,
            c.catchment_name,
            pd.parameter_type,
            pd.original_value,
            pd.standardized_value,
            pd.std_deviation,
            pd.classification,
            pd.is_failure,
            pd.severity_level,
            pd.drought_index,
            pd.created_at
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE pd.org_id = ?
        """
        params = [g.current_user_org_id]

        logger.info(f"[DATA] Filters: catchment={catchment}, parameter={parameter}, start={start_date}, end={end_date}")

        if catchment:
            query += " AND c.catchment_name = ?"
            params.append(catchment)
            logger.info(f"[DATA] Added catchment filter: {catchment}")

        if parameter:
            query += " AND LOWER(pd.parameter_type) = ?"
            params.append(parameter.lower())
            logger.info(f"[DATA] Added parameter filter: {parameter}")

        if start_date:
            query += " AND CAST(pd.measurement_date AS DATE) >= ?"
            params.append(start_date)
            logger.info(f"[DATA] Added start_date filter: {start_date}")

        if end_date:
            query += " AND CAST(pd.measurement_date AS DATE) <= ?"
            params.append(end_date)
            logger.info(f"[DATA] Added end_date filter: {end_date}")

        query += " ORDER BY pd.measurement_date DESC"
        
        logger.info(f"[DATA] Full query: {query}")
        
        # Execute query
        results = _exec(query, params if params else None)

        logger.info(f"[DATA] Query returned {len(results) if results else 0} rows")
        
        # Format results - MATCH FRONTEND EXPECTATIONS
        data = []
        if results:
            for row in results[:limit]:
                data.append({
                    'processed_id': row[0],
                    'measurement_date': row[1].strftime('%Y-%m-%d') if row[1] else None,
                    'catchment_name': row[2],
                    'parameter_type': row[3],
                    'original_value': float(row[4]) if row[4] else 0,
                    'standardized_value': float(row[5]) if row[5] else 0,  # ← FIXED: was 'zscore'
                    'std_deviation': float(row[6]) if row[6] else 0,
                    'classification': row[7],
                    'is_failure': int(row[8]) if row[8] else 0,
                    'severity_level': row[9],
                    'drought_index': float(row[10]) if row[10] else 0,
                    'created_at': row[11].isoformat() if row[11] else None
                })
        
        logger.info(f"[DATA] Formatted {len(data)} records for response")
        
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Data retrieval error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'data': [],
            'count': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/export', methods=['GET'])
@require_auth()
def export_data():
    """Export data to CSV"""
    try:
        # Get query parameters
        catchment_id = request.args.get('catchment_id')
        parameter_type = request.args.get('parameter_type')
        format_type = request.args.get('format', 'csv')
        
        # Build query — always scope to caller's org
        query = "SELECT * FROM dbo.ProcessedData WHERE org_id = ?"
        params = [g.current_user_org_id]

        if catchment_id:
            query += " AND catchment_id = ?"
            params.append(catchment_id)

        if parameter_type:
            query += " AND LOWER(parameter_type) = ?"
            params.append(parameter_type.lower())

        query += " ORDER BY measurement_date DESC"

        results = _exec(query, params)

        if not results:
            return jsonify({'error': 'No data to export'}), 404
        
        # Create DataFrame
        df = pd.DataFrame([tuple(row) for row in results])
        
        # Export based on format
        if format_type == 'csv':
            output = StringIO()
            df.to_csv(output, index=False)
            output.seek(0)
            return send_file(
                BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'groundwater_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
        else:
            output = BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'groundwater_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify(get_error_response(
            'EXPORT_ERROR', 'Failed to export data'
        )), 500
    

@app.route('/api/catchments', methods=['GET'])
@require_auth()
def get_catchments():
    """Get all available catchments with record counts from ProcessedData"""
    try:
        query = """
        SELECT
            c.catchment_id,
            c.catchment_name,
            COUNT(DISTINCT pd.processed_id) as total_records
        FROM dbo.Catchments c
        INNER JOIN dbo.ProcessedData pd ON c.catchment_id = pd.catchment_id
        WHERE pd.org_id = ?
        GROUP BY c.catchment_id, c.catchment_name
        ORDER BY c.catchment_name
        """

        results = _exec(query, (g.current_user_org_id,))

        catchments = []
        if results:
            for row in results:
                catchments.append({
                    'catchment_id': row[0],
                    'catchment_name': row[1],
                    'total_records': row[2] or 0
                })
        
        return jsonify({
            'success': True,
            'catchments': catchments,
            'count': len(catchments),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting catchments: {e}")
        return jsonify({
            'success': False,
            'catchments': [],
            'count': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500
    

@app.route('/api/summary', methods=['GET'])
@require_auth()
def get_summary():
    """Get dashboard summary statistics - NEW ENDPOINT"""
    try:
        # Total records for this org
        total_query = "SELECT COUNT(*) FROM dbo.ProcessedData WHERE org_id = ?"
        total_result = _exec(total_query, (g.current_user_org_id,))
        total_records = total_result[0][0] if total_result else 0

        # Failure stats for this org
        failure_query = """
        SELECT
            SUM(CASE WHEN is_failure = 1 THEN 1 ELSE 0 END),
            COUNT(DISTINCT catchment_id),
            AVG(CAST(severity_level AS FLOAT))
        FROM dbo.ProcessedData
        WHERE org_id = ?
        """
        failure_result = _exec(failure_query, (g.current_user_org_id,))
        
        failures = 0
        catchments = 0
        avg_severity = 0
        if failure_result:
            failures = failure_result[0][0] or 0
            catchments = failure_result[0][1] or 0
            avg_severity = float(failure_result[0][2]) if failure_result[0][2] else 0
        
        failure_rate = (failures / total_records * 100) if total_records > 0 else 0
        
        return jsonify({
            'success': True,
            'summary': {
                'total_records': total_records,
                'total_failures': failures,
                'failure_rate': failure_rate,
                'active_catchments': catchments,
                'avg_severity': avg_severity
            },
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Summary error: {e}")
        return jsonify({
            'success': False,
            'summary': {
                'total_records': 0,
                'total_failures': 0,
                'failure_rate': 0,
                'active_catchments': 0,
                'avg_severity': 0
            },
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 200


@app.route('/api/sources', methods=['GET'])
@require_auth()
def get_sources():
    """Get list of all data sources"""
    try:
        query = """
        SELECT
            ds.source_id,
            ds.file_name,
            ds.category,
            ds.processing_status,
            ds.upload_date,
            ds.records_processed,
            ds.date_range_start,
            ds.date_range_end,
            ds.subcatchment_name,
            ds.error_message,
            ISNULL(u.username, 'system') as uploaded_by_username
        FROM dbo.DataSources ds
        LEFT JOIN dbo.Users u ON ds.uploaded_by = u.user_id
        WHERE ds.org_id = ?
        ORDER BY ds.upload_date DESC
        """

        results = _exec(query, (g.current_user_org_id,))

        sources = []
        if results:
            for row in results:
                sources.append({
                    'source_id': row[0],
                    'filename': row[1],
                    'category': row[2],
                    'processing_status': row[3],
                    'upload_date': str(row[4]) if row[4] else None,
                    'total_records': row[5] if row[5] else 0,
                    'date_start': str(row[6]) if row[6] else None,
                    'date_end': str(row[7]) if row[7] else None,
                    'subcatchment_name': row[8],
                    'error_message': row[9],
                    'uploaded_by': row[10] if len(row) > 10 else 'system',
                })
        
        return jsonify({
            'success': True,
            'sources': sources,
            'count': len(sources),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Sources error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'sources': [],
            'count': 0,
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/sources/<int:source_id>/records', methods=['GET'])
@require_auth()
def get_source_records(source_id):
    """Return every ProcessedData row that belongs to a given source."""
    err = _check_source_access(source_id)
    if err:
        return err
    try:
        query = """
        SELECT
            pd.processed_id,
            pd.measurement_date,
            pd.parameter_type,
            pd.original_value,
            pd.mean_value,
            pd.std_deviation,
            pd.standardized_value,
            pd.parameter_deviation,
            pd.drought_index,
            pd.classification,
            pd.is_failure,
            pd.severity_level,
            c.catchment_name,
            ds.file_name,
            ds.category
        FROM dbo.ProcessedData pd
        JOIN dbo.Catchments c  ON pd.catchment_id = c.catchment_id
        JOIN dbo.DataSources ds ON pd.source_id   = ds.source_id
        WHERE pd.source_id = ?
        ORDER BY pd.measurement_date ASC
        """
        rows = db.execute_query(query, (source_id,))
        records = []
        for r in rows:
            records.append({
                'processed_id':      r[0],
                'measurement_date':  r[1].strftime('%Y-%m-%d') if r[1] else None,
                'parameter_type':    r[2],
                'original_value':    float(r[3])  if r[3]  is not None else None,
                'mean_value':        float(r[4])  if r[4]  is not None else None,
                'std_deviation':     float(r[5])  if r[5]  is not None else None,
                'standardized_value':float(r[6])  if r[6]  is not None else None,
                'parameter_deviation':float(r[7]) if r[7]  is not None else None,
                'drought_index':     float(r[8])  if r[8]  is not None else None,
                'classification':    r[9],
                'is_failure':        int(r[10])   if r[10] is not None else 0,
                'severity_level':    int(r[11])   if r[11] is not None else 0,
                'catchment_name':    r[12],
                'file_name':         r[13],
                'category':          r[14],
            })
        return jsonify({'success': True, 'records': records, 'count': len(records)}), 200
    except Exception as e:
        logger.error(f"get_source_records error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sources/<int:source_id>/records', methods=['PUT'])
@require_auth(roles=['admin', 'analyst'])
def update_source_records(source_id):
    """Edit records — admin can edit any org source, analyst only their own uploads."""
    err = _check_source_access(source_id, require_uploader=True)
    if err:
        return err
    try:
        body = request.get_json(force=True)
        if not body or not isinstance(body.get('records'), list):
            return jsonify({'success': False, 'error': 'Expected {"records": [...]}'}), 400

        edits = body['records']
        updated = 0

        for rec in edits:
            pid        = rec.get('processed_id')
            new_date   = rec.get('measurement_date')
            new_value  = rec.get('original_value')

            if pid is None:
                continue

            # Fetch the stored mean + stdev so we can recompute the z-score
            existing = db.execute_query(
                "SELECT mean_value, std_deviation FROM dbo.ProcessedData "
                "WHERE processed_id = ? AND source_id = ?",
                (pid, source_id)
            )
            if not existing:
                logger.warning(f"update_source_records: processed_id {pid} not in source {source_id}")
                continue

            mean_val = float(existing[0][0]) if existing[0][0] is not None else 0.0
            std_val  = float(existing[0][1]) if existing[0][1] is not None else 1.0
            if std_val == 0:
                std_val = 1.0   # guard against division by zero

            set_clauses  = []
            update_params = []

            if new_value is not None:
                val = float(new_value)
                z   = (val - mean_val) / std_val

                # Classification thresholds (must match sp_ProcessRawData)
                if z >= 0.5:
                    cls = 'Surplus'
                elif z >= -0.5:
                    cls = 'Normal'
                elif z >= -1.0:
                    cls = 'Moderate_Deficit'
                elif z >= -1.5:
                    cls = 'Severe_Deficit'
                else:
                    cls = 'Extreme_Deficit'

                is_fail  = 1 if z < -0.5 else 0
                severity = 0 if z >= -0.5 else (1 if z >= -1.0 else (2 if z >= -1.5 else 3))

                set_clauses  += ['original_value=?','standardized_value=?','drought_index=?',
                                  'parameter_deviation=?','classification=?',
                                  'is_failure=?','severity_level=?']
                update_params += [val, z, z, val - mean_val, cls, is_fail, severity]

            if new_date:
                parsed = parse_date_param(new_date)
                if parsed:
                    set_clauses.append('measurement_date=?')
                    update_params.append(parsed)

            if not set_clauses:
                continue

            update_params += [pid, source_id]
            db.execute_query(
                f"UPDATE dbo.ProcessedData SET {', '.join(set_clauses)} "
                f"WHERE processed_id = ? AND source_id = ?",
                update_params, fetch=False
            )
            updated += 1

        logger.info(f"update_source_records: {updated} rows updated for source {source_id}")
        return jsonify({'success': True, 'updated': updated,
                        'message': f'{updated} record(s) updated successfully'}), 200

    except Exception as e:
        logger.error(f"update_source_records error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sources/<int:source_id>/records', methods=['DELETE'])
@require_auth(roles=['admin', 'analyst'])
def delete_source_records(source_id):
    """Delete records — admin can delete any org source, analyst only their own uploads."""
    err = _check_source_access(source_id, require_uploader=True)
    if err:
        return err
    try:
        body = request.get_json(force=True, silent=True) or {}
        processed_ids = body.get('processed_ids', [])

        if not processed_ids or not isinstance(processed_ids, list):
            return jsonify({'success': False, 'error': 'processed_ids must be a non-empty list'}), 400

        # Validate all IDs are integers
        try:
            processed_ids = [int(pid) for pid in processed_ids]
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'All processed_ids must be integers'}), 400

        placeholders = ','.join(['?'] * len(processed_ids))
        params = processed_ids + [source_id]
        db.execute_query(
            f"DELETE FROM dbo.ProcessedData WHERE processed_id IN ({placeholders}) AND source_id = ?",
            params, fetch=False
        )

        logger.info(f"delete_source_records: {len(processed_ids)} rows deleted for source {source_id}")
        return jsonify({'success': True, 'deleted': len(processed_ids),
                        'message': f'{len(processed_ids)} record(s) deleted'}), 200

    except Exception as e:
        logger.error(f"delete_source_records error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sources/<int:source_id>', methods=['GET', 'DELETE'])
@require_auth(roles=['admin', 'analyst'])
def handle_source(source_id):
    """Get source details or delete source."""
    # GET: any org member may view; DELETE: admin or the uploader
    require_uploader = (request.method == 'DELETE')
    err = _check_source_access(source_id, require_uploader=require_uploader)
    if err:
        return err
    try:
        if request.method == 'GET':
            query = """
            SELECT 
                ds.source_id,
                ds.file_name,
                ds.category,
                ds.processing_status,
                ds.upload_date,
                ds.records_processed,
                ds.error_message,
                ds.subcatchment_name
            FROM dbo.DataSources ds
            WHERE ds.source_id = ?
            """
            results = db.execute_query(query, (source_id,))
            
            if results:
                row = results[0]
                return jsonify({
                    'success': True,
                    'source': {
                        'source_id': row[0],
                        'filename': row[1],
                        'category': row[2],
                        'processing_status': row[3],
                        'upload_date': str(row[4]) if row[4] else None,
                        'total_records': row[5] if row[5] else 0,
                        'error_message': row[6],
                        'subcatchment_name': row[7]
                    }
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Source not found'
                }), 404
        
        elif request.method == 'DELETE':
            # Delete in correct order due to foreign key constraints
            # 1. Delete ProcessedData
            delete_query = """
            DELETE FROM dbo.ProcessedData 
            WHERE raw_id IN (SELECT raw_id FROM dbo.RawData WHERE source_id = ?)
            """
            db.execute_query(delete_query, (source_id,), fetch=False)
            
            # 2. Delete RawData
            delete_query = "DELETE FROM dbo.RawData WHERE source_id = ?"
            db.execute_query(delete_query, (source_id,), fetch=False)
            
            # 3. Delete DataSource
            delete_query = "DELETE FROM dbo.DataSources WHERE source_id = ?"
            db.execute_query(delete_query, (source_id,), fetch=False)
            
            logger.info(f"Successfully deleted source {source_id}")
            return jsonify({
                'success': True,
                'message': f'Source {source_id} deleted successfully'
            }), 200
    
    except Exception as e:
        logger.error(f"Source error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to process source: {str(e)}'
        }), 500

@app.route('/api/failure-analysis', methods=['GET'])
@require_auth()
def get_failure_analysis():
    """Get failure analysis with proper filtering - FIXED with DATE support"""
    try:
        # Accept both 'category' and 'parameter' (frontend sends 'category')
        catchment = request.args.get('catchment')
        category = request.args.get('category')  # What frontend sends
        parameter = request.args.get('parameter')  # Alternative name
        start_date = parse_date_param(request.args.get('start_date'))
        end_date = parse_date_param(request.args.get('end_date'))

        # Use whichever one was provided
        param_filter = category or parameter
        
        # Query to get failure analysis data
        query = """
        SELECT
            c.catchment_name,
            pd.parameter_type,
            COUNT(*) as total_records,
            SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) as failure_count,
            CAST(SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) AS FLOAT) /
                NULLIF(COUNT(*), 0) * 100 as failure_rate,
            AVG(CAST(pd.severity_level AS FLOAT)) as avg_severity,
            MAX(pd.severity_level) as max_severity,
            MIN(pd.severity_level) as min_severity
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE pd.org_id = ?
        """
        params = [g.current_user_org_id]

        if catchment:
            query += " AND c.catchment_name = ?"
            params.append(catchment)

        if param_filter:
            query += " AND LOWER(pd.parameter_type) = ?"
            params.append(param_filter.lower())

        # ✅ NEW: Add date range filters
        if start_date:
            query += " AND CAST(pd.measurement_date AS DATE) >= ?"
            params.append(start_date)
            logger.info(f"[FILTER] Adding start_date filter: {start_date}")

        if end_date:
            query += " AND CAST(pd.measurement_date AS DATE) <= ?"
            params.append(end_date)
            logger.info(f"[FILTER] Adding end_date filter: {end_date}")

        query += " GROUP BY c.catchment_name, pd.parameter_type ORDER BY failure_rate DESC"
        
        print(f"[DEBUG] Query: {query}")
        print(f"[DEBUG] Params: {params}")
        
        results = _exec(query, params if params else None)

        print(f"[DEBUG] Results count: {len(results) if results else 0}")
        
        analysis = []
        if results:
            for row in results:
                analysis.append({
                    'catchment': row[0],
                    'parameter': row[1],
                    'total': row[2],
                    'failures': row[3],
                    'failure_rate': float(row[4]) if row[4] else 0,
                    'avg_severity': float(row[5]) if row[5] else 0,
                    'max_severity': row[6],
                    'min_severity': row[7]
                })
        
        # FIXED: Also apply filters to overall stats
        overall_query = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_failure = 1 THEN 1 ELSE 0 END) as failures,
            COUNT(DISTINCT catchment_id) as catchments
        FROM dbo.ProcessedData
        WHERE org_id = ?
        """
        overall_params = [g.current_user_org_id]

        if catchment:
            overall_query += " AND catchment_id = (SELECT catchment_id FROM dbo.Catchments WHERE catchment_name = ?)"
            overall_params.append(catchment)

        if param_filter:
            overall_query += " AND LOWER(parameter_type) = ?"
            overall_params.append(param_filter.lower())

        # ✅ NEW: Add date range filters to overall stats too
        if start_date:
            overall_query += " AND CAST(measurement_date AS DATE) >= ?"
            overall_params.append(start_date)

        if end_date:
            overall_query += " AND CAST(measurement_date AS DATE) <= ?"
            overall_params.append(end_date)

        overall_results = _exec(overall_query, overall_params if overall_params else None)
        
        overall_stats = {}
        if overall_results:
            row = overall_results[0]
            overall_stats = {
                'total_records': row[0],
                'total_failures': row[1],
                'failure_rate': (float(row[1]) / row[0] * 100) if row[0] > 0 else 0,
                'active_catchments': row[2]
            }
        
        return jsonify({
            'success': True,
            'failure_analysis': analysis,  # Keep this field name
            'analysis': analysis,           # Also return as 'analysis' for compatibility
            'overall_stats': overall_stats,
            'count': len(analysis),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Failure analysis error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'failure_analysis': [],
            'analysis': [],
            'overall_stats': {},
            'count': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 200


@app.route('/api/metrics', methods=['GET'])
@require_auth()
def get_metrics():
    """
    Get water system performance metrics.
    
    Query Parameters:
    - catchment: Filter by catchment name (optional)
    - parameter/parameter_type: Filter by parameter (optional)
    - aggregate: If 'true', return single aggregated metric (optional)
    
    Returns:
    {
        "success": true,
        "metrics": [
            {
                "catchment": "Crocodile" or "OVERALL" if aggregated,
                "parameter": "recharge" or "ALL" if aggregated,
                "reliability": 0.75,
                "resilience": 0.65,
                "vulnerability": 0.33,
                "sustainability": 0.42
            }
        ]
    }
    """
    try:
        catchment = request.args.get('catchment')
        parameter = request.args.get('parameter')
        parameter_type = request.args.get('parameter_type')
        start_date = parse_date_param(request.args.get('start_date'))
        end_date = parse_date_param(request.args.get('end_date'))

        # ✅ NEW: Handle aggregation flag
        aggregate = request.args.get('aggregate', 'false').lower() == 'true'

        # Use whichever parameter name was provided
        if not parameter and parameter_type:
            parameter = parameter_type

        logger.info(f"[METRICS] Request - catchment={catchment}, parameter={parameter}, aggregate={aggregate}, dates={start_date} to {end_date}")
        
        # ============================================================================
        # ✅ NEW: If aggregation requested, return single OVERALL metric
        # ============================================================================
        if aggregate:
            logger.info("[METRICS] Returning AGGREGATED metrics")
            
            query = """
            SELECT
                'OVERALL' as catchment,
                'ALL' as parameter,
                COUNT(*) as total_records,

                -- RELIABILITY: % of time satisfactory (z-score >= -0.5)
                -- Values: 0-1 (0% to 100%)
                CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
                NULLIF(COUNT(*), 0) as reliability,

                -- RESILIENCE: Recovery speed based on failure severity (FAILURES ONLY)
                -- Calculated as the inverse of average severity during failures
                -- Higher severity = longer recovery time = lower resilience
                -- Scale: 0-1, where severity levels: 1=Moderate, 2=Severe, 3=Extreme
                -- If no failures exist, resilience = 1.0 (perfect)
                CASE
                    WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 1.0
                    ELSE 1.0 - (AVG(CASE
                        WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT)
                        ELSE NULL
                    END) / 3.0)
                END as resilience,

                -- VULNERABILITY: Mean absolute deviation during failures ONLY
                -- Based on reference: mean(abs(z_score)) for failure records only
                -- Normalized to 0-1 scale by dividing by 6.0 (handles extreme z-scores)
                -- Capped at 1.0 (100%) to prevent overflow in sustainability calculation
                CASE
                    WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 0
                    ELSE
                        CASE
                            WHEN AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0 > 1.0
                            THEN 1.0
                            ELSE AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0
                        END
                END as vulnerability,

                -- SUSTAINABILITY: Weighted average formula (ISI)
                -- ISI = (w_r*R + w_s*S + w_v*(1-V)) / (w_r + w_s + w_v)
                -- Using equal weights (w_r=1, w_s=1, w_v=1)
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE
                        (
                            -- Reliability component (w_r=1)
                            (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) +
                            -- Resilience component (w_s=1) - only considers failures
                            CASE
                                WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 1.0
                                ELSE 1.0 - (AVG(CASE
                                    WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT)
                                    ELSE NULL
                                END) / 3.0)
                            END +
                            -- Robustness component (w_v=1): (1 - Vulnerability)
                            -- Vulnerability is capped at 1.0 to prevent negative sustainability
                            (1.0 - CASE
                                WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 0
                                ELSE
                                    CASE
                                        WHEN AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0 > 1.0
                                        THEN 1.0
                                        ELSE AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0
                                    END
                            END)
                        ) / 3.0  -- Divide by sum of weights (1+1+1=3)
                END as sustainability

            FROM dbo.ProcessedData pd
            JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
            WHERE pd.org_id = ?
            """

            params = [g.current_user_org_id]
            
            # Add filters if provided
            if catchment:
                query += " AND LOWER(c.catchment_name) = LOWER(?)"
                params.append(catchment)
                logger.info(f"[METRICS] Adding catchment filter: {catchment}")

            if parameter:
                query += " AND LOWER(pd.parameter_type) = LOWER(?)"
                params.append(parameter)
                logger.info(f"[METRICS] Adding parameter filter: {parameter}")

            # ✅ NEW: Add date range filters
            if start_date:
                query += " AND CAST(pd.measurement_date AS DATE) >= ?"
                params.append(start_date)
                logger.info(f"[METRICS] Adding start_date filter: {start_date}")

            if end_date:
                query += " AND CAST(pd.measurement_date AS DATE) <= ?"
                params.append(end_date)
                logger.info(f"[METRICS] Adding end_date filter: {end_date}")
        
        # ============================================================================
        # EXISTING: Per-catchment-parameter breakdown (when aggregate=false)
        # ============================================================================
        else:
            logger.info("[METRICS] Returning PER-CATCHMENT-PARAMETER metrics")
            
            query = """
            SELECT
                c.catchment_name,
                pd.parameter_type,
                COUNT(*) as total_records,

                -- RELIABILITY: % of time satisfactory (z-score >= -0.5)
                -- Values: 0-1 (0% to 100%)
                CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
                NULLIF(COUNT(*), 0) as reliability,

                -- RESILIENCE: Recovery speed based on failure severity (FAILURES ONLY)
                -- Calculated as the inverse of average severity during failures
                -- Higher severity = longer recovery time = lower resilience
                -- Scale: 0-1, where severity levels: 1=Moderate, 2=Severe, 3=Extreme
                -- If no failures exist, resilience = 1.0 (perfect)
                CASE
                    WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 1.0
                    ELSE 1.0 - (AVG(CASE
                        WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT)
                        ELSE NULL
                    END) / 3.0)
                END as resilience,

                -- VULNERABILITY: Mean absolute deviation during failures ONLY
                -- Based on reference: mean(abs(z_score)) for failure records only
                -- Normalized to 0-1 scale by dividing by 6.0 (handles extreme z-scores)
                -- Capped at 1.0 (100%) to prevent overflow in sustainability calculation
                CASE
                    WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 0
                    ELSE
                        CASE
                            WHEN AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0 > 1.0
                            THEN 1.0
                            ELSE AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0
                        END
                END as vulnerability,

                -- SUSTAINABILITY: Weighted average formula (ISI)
                -- ISI = (w_r*R + w_s*S + w_v*(1-V)) / (w_r + w_s + w_v)
                -- Using equal weights (w_r=1, w_s=1, w_v=1)
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE
                        (
                            -- Reliability component (w_r=1)
                            (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) +
                            -- Resilience component (w_s=1) - only considers failures
                            CASE
                                WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 1.0
                                ELSE 1.0 - (AVG(CASE
                                    WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT)
                                    ELSE NULL
                                END) / 3.0)
                            END +
                            -- Robustness component (w_v=1): (1 - Vulnerability)
                            -- Vulnerability is capped at 1.0 to prevent negative sustainability
                            (1.0 - CASE
                                WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 0
                                ELSE
                                    CASE
                                        WHEN AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0 > 1.0
                                        THEN 1.0
                                        ELSE AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) ELSE NULL END) / 6.0
                                    END
                            END)
                        ) / 3.0  -- Divide by sum of weights (1+1+1=3)
                END as sustainability

            FROM dbo.ProcessedData pd
            JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
            WHERE pd.org_id = ?
            """

            params = [g.current_user_org_id]
            
            if catchment:
                query += " AND LOWER(c.catchment_name) = LOWER(?)"
                params.append(catchment)
                logger.info(f"[METRICS] Adding catchment filter: {catchment}")

            if parameter:
                query += " AND LOWER(pd.parameter_type) = LOWER(?)"
                params.append(parameter)
                logger.info(f"[METRICS] Adding parameter filter: {parameter}")

            # ✅ NEW: Add date range filters
            if start_date:
                query += " AND CAST(pd.measurement_date AS DATE) >= ?"
                params.append(start_date)
                logger.info(f"[METRICS] Adding start_date filter: {start_date}")

            if end_date:
                query += " AND CAST(pd.measurement_date AS DATE) <= ?"
                params.append(end_date)
                logger.info(f"[METRICS] Adding end_date filter: {end_date}")

            query += " GROUP BY c.catchment_name, pd.parameter_type"
        
        # Execute query
        results = _exec(query, params if params else None)

        logger.info(f"[METRICS] Query returned {len(results) if results else 0} rows")

        # Process results
        metrics = []
        if results:
            for row in results:
                metric = {
                    'catchment': row[0],
                    'parameter': row[1],
                    'total_records': row[2],
                    'reliability': float(row[3]) if row[3] else 0,
                    'resilience': float(row[4]) if row[4] else 0,
                    'vulnerability': float(row[5]) if row[5] else 0,
                    'sustainability': float(row[6]) if row[6] else 0
                }
                metrics.append(metric)
                
                logger.info(f"[METRICS] Metric: {metric['catchment']} / {metric['parameter']} "
                           f"→ R:{metric['reliability']:.2f} Res:{metric['resilience']:.2f} "
                           f"V:{metric['vulnerability']:.2f} S:{metric['sustainability']:.2f}")
        
        logger.info(f"[METRICS] Returning {len(metrics)} metrics")
        
        return jsonify({
            'success': True,
            'metrics': metrics,
            'count': len(metrics),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"[METRICS] Error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'metrics': [],
            'count': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/metrics-calculated', methods=['GET'])
@require_auth()
def get_metrics_calculated():
    """Get calculated performance metrics - RELIABILITY, RESILIENCE, VULNERABILITY, SUSTAINABILITY"""
    try:
        catchment = request.args.get('catchment')
        parameter = request.args.get('parameter')
        parameter_type = request.args.get('parameter_type')
        
        # Use whichever parameter name was provided
        if not parameter and parameter_type:
            parameter = parameter_type
        
        query = """
        SELECT 
            c.catchment_name,
            pd.parameter_type,
            COUNT(*) as total_records,
            
            -- RELIABILITY: % of time satisfactory (z-score >= -0.5)
            CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / 
            NULLIF(COUNT(*), 0) as reliability,
            
            -- RESILIENCE: Recovery speed (inverse of avg severity, 0-1 scale)
            CASE 
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0.5
                ELSE 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)
            END as resilience,
            
            -- VULNERABILITY: Average severity as percentage (0-1)
            CASE 
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0
                ELSE AVG(CAST(pd.severity_level AS FLOAT)) / 3.0
            END as vulnerability,
            
            -- SUSTAINABILITY: Combined metric = Reliability * Resilience * (1 - Vulnerability)
            CASE 
                WHEN COUNT(*) = 0 THEN 0
                ELSE (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) *
                     (1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)) *
                     (1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0))
            END as sustainability
            
        FROM dbo.ProcessedData pd
        JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE pd.org_id = ?
        """
        params = [g.current_user_org_id]

        logger.info(f"[METRICS] Request: catchment={catchment}, parameter={parameter}")

        if catchment:
            query += " AND LOWER(c.catchment_name) = LOWER(?)"
            params.append(catchment)

        if parameter:
            query += " AND LOWER(pd.parameter_type) = LOWER(?)"
            params.append(parameter)
        
        query += " GROUP BY c.catchment_name, pd.parameter_type"

        results = _exec(query, params if params else None)

        logger.info(f"[METRICS] Query returned {len(results) if results else 0} rows")
        
        metrics = []
        if results:
            for row in results:
                metrics.append({
                    'catchment': row[0],
                    'parameter': row[1],
                    'total_records': row[2],
                    'reliability': float(row[3]) if row[3] else 0,
                    'resilience': float(row[4]) if row[4] else 0,
                    'vulnerability': float(row[5]) if row[5] else 0,
                    'sustainability': float(row[6]) if row[6] else 0
                })
        
        logger.info(f"[METRICS] Returning {len(metrics)} metric groups")
        
        return jsonify({
            'success': True,
            'metrics': metrics,
            'count': len(metrics),
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'metrics': [],
            'count': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/export-enhanced', methods=['GET'])
@require_auth()
def export_data_enhanced():
    """Enhanced export with more options"""
    try:
        catchment_id = request.args.get('catchment_id')
        parameter_type = request.args.get('parameter_type')
        include_classification = request.args.get('include_classification', 'true').lower() == 'true'
        format_type = request.args.get('format', 'csv')
        
        query = "SELECT * FROM dbo.ProcessedData WHERE org_id = ?"
        params = [g.current_user_org_id]

        if catchment_id:
            query += " AND catchment_id = ?"
            params.append(catchment_id)

        if parameter_type:
            query += " AND LOWER(parameter_type) = ?"
            params.append(parameter_type.lower())

        query += " ORDER BY measurement_date DESC"

        results = _exec(query, params)

        if not results:
            return jsonify({'error': 'No data to export'}), 404

        # Create DataFrame
        columns = ['processed_id', 'raw_id', 'source_id', 'catchment_id', 'measurement_date',
                  'parameter_type', 'original_value', 'mean_value', 'std_deviation',
                  'standardized_value', 'parameter_deviation', 'drought_index', 'classification',
                  'is_failure', 'severity_level', 'created_at', 'org_id']
        
        df = pd.DataFrame([tuple(row) for row in results], columns=columns)
        
        if not include_classification:
            df = df.drop(['classification', 'is_failure', 'severity_level'], axis=1)
        
        if format_type == 'csv':
            output = StringIO()
            df.to_csv(output, index=False)
            output.seek(0)
            return send_file(
                BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'groundwater_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
        else:
            output = BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'groundwater_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
    
    except Exception as e:
        logger.error(f"Enhanced export error: {e}")
        return jsonify(get_error_response(
            'EXPORT_ERROR', 'Failed to export data'
        )), 500

@app.route('/debug/baseflow-check', methods=['GET'])
@require_auth(roles=['admin'])
def debug_baseflow_check():
    """Debug endpoint to verify baseflow data"""
    try:
        source_id = request.args.get('source_id', type=int)
        
        if not source_id:
            return jsonify({'error': 'source_id required'}), 400
        
        query = """
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN baseflow_value IS NOT NULL THEN 1 ELSE 0 END) as with_values,
               SUM(CASE WHEN baseflow_deviation IS NOT NULL THEN 1 ELSE 0 END) as with_deviations
        FROM dbo.RawData 
        WHERE source_id = ? AND category = 'baseflow'
        """
        
        results = db.execute_query(query, (source_id,))
        
        if results:
            row = results[0]
            return jsonify({
                'total_records': row[0],
                'with_values': row[1],
                'with_deviations': row[2],
                'source_id': source_id
            }), 200
        
        return jsonify({'error': 'No data found'}), 404
    
    except Exception as e:
        logger.error(f"Debug error: {e}")
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    logger.info("Starting Groundwater Analysis Backend")
    logger.info(f"Database: {DB_CONFIG['database']} @ {DB_CONFIG['server']}")

    # Use environment variable for debug mode (defaults to False for production)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)