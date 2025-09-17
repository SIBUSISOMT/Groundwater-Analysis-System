# Groundwater Analysis System Backend API - Fixed Version
# Based on Shakhane et al. methodology

from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import pyodbc
import logging
from datetime import datetime, date
import os
from werkzeug.utils import secure_filename
import traceback
from typing import Dict, List, Tuple, Optional
import io
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('groundwater_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app with template and static folders pointing to frontend
app = Flask(__name__, 
           template_folder='../frontend',  # Point to your frontend folder
           static_folder='../frontend')    # For CSS, JS, and other static files
CORS(app)

# Configuration
class Config:
    # SQL Server connection settings
    SQL_SERVER = os.getenv('SQL_SERVER', 'localhost')
    SQL_DATABASE = os.getenv('SQL_DATABASE', 'GroundwaterAnalysis') 
    SQL_USERNAME = os.getenv('SQL_USERNAME', '')  # Windows Authentication if empty
    SQL_PASSWORD = os.getenv('SQL_PASSWORD', '')
    
    # File upload settings
    UPLOAD_FOLDER = 'uploads'
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    
    # Threshold definitions from Shakhane et al. study
    THRESHOLDS = {
        'normal_upper': 0.5,
        'normal_lower': -0.5,
        'moderate_lower': -1.0,
        'severe_lower': -1.5,
        'extreme_lower': -2.0
    }

config = Config()

# Ensure upload directory exists
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

class DatabaseManager:
    """Handles all SQL Server database operations"""
    
    def __init__(self):
        self.connection_string = self._build_connection_string()
    
    def _build_connection_string(self):
        """Build SQL Server connection string"""
        if config.SQL_USERNAME:
            return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={config.SQL_SERVER};DATABASE={config.SQL_DATABASE};UID={config.SQL_USERNAME};PWD={config.SQL_PASSWORD}"
        else:
            return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={config.SQL_SERVER};DATABASE={config.SQL_DATABASE};Trusted_Connection=yes;"
    
    def get_connection(self):
        """Get database connection"""
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True):
        """Execute SQL query with parameters"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch:
                    columns = [column[0] for column in cursor.description] if cursor.description else []
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                else:
                    conn.commit()
                    return cursor.rowcount
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def insert_data_source(self, file_name: str, file_size: int, category: str, subcatchment: str) -> int:
        """Insert new data source record"""
        query = """
        INSERT INTO dbo.DataSources (file_name, file_size_kb, processing_status, category, subcatchment)
        OUTPUT INSERTED.source_id
        VALUES (?, ?, 'Processing', ?, ?)
        """
        result = self.execute_query(query, (file_name, file_size, category, subcatchment), fetch=True)
        return result[0]['source_id'] if result else None
    
    def update_data_source_status(self, source_id: int, status: str, error_message: str = None, 
                                  total_records: int = None, date_range: tuple = None):
        """Update data source status with string date handling"""
        query = """
        UPDATE dbo.DataSources 
        SET processing_status = ?, error_message = ?, total_records = ?,
            date_range_start = ?, date_range_end = ?, updated_at = GETDATE()
        WHERE source_id = ?
        """
        
        # Keep dates as strings for DataSources table (NVARCHAR fields)
        start_date_str = None
        end_date_str = None
        
        if date_range:
            start_date_str, end_date_str = date_range
            # Store as YYYY-MM-DD string format
        
        self.execute_query(query, (status, error_message, total_records, start_date_str, end_date_str, source_id), fetch=False)
    
    def get_catchment_id(self, catchment_name: str) -> Optional[int]:
        """Get catchment ID or create if doesn't exist"""
        query = "SELECT catchment_id FROM dbo.Catchments WHERE catchment_name = ?"
        result = self.execute_query(query, (catchment_name,))
        
        if result:
            return result[0]['catchment_id']
        else:
            # Create new catchment
            insert_query = """
            INSERT INTO dbo.Catchments (catchment_name) 
            OUTPUT INSERTED.catchment_id
            VALUES (?)
            """
            result = self.execute_query(insert_query, (catchment_name,), fetch=True)
            return result[0]['catchment_id'] if result else None

    def insert_raw_data(self, values: dict):
        """
        Insert a row into RawData table with proper DATE handling.
        Now measurement_date is a proper DATE field in the database.
        """
        query = """
        INSERT INTO dbo.RawData (
            source_id, catchment_id, measurement_date, category,
            recharge_inches, recharge_converted, average_recharge, recharge_stdev, drought_index_recharge,
            baseflow_value, average_baseflow, baseflow_stdev, standardized_baseflow,
            gw_level, average_gw_level, gw_level_stdev, standardized_gw_level,
            original_sheet_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Prepare parameters - measurement_date should be a proper date object
        params = (
            values.get('source_id'),
            values.get('catchment_id'),
            values.get('measurement_date'),  # This should be a datetime.date object now
            values.get('category'),
            values.get('recharge_inches'),
            values.get('recharge_converted'),
            values.get('average_recharge'),
            values.get('recharge_stdev'),
            values.get('drought_index_recharge'),
            values.get('baseflow_value'),
            values.get('average_baseflow'),
            values.get('baseflow_stdev'),
            values.get('standardized_baseflow'),
            values.get('gw_level'),
            values.get('average_gw_level'),
            values.get('gw_level_stdev'),
            values.get('standardized_gw_level'),
            values.get('original_sheet_name')
        )
        
        try:
            self.execute_query(query, params, fetch=False)
        except Exception as e:
            logger.error(f"Failed to insert raw data: {e}")
            logger.error(f"Values: {values}")
            raise


class GroundwaterAnalyzer:
    """Implements Shakhane et al. groundwater analysis methodology"""
    
    @staticmethod
    def calculate_zscore(values: np.array) -> tuple:
        """
        Calculate Z-score normalization (Equation 3 from paper)
        Z = (p - p̄) / σ
        """
        # Remove NaN values for calculation
        clean_values = values[~np.isnan(values)]
        if len(clean_values) == 0:
            return np.zeros_like(values), 0, 0
        
        mean_val = np.mean(clean_values)
        std_val = np.std(clean_values, ddof=1)  # Sample standard deviation
        
        if std_val == 0:
            logger.warning("Standard deviation is zero, using values as-is")
            z_scores = np.zeros_like(values)
        else:
            z_scores = (values - mean_val) / std_val
        
        return z_scores, mean_val, std_val
    
    @staticmethod
    def classify_threshold(z_score: float) -> dict:
        """
        Classify z-score based on threshold levels from the study
        """
        if np.isnan(z_score):
            return {'level': 'Normal', 'severity': 0, 'is_failure': False}
            
        if z_score >= config.THRESHOLDS['normal_lower'] and z_score <= config.THRESHOLDS['normal_upper']:
            return {'level': 'Normal', 'severity': 0, 'is_failure': False}
        elif z_score < config.THRESHOLDS['normal_lower'] and z_score >= config.THRESHOLDS['moderate_lower']:
            return {'level': 'Moderate_Deficit', 'severity': 1, 'is_failure': True}
        elif z_score < config.THRESHOLDS['moderate_lower'] and z_score >= config.THRESHOLDS['severe_lower']:
            return {'level': 'Severe_Deficit', 'severity': 2, 'is_failure': True}
        elif z_score < config.THRESHOLDS['severe_lower']:
            return {'level': 'Extreme_Deficit', 'severity': 3, 'is_failure': True}
        else:
            return {'level': 'Surplus', 'severity': -1, 'is_failure': False}
    
    @staticmethod
    def calculate_performance_metrics(z_scores: np.array, is_failure: np.array) -> dict:
        """
        Calculate reliability, resilience, and vulnerability metrics
        Based on equations from Shakhane et al. study
        """
        total_points = len(z_scores)
        failure_count = np.sum(is_failure)
        
        # Reliability - probability of satisfactory performance
        reliability = (total_points - failure_count) / total_points if total_points > 0 else 0
        
        # Find failure sequences for resilience calculation
        failure_sequences = []
        current_sequence = []
        
        for i, failed in enumerate(is_failure):
            if failed:
                current_sequence.append(i)
            else:
                if current_sequence:
                    failure_sequences.append(current_sequence.copy())
                    current_sequence = []
        
        # Add last sequence if it ends in failure
        if current_sequence:
            failure_sequences.append(current_sequence)
        
        # Resilience calculation (Equation 8): γ = (1/ρ * Σα(j))^-1
        if failure_sequences:
            avg_failure_duration = np.mean([len(seq) for seq in failure_sequences])
            resilience = 1 / avg_failure_duration if avg_failure_duration > 0 else 0
        else:
            resilience = 1.0  # Perfect resilience if no failures
            avg_failure_duration = 0
        
        # Vulnerability calculation (Equations 9-10)
        if failure_count > 0:
            failure_severities = np.abs(z_scores[is_failure])
            avg_severity = np.mean(failure_severities)
            max_severity = np.max(failure_severities)
            vulnerability = avg_severity / max_severity if max_severity > 0 else 0
        else:
            vulnerability = 0
            avg_severity = 0
            max_severity = 0
        
        # Sustainability Index (Equation 11): S = α * γ * (1 - rv)
        sustainability = reliability * resilience * (1 - vulnerability)
        
        return {
            'reliability': float(reliability),
            'resilience': float(resilience),
            'vulnerability': float(vulnerability),
            'sustainability': float(sustainability),
            'total_failures': int(failure_count),
            'failure_sequences': len(failure_sequences),
            'avg_failure_duration': float(avg_failure_duration),
            'max_failure_duration': max([len(seq) for seq in failure_sequences]) if failure_sequences else 0,
            'avg_failure_severity': float(avg_severity),
            'max_failure_severity': float(max_severity)
        }

# Initialize database manager
db = DatabaseManager()
analyzer = GroundwaterAnalyzer()

# FRONTEND ROUTES - Added to serve your HTML
@app.route('/')
def home():
    """Serve the main index.html page"""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Failed to serve index.html: {e}")
        return f"<h1>Groundwater Analysis System</h1><p>Error loading page: {e}</p><p>Make sure index.html exists in your frontend folder.</p>"

@app.route('/<path:filename>')
def serve_static_files(filename):
    """Serve static files (CSS, JS, images) from frontend folder"""
    try:
        return send_from_directory('../frontend', filename)
    except Exception as e:
        logger.error(f"Failed to serve static file {filename}: {e}")
        return f"File not found: {filename}", 404

# API ROUTES - All your existing API routes
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.execute_query("SELECT 1 as test")
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected'
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'database': 'disconnected',
            'error': str(e)
        }), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload and process Excel file - Fixed for proper DATE handling"""
    try:
        file = request.files['file']
        category = request.form.get('category')
        subcatchment = request.form.get('subcatchment')

        if not file or not category or not subcatchment:
            return jsonify({'error': 'File, category, and subcatchment are required.'}), 400

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
        file.save(filepath)
        file_size_kb = os.path.getsize(filepath) // 1024

        # Create data source record
        source_id = db.insert_data_source(filename, file_size_kb, category, subcatchment)
        if not source_id:
            return jsonify({'error': 'Failed to create data source record'}), 500

        # Read Excel file
        try:
            df = pd.read_excel(filepath)
        except Exception as e:
            db.update_data_source_status(source_id, 'Failed', f'Failed to read Excel file: {str(e)}')
            return jsonify({'error': f'Failed to read Excel file: {str(e)}'}), 400
        
        # Clean column names
        df.columns = df.columns.str.strip()
        original_columns = list(df.columns)
        df.columns = df.columns.str.lower()

        logger.info(f"Excel columns found: {original_columns}")

        # Map columns based on category
        if category.lower() == 'gwlevel':
            required = ['date', 'gw level', 'average gw level', 'stdev', 'standardized gw level']
        elif category.lower() == 'recharge':
            required = ['date', 'recharge (inches)', 'recharge', 'average recharge', 'stdev', 'drought index - recharge']
        elif category.lower() == 'baseflow':
            required = ['date', 'baseflow', 'average baseflow', 'stdev', 'standardized baseflow']
        else:
            db.update_data_source_status(source_id, 'Failed', f'Unknown category: {category}')
            return jsonify({'error': f'Unknown category: {category}'}), 400

        # Check for required columns
        missing = [col for col in required if col not in df.columns]
        if missing:
            error_msg = f'Missing columns: {missing}. Available columns: {list(df.columns)}'
            db.update_data_source_status(source_id, 'Failed', error_msg)
            return jsonify({'error': error_msg}), 400

        # Process records with proper date handling
        total_inserted = 0
        date_range_start = None
        date_range_end = None
        errors = []

        catchment_id = db.get_catchment_id(subcatchment)
        if not catchment_id:
            error_msg = f'Failed to get or create catchment: {subcatchment}'
            db.update_data_source_status(source_id, 'Failed', error_msg)
            return jsonify({'error': error_msg}), 500

        logger.info(f"Processing {len(df)} rows for catchment_id: {catchment_id}")
        
        for idx, row in df.iterrows():
            try:
                raw_date = row['date']
                
                # Skip rows with empty/null dates
                if pd.isna(raw_date) or raw_date == '' or raw_date is None:
                    logger.debug(f"Row {idx}: Empty date, skipping")
                    continue
                
                # Parse date and convert to Python date object
                parsed_date = None
                date_str_for_range = None
                
                try:
                    if isinstance(raw_date, (pd.Timestamp, datetime)):
                        parsed_date = raw_date.date()
                        date_str_for_range = raw_date.strftime('%Y-%m-%d')
                    elif isinstance(raw_date, date):
                        parsed_date = raw_date
                        date_str_for_range = raw_date.strftime('%Y-%m-%d')
                    elif isinstance(raw_date, str):
                        # Clean the date string
                        raw_date = str(raw_date).strip()
                        if not raw_date:
                            continue
                            
                        # Try multiple date formats
                        date_formats = [
                            '%Y-%m-%d',    # 2011-01-01
                            '%Y/%m/%d',    # 2011/01/01  
                            '%Y-%m',       # 2011-01 (will default to first day of month)
                            '%Y/%m',       # 2011/01 (will default to first day of month)
                            '%m/%d/%Y',    # 01/01/2011
                            '%d/%m/%Y',    # 01/01/2011
                            '%Y%m%d'       # 20110101
                        ]
                        
                        for date_format in date_formats:
                            try:
                                temp_date = datetime.strptime(raw_date, date_format)
                                parsed_date = temp_date.date()
                                date_str_for_range = temp_date.strftime('%Y-%m-%d')
                                break
                            except ValueError:
                                continue
                                
                        if not parsed_date:
                            # Try pandas to_datetime as last resort
                            try:
                                temp_date = pd.to_datetime(raw_date, errors='raise')
                                parsed_date = temp_date.date()
                                date_str_for_range = temp_date.strftime('%Y-%m-%d')
                            except:
                                logger.warning(f"Row {idx}: Could not parse date '{raw_date}', skipping")
                                errors.append(f"Row {idx}: Invalid date format '{raw_date}'")
                                continue
                    else:
                        # Handle numeric dates (Excel serial dates)
                        try:
                            if isinstance(raw_date, (int, float)) and not pd.isna(raw_date):
                                # Convert Excel serial date to datetime
                                temp_date = pd.to_datetime(raw_date, origin='1899-12-30', unit='D')
                                parsed_date = temp_date.date()
                                date_str_for_range = temp_date.strftime('%Y-%m-%d')
                            else:
                                logger.warning(f"Row {idx}: Invalid date type/value '{raw_date}', skipping")
                                continue
                        except:
                            logger.warning(f"Row {idx}: Could not parse numeric date '{raw_date}', skipping")
                            continue

                except Exception as date_error:
                    logger.warning(f"Row {idx}: Date parsing error for '{raw_date}': {str(date_error)}")
                    errors.append(f"Row {idx}: Date parsing error - {str(date_error)}")
                    continue

                # Validate parsed date
                if not parsed_date:
                    logger.warning(f"Row {idx}: Failed to parse date '{raw_date}', skipping")
                    continue

                # Track date range for metadata (string format for DataSources table)
                if not date_range_start or date_str_for_range < date_range_start:
                    date_range_start = date_str_for_range
                if not date_range_end or date_str_for_range > date_range_end:
                    date_range_end = date_str_for_range

                # Safely convert values to float, handle NaN/empty values
                def safe_float(value):
                    """Safely convert value to float, return None if invalid"""
                    if pd.isna(value) or value == '' or value is None:
                        return None
                    try:
                        if isinstance(value, str):
                            value = value.strip()
                            if value == '' or value.lower() in ['nan', 'null', 'none', '#n/a', 'n/a']:
                                return None
                        return float(value)
                    except (ValueError, TypeError):
                        logger.debug(f"Could not convert '{value}' to float")
                        return None

                # Prepare values for RawData table
                values = {
                    'source_id': source_id,
                    'catchment_id': catchment_id,
                    'measurement_date': parsed_date,  # Now using actual date object
                    'category': category,
                    'original_sheet_name': subcatchment
                }

                # Add category-specific fields with validation
                if category.lower() == 'gwlevel':
                    gw_level = safe_float(row.get('gw level'))
                    avg_gw_level = safe_float(row.get('average gw level'))
                    gw_stdev = safe_float(row.get('stdev'))
                    std_gw_level = safe_float(row.get('standardized gw level'))
                    
                    # Skip row if all main values are None
                    if all(v is None for v in [gw_level, avg_gw_level, std_gw_level]):
                        logger.debug(f"Row {idx}: All GW Level values are None, skipping")
                        continue
                    
                    values.update({
                        'gw_level': gw_level,
                        'average_gw_level': avg_gw_level,
                        'gw_level_stdev': gw_stdev,
                        'standardized_gw_level': std_gw_level,
                        # Set other fields to None
                        'recharge_inches': None,
                        'recharge_converted': None,
                        'average_recharge': None,
                        'recharge_stdev': None,
                        'drought_index_recharge': None,
                        'baseflow_value': None,
                        'average_baseflow': None,
                        'baseflow_stdev': None,
                        'standardized_baseflow': None
                    })
                    
                elif category.lower() == 'recharge':
                    recharge_inches = safe_float(row.get('recharge (inches)'))
                    recharge_converted = safe_float(row.get('recharge'))
                    avg_recharge = safe_float(row.get('average recharge'))
                    recharge_stdev = safe_float(row.get('stdev'))
                    drought_index = safe_float(row.get('drought index - recharge'))
                    
                    # Skip row if all main values are None
                    if all(v is None for v in [recharge_inches, recharge_converted, drought_index]):
                        logger.debug(f"Row {idx}: All recharge values are None, skipping")
                        continue
                    
                    values.update({
                        'recharge_inches': recharge_inches,
                        'recharge_converted': recharge_converted,
                        'average_recharge': avg_recharge,
                        'recharge_stdev': recharge_stdev,
                        'drought_index_recharge': drought_index,
                        # Set other fields to None
                        'baseflow_value': None,
                        'average_baseflow': None,
                        'baseflow_stdev': None,
                        'standardized_baseflow': None,
                        'gw_level': None,
                        'average_gw_level': None,
                        'gw_level_stdev': None,
                        'standardized_gw_level': None
                    })
                    
                elif category.lower() == 'baseflow':
                    baseflow_val = safe_float(row.get('baseflow'))
                    avg_baseflow = safe_float(row.get('average baseflow'))
                    baseflow_stdev = safe_float(row.get('stdev'))
                    std_baseflow = safe_float(row.get('standardized baseflow'))
                    
                    # Skip row if all main values are None
                    if all(v is None for v in [baseflow_val, avg_baseflow, std_baseflow]):
                        logger.debug(f"Row {idx}: All baseflow values are None, skipping")
                        continue
                    
                    values.update({
                        'baseflow_value': baseflow_val,
                        'average_baseflow': avg_baseflow,
                        'baseflow_stdev': baseflow_stdev,
                        'standardized_baseflow': std_baseflow,
                        # Set other fields to None
                        'recharge_inches': None,
                        'recharge_converted': None,
                        'average_recharge': None,
                        'recharge_stdev': None,
                        'drought_index_recharge': None,
                        'gw_level': None,
                        'average_gw_level': None,
                        'gw_level_stdev': None,
                        'standardized_gw_level': None
                    })
                
                # Insert the record
                try:
                    db.insert_raw_data(values)
                    total_inserted += 1
                    logger.debug(f"Row {idx}: Successfully inserted data for date {date_str_for_range}")
                except Exception as insert_error:
                    error_msg = f"Row {idx}: Insert failed - {str(insert_error)}"
                    errors.append(error_msg)
                    logger.error(f"Insert error for row {idx}: {str(insert_error)}")
                    logger.error(f"Values that failed: {values}")
                    continue
                
            except Exception as row_error:
                error_msg = f"Row {idx}: Processing error - {str(row_error)}"
                errors.append(error_msg)
                logger.error(f"Row processing error: {str(row_error)}")
                continue

        # Update data source status with comprehensive information
        logger.info(f"Processing complete. Inserted: {total_inserted}, Errors: {len(errors)}")
        
        if errors and total_inserted == 0:
            # Complete failure
            error_summary = f"Failed to process any records. Errors: {'; '.join(errors[:5])}"
            db.update_data_source_status(source_id, 'Failed', error_summary, 0, None)
            return jsonify({
                'error': 'Failed to process any records',
                'details': errors[:10],
                'total_errors': len(errors)
            }), 400
        elif errors:
            # Partial success
            error_summary = f"Processed {total_inserted} records with {len(errors)} errors. Sample errors: {'; '.join(errors[:3])}"
            db.update_data_source_status(
                source_id, 'Completed with Errors', error_summary, 
                total_inserted, (date_range_start, date_range_end)
            )
        else:
            # Complete success
            db.update_data_source_status(
                source_id, 'Completed', None, total_inserted, 
                (date_range_start, date_range_end)
            )

        # Process raw data into analyzed format
        try:
            logger.info(f"Running data analysis for source_id: {source_id}")
            db.execute_query("EXEC sp_ProcessRawData ?", (source_id,), fetch=False)
            logger.info("Data analysis completed successfully")
        except Exception as proc_error:
            logger.error(f"Failed to process raw data: {str(proc_error)}")
            # Don't fail the upload, but log the issue
            db.update_data_source_status(
                source_id, 'Upload Complete - Processing Failed', 
                f"Raw data uploaded but analysis failed: {str(proc_error)}", 
                total_inserted, (date_range_start, date_range_end)
            )

        return jsonify({
            'message': 'File uploaded and processed successfully.',
            'processed_records': total_inserted,
            'errors': len(errors),
            'error_details': errors[:10] if errors else None,
            'date_range': f"{date_range_start} to {date_range_end}" if date_range_start and date_range_end else None,
            'source_id': source_id
        }), 200

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        logger.error(traceback.format_exc())
        
        # Try to update the source status if source_id exists
        try:
            if 'source_id' in locals():
                db.update_data_source_status(source_id, 'Failed', str(e))
        except Exception as status_error:
            logger.error(f"Failed to update status: {status_error}")
            
        return jsonify({'error': str(e)}), 500
@app.route('/api/catchments', methods=['GET'])
def get_catchments():
    """Get list of available catchments"""
    try:
        query = """
        SELECT c.catchment_id, c.catchment_name, c.catchment_code, c.area_km2,
               COUNT(DISTINCT pd.source_id) as datasets,
               MIN(pd.measurement_date) as earliest_date,
               MAX(pd.measurement_date) as latest_date,
               COUNT(pd.processed_id) as total_records
        FROM dbo.Catchments c
        LEFT JOIN dbo.ProcessedData pd ON c.catchment_id = pd.catchment_id
        GROUP BY c.catchment_id, c.catchment_name, c.catchment_code, c.area_km2
        ORDER BY c.catchment_name
        """
        
        catchments = db.execute_query(query)
        return jsonify({'catchments': catchments})
        
    except Exception as e:
        logger.error(f"Failed to get catchments: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data', methods=['GET'])
def get_data():

    """Get data with proper error handling and parameter mapping"""
    try:
        # Parse query parameters
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', '').upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        source_id = request.args.get('source_id')
        
        logger.info(f"Data request received: catchment={catchment_name}, parameter={parameter}, start_date={start_date}, end_date={end_date}, source_id={source_id}")
        
        # Map frontend parameter names to database categories
        parameter_mapping = {
            'GWL': 'gwlevel',
            'GWLEVEL': 'gwlevel',
            'RECHARGE': 'recharge', 
            'BASEFLOW': 'baseflow'
        }
        
        # Default to recharge if parameter not recognized
        db_category = parameter_mapping.get(parameter, 'recharge')
        logger.info(f"Mapped parameter '{parameter}' to database category '{db_category}'")
        
        # First, let's try to query from RawData table (which we know exists from upload code)
        base_query = """
        SELECT rd.measurement_date, 
               c.catchment_name, 
               rd.source_id,
               rd.category,
               CASE 
                   WHEN rd.category = 'gwlevel' THEN rd.gw_level
                   WHEN rd.category = 'recharge' THEN rd.recharge_converted
                   WHEN rd.category = 'baseflow' THEN rd.baseflow_value
                   ELSE NULL
               END as original_value,
               CASE 
                   WHEN rd.category = 'gwlevel' THEN rd.standardized_gw_level
                   WHEN rd.category = 'recharge' THEN rd.drought_index_recharge
                   WHEN rd.category = 'baseflow' THEN rd.standardized_baseflow
                   ELSE NULL
               END as zscore_value,
               CASE 
                   WHEN rd.category = 'gwlevel' THEN rd.average_gw_level
                   WHEN rd.category = 'recharge' THEN rd.average_recharge
                   WHEN rd.category = 'baseflow' THEN rd.average_baseflow
                   ELSE NULL
               END as average_value
        FROM dbo.RawData rd
        INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
        WHERE 1=1
        """
        
        conditions = []
        params = []
        
        # Add category filter
        conditions.append("rd.category = ?")
        params.append(db_category)
        
        # Add catchment filter
        if catchment_name and catchment_name.upper() != 'ALL':
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        # Add date filters
        if start_date:
            try:
                # Validate date format
                datetime.strptime(start_date, '%Y-%m-%d')
                conditions.append("rd.measurement_date >= ?")
                params.append(start_date)
            except ValueError:
                logger.warning(f"Invalid start_date format: {start_date}")
                
        if end_date:
            try:
                # Validate date format  
                datetime.strptime(end_date, '%Y-%m-%d')
                conditions.append("rd.measurement_date <= ?")
                params.append(end_date)
            except ValueError:
                logger.warning(f"Invalid end_date format: {end_date}")
            
        if source_id:
            conditions.append("rd.source_id = ?")
            params.append(int(source_id))
        
        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        # Add ordering and limit for performance
        base_query += " ORDER BY rd.measurement_date DESC"
        
        # Add pagination limit
        limit = min(int(request.args.get('limit', 1000)), 10000)
        base_query += f" OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
        
        logger.info(f"Executing query: {base_query}")
        logger.info(f"With parameters: {params}")
        
        # Execute the query
        try:
            data = db.execute_query(base_query, tuple(params))
            
            if not data:
                logger.info("No data found matching the filters")
                
                # Let's check what data is available
                debug_query = """
                SELECT DISTINCT c.catchment_name, rd.category, COUNT(*) as record_count
                FROM dbo.RawData rd
                INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
                GROUP BY c.catchment_name, rd.category
                ORDER BY c.catchment_name, rd.category
                """
                
                available_data = db.execute_query(debug_query)
                logger.info(f"Available data summary: {available_data}")
                
                return jsonify({
                    'data': [],
                    'message': 'No data found for the specified filters',
                    'available_data': available_data,
                    'filters_applied': {
                        'catchment': catchment_name,
                        'parameter': parameter,
                        'db_category': db_category,
                        'start_date': start_date,
                        'end_date': end_date,
                        'source_id': source_id
                    }
                }), 200
            
            # Format the data for response
            formatted_data = []
            for row in data:
                formatted_row = {
                    'measurement_date': row['measurement_date'].strftime('%Y-%m-%d') if isinstance(row['measurement_date'], (date, datetime)) else str(row['measurement_date']),
                    'catchment_name': row['catchment_name'],
                    'source_id': row['source_id'],
                    'category': row['category'],
                    'original_value': float(row['original_value']) if row['original_value'] is not None else None,
                    'zscore': float(row['zscore_value']) if row['zscore_value'] is not None else None,
                    'average_value': float(row['average_value']) if row['average_value'] is not None else None
                }
                
                # Add classification based on zscore
                if formatted_row['zscore'] is not None:
                    zscore = formatted_row['zscore']
                    if zscore >= -0.5 and zscore <= 0.5:
                        classification = 'Normal'
                        is_failure = False
                        severity = 0
                    elif zscore < -0.5 and zscore >= -1.0:
                        classification = 'Moderate_Deficit'
                        is_failure = True
                        severity = 1
                    elif zscore < -1.0 and zscore >= -1.5:
                        classification = 'Severe_Deficit'
                        is_failure = True
                        severity = 2
                    elif zscore < -1.5:
                        classification = 'Extreme_Deficit'
                        is_failure = True
                        severity = 3
                    else:
                        classification = 'Surplus'
                        is_failure = False
                        severity = -1
                        
                    formatted_row.update({
                        'classification': classification,
                        'is_failure': is_failure,
                        'severity_level': severity
                    })
                
                formatted_data.append(formatted_row)
            
            logger.info(f"Successfully retrieved {len(formatted_data)} records")
            
            return jsonify({
                'data': formatted_data,
                'count': len(formatted_data),
                'parameter': parameter,
                'db_category': db_category,
                'filters_applied': {
                    'catchment': catchment_name,
                    'parameter': parameter,
                    'start_date': start_date,
                    'end_date': end_date,
                    'source_id': source_id
                }
            }), 200
            
        except Exception as query_error:
            logger.error(f"Database query failed: {str(query_error)}")
            logger.error(f"Query: {base_query}")
            logger.error(f"Params: {params}")
            
            # Try to provide more debugging information
            try:
                # Check if tables exist
                table_check_query = """
                SELECT TABLE_NAME, TABLE_SCHEMA 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME IN ('RawData', 'Catchments', 'ProcessedData')
                """
                tables = db.execute_query(table_check_query)
                logger.info(f"Available tables: {tables}")
                
                # Check RawData structure
                column_check_query = """
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'RawData'
                ORDER BY ORDINAL_POSITION
                """
                columns = db.execute_query(column_check_query)
                logger.info(f"RawData columns: {columns}")
                
            except Exception as debug_error:
                logger.error(f"Debug query failed: {debug_error}")
            
            raise query_error
            
    except Exception as e:
        logger.error(f"Data API error: {str(e)}")
        logger.error(traceback.format_exc())
        
        return jsonify({
            'error': 'Failed to retrieve data',
            'details': str(e),
            'request_info': {
                'catchment': request.args.get('catchment'),
                'parameter': request.args.get('parameter'),
                'start_date': request.args.get('start_date'),
                'end_date': request.args.get('end_date'),
                'source_id': request.args.get('source_id')
            }
        }), 500
    """Get processed data with filters"""
    try:
        # Parse query parameters
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter')
        if not parameter:
            # Use category from the source_id if available, or default to 'recharge'
            source_id = request.args.get('source_id')
            if source_id:
                # Query the category from DataSources
                cat_query = "SELECT category FROM dbo.DataSources WHERE source_id = ?"
                cat_result = db.execute_query(cat_query, (int(source_id),))
                if cat_result:
                    parameter = cat_result[0]['category'].lower()
                else:
                    parameter = 'recharge'
            else:
                parameter = 'recharge'
        else:
            parameter = parameter.lower()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        source_id = request.args.get('source_id')
        
        # FIXED: Build query dynamically to avoid parameter count issues
        base_query = f"""
        SELECT pd.measurement_date, c.catchment_name, pd.source_id,
               pd.{parameter.lower()}_original as original_value,
               pd.{parameter.lower()}_zscore as zscore,
               pd.{parameter.lower()}_classification as classification,
               pd.{parameter.lower()}_is_failure as is_failure,
               pd.{parameter.lower()}_severity_level as severity_level
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE pd.{parameter.lower()}_original IS NOT NULL
        """
        
        conditions = []
        params = []
        
        if catchment_name:
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if start_date:
            conditions.append("pd.measurement_date >= ?")
            params.append(start_date)
            
        if end_date:
            conditions.append("pd.measurement_date <= ?")
            params.append(end_date)
            
        if source_id:
            conditions.append("pd.source_id = ?")
            params.append(int(source_id))
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " ORDER BY pd.measurement_date"
        
        data = db.execute_query(base_query, tuple(params) if params else None)
        
        return jsonify({
            'data': data,
            'parameter': parameter,
            'filters': {
                'catchment': catchment_name,
                'start_date': start_date,
                'end_date': end_date,
                'source_id': source_id
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get data: {e}")
        return jsonify({'error': str(e)}), 500

# Add a debug endpoint to check what data is available
@app.route('/api/debug/data-summary', methods=['GET'])
def debug_data_summary():
    """Debug endpoint to see what data is available"""
    try:
        # Check available catchments
        catchments_query = """
        SELECT c.catchment_name, COUNT(*) as record_count
        FROM dbo.RawData rd
        INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
        GROUP BY c.catchment_name
        ORDER BY c.catchment_name
        """
        catchments = db.execute_query(catchments_query)
        
        # Check available categories
        categories_query = """
        SELECT rd.category, COUNT(*) as record_count,
               MIN(rd.measurement_date) as earliest_date,
               MAX(rd.measurement_date) as latest_date
        FROM dbo.RawData rd
        GROUP BY rd.category
        ORDER BY rd.category
        """
        categories = db.execute_query(categories_query)
        
        # Check data by catchment and category
        detailed_query = """
        SELECT c.catchment_name, rd.category, COUNT(*) as record_count,
               MIN(rd.measurement_date) as earliest_date,
               MAX(rd.measurement_date) as latest_date
        FROM dbo.RawData rd
        INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
        GROUP BY c.catchment_name, rd.category
        ORDER BY c.catchment_name, rd.category
        """
        detailed = db.execute_query(detailed_query)
        
        return jsonify({
            'catchments': catchments,
            'categories': categories, 
            'detailed_breakdown': detailed
        }), 200
        
    except Exception as e:
        logger.error(f"Debug summary failed: {e}")
        return jsonify({'error': str(e)}), 500

# Add endpoint to get filter options
@app.route('/api/filter-options', methods=['GET'])
def get_filter_options():
    """Get available filter options for the frontend"""
    try:
        # Get unique catchments that have data
        catchments_query = """
        SELECT DISTINCT c.catchment_name
        FROM dbo.Catchments c
        INNER JOIN dbo.RawData rd ON c.catchment_id = rd.catchment_id
        ORDER BY c.catchment_name
        """
        catchments_result = db.execute_query(catchments_query)
        catchments = [row['catchment_name'] for row in catchments_result]
        
        # Get unique categories
        categories_query = """
        SELECT DISTINCT rd.category
        FROM dbo.RawData rd
        WHERE rd.category IS NOT NULL
        ORDER BY rd.category
        """
        categories_result = db.execute_query(categories_query)
        
        # Map categories to frontend parameter names
        category_to_param = {
            'gwlevel': 'GWL',
            'recharge': 'RECHARGE',
            'baseflow': 'BASEFLOW'
        }
        
        parameters = []
        for row in categories_result:
            category = row['category']
            if category in category_to_param:
                parameters.append(category_to_param[category])
        
        return jsonify({
            'catchments': catchments,
            'parameters': parameters
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get filter options: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/metrics', methods=['GET'])
def get_performance_metrics():
    """Get performance metrics from PerformanceMetrics table"""
    try:
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter')
        
        base_query = """
        SELECT 
            pm.reliability,
            pm.resilience, 
            pm.vulnerability,
            pm.sustainability,
            c.catchment_name,
            pm.parameter_type
        FROM dbo.PerformanceMetrics pm
        INNER JOIN dbo.Catchments c ON pm.catchment_id = c.catchment_id
        WHERE 1=1
        """
        
        conditions = []
        params = []
        
        if catchment_name:
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if parameter:
            # Map frontend parameter names to database parameter names
            param_mapping = {'GWR': 'Recharge', 'GWL': 'GWLevel', 'GWB': 'Baseflow'}
            db_param = param_mapping.get(parameter, parameter)
            conditions.append("pm.parameter_type = ?")
            params.append(db_param)
            
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
            
        base_query += " ORDER BY c.catchment_name, pm.parameter_type"
        
        metrics = db.execute_query(base_query, tuple(params) if params else None)
        
        return jsonify({'metrics': metrics})
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/failure-analysis', methods=['GET'])
def get_failure_analysis():
    """Get failure analysis summary"""
    try:
        catchment_name = request.args.get('catchment')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Use the existing ProcessedData table directly instead of non-existent view
        base_query = """
        SELECT 
            c.catchment_name,
            YEAR(pd.measurement_date) as year,
            MONTH(pd.measurement_date) as month,
            COUNT(*) as total_records,
            SUM(CASE WHEN pd.parameter_type = 'Recharge' AND pd.is_failure = 1 THEN 1 ELSE 0 END) as gwr_failures,
            SUM(CASE WHEN pd.parameter_type = 'GWLevel' AND pd.is_failure = 1 THEN 1 ELSE 0 END) as gwl_failures,
            SUM(CASE WHEN pd.parameter_type = 'Baseflow' AND pd.is_failure = 1 THEN 1 ELSE 0 END) as gwb_failures,
            SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) as total_failures
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE 1=1
        """
        
        conditions = []
        params = []
        
        if catchment_name:
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if start_date and end_date:
            conditions.append("pd.measurement_date BETWEEN ? AND ?")
            params.extend([start_date, end_date])
            
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
            
        base_query += " GROUP BY c.catchment_name, YEAR(pd.measurement_date), MONTH(pd.measurement_date)"
        base_query += " ORDER BY c.catchment_name, YEAR(pd.measurement_date), MONTH(pd.measurement_date)"
        
        analysis = db.execute_query(base_query, tuple(params) if params else None)
        
        return jsonify({'failure_analysis': analysis})
        
    except Exception as e:
        logger.error(f"Failed to get failure analysis: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sources', methods=['GET'])
def get_data_sources():
    """Get list of uploaded data sources"""
    try:
        query = """
        SELECT source_id, file_name, category, subcatchment, upload_date, file_size_kb, total_records,
               date_range_start, date_range_end, processing_status, error_message, updated_at
        FROM dbo.DataSources
        ORDER BY upload_date DESC
        """
        sources = db.execute_query(query)
        return jsonify({'sources': sources}), 200
    except Exception as e:
        logger.error(f"Failed to get data sources: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sources/<int:source_id>', methods=['DELETE'])
def delete_source(source_id):
    """Delete a data source and all associated data"""
    try:
        # Delete in correct order due to foreign key constraints
        queries = [
            "DELETE FROM dbo.PerformanceMetrics WHERE source_id = ?",
            "DELETE FROM dbo.ProcessedData WHERE source_id = ?",
            "DELETE FROM dbo.RawData WHERE source_id = ?",
            "DELETE FROM dbo.DataSources WHERE source_id = ?"
        ]
        
        for query in queries:
            db.execute_query(query, (source_id,), fetch=False)
        
        return jsonify({'status': 'success', 'message': 'Data source deleted successfully'})
        
    except Exception as e:
        logger.error(f"Failed to delete source: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['GET'])
def export_data():
    """Export processed data to Excel"""
    try:
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', 'GWR').upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build query for export
        base_query = f"""
        SELECT pd.measurement_date, c.catchment_name, pd.source_id,
               pd.{parameter.lower()}_original as original_value,
               pd.{parameter.lower()}_zscore as zscore,
               pd.{parameter.lower()}_classification as classification,
               pd.{parameter.lower()}_is_failure as is_failure,
               pd.{parameter.lower()}_severity_level as severity_level
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE pd.{parameter.lower()}_original IS NOT NULL
        """
        
        conditions = []
        params = []
        
        if catchment_name:
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if start_date:
            conditions.append("pd.measurement_date >= ?")
            params.append(start_date)
            
        if end_date:
            conditions.append("pd.measurement_date <= ?")
            params.append(end_date)
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " ORDER BY pd.measurement_date"
        
        data = db.execute_query(base_query, tuple(params) if params else None)
        
        if not data:
            return jsonify({'error': 'No data to export'}), 400
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Get metrics data
        metrics_base_query = """
        SELECT pm.*, c.catchment_name
        FROM dbo.PerformanceMetrics pm
        INNER JOIN dbo.Catchments c ON pm.catchment_id = c.catchment_id
        WHERE pm.parameter_type = ?
        """
        
        metrics_conditions = []
        metrics_params = [parameter]
        
        if catchment_name:
            metrics_conditions.append("c.catchment_name = ?")
            metrics_params.append(catchment_name)
        
        if metrics_conditions:
            metrics_base_query += " AND " + " AND ".join(metrics_conditions)
            
        metrics_data = db.execute_query(metrics_base_query, tuple(metrics_params))
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Data sheet
            df.to_excel(writer, sheet_name='Processed_Data', index=False)
            
            # Metrics sheet
            if metrics_data:
                metrics_df = pd.DataFrame(metrics_data)
                metrics_df.to_excel(writer, sheet_name='Performance_Metrics', index=False)
        
        output.seek(0)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"groundwater_analysis_{parameter}_{timestamp}.xlsx"
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Failed to export data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    """Get threshold configuration"""
    return jsonify({
        'thresholds': config.THRESHOLDS,
        'classifications': {
            'Normal': {'range': '[-0.5, 0.5]', 'color': '#22c55e'},
            'Moderate_Deficit': {'range': '[-1.0, -0.5)', 'color': '#eab308'},
            'Severe_Deficit': {'range': '[-1.5, -1.0)', 'color': '#f97316'},
            'Extreme_Deficit': {'range': '< -1.5', 'color': '#ef4444'},
            'Surplus': {'range': '> 0.5', 'color': '#3b82f6'}
        }
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {e}")
    return jsonify({'error': 'An unexpected error occurred'}), 500

if __name__ == '__main__':
    logger.info("Starting Groundwater Analysis API Server")
    logger.info(f"Database: {config.SQL_SERVER}/{config.SQL_DATABASE}")
    logger.info(f"Upload folder: {config.UPLOAD_FOLDER}")
    
    # Test database connection on startup
    try:
        db.execute_query("SELECT 1")
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Please check your database configuration and connection string")
    
    app.run(debug=True, host='0.0.0.0', port=5000)