# Groundwater Analysis System Backend API
# Based on Shakhane et al. methodology

from flask import Flask, request, jsonify, send_file
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

app = Flask(__name__)
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
    
    def insert_data_source(self, file_name: str, file_size: int) -> int:
        """Insert new data source record"""
        query = """
        INSERT INTO dbo.DataSources (file_name, file_size_kb, processing_status)
        OUTPUT INSERTED.source_id
        VALUES (?, ?, 'Processing')
        """
        result = self.execute_query(query, (file_name, file_size), fetch=True)
        return result[0]['source_id'] if result else None
    
    def update_data_source_status(self, source_id: int, status: str, error_message: str = None, 
                                  total_records: int = None, date_range: tuple = None):
        """Update data source processing status"""
        query = """
        UPDATE dbo.DataSources 
        SET processing_status = ?, error_message = ?, total_records = ?,
            date_range_start = ?, date_range_end = ?, updated_at = GETDATE()
        WHERE source_id = ?
        """
        start_date, end_date = date_range if date_range else (None, None)
        self.execute_query(query, (status, error_message, total_records, start_date, end_date, source_id), fetch=False)
    
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

class GroundwaterAnalyzer:
    """Implements Shakhane et al. groundwater analysis methodology"""
    
    @staticmethod
    def calculate_zscore(values: np.array) -> tuple:
        """
        Calculate Z-score normalization (Equation 3 from paper)
        Z = (p - p̄) / σ
        """
        mean_val = np.nanmean(values)
        std_val = np.nanstd(values, ddof=1)  # Sample standard deviation
        
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
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'database': 'disconnected',
            'error': str(e)
        }), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload and process Excel file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'Only Excel files (.xlsx, .xls) are supported'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Get file size
        file_size_kb = os.path.getsize(filepath) // 1024
        
        # Create data source record
        source_id = db.insert_data_source(filename, file_size_kb)
        if not source_id:
            return jsonify({'error': 'Failed to create data source record'}), 500
        
        # Process the Excel file
        try:
            # Read Excel file
            df = pd.read_excel(filepath)
            logger.info(f"Read Excel file with {len(df)} rows and columns: {list(df.columns)}")
            
            # Clean and standardize column names
            df.columns = df.columns.str.strip().str.lower()
            
            # Map common column variations
            column_mapping = {
                'date': ['date', 'measurement_date', 'datetime', 'time'],
                'catchment': ['catchment', 'catchment_name', 'site', 'location'],
                'gwr': ['gwr', 'recharge', 'groundwater_recharge', 'gwrecharge'],
                'gwl': ['gwl', 'level', 'groundwater_level', 'water_level', 'gwlevel'],
                'gwb': ['gwb', 'baseflow', 'groundwater_baseflow', 'discharge', 'gwbaseflow']
            }
            
            # Find and rename columns
            standardized_columns = {}
            for standard, variations in column_mapping.items():
                for col in df.columns:
                    if col in variations:
                        standardized_columns[col] = standard
                        break
            
            df = df.rename(columns=standardized_columns)
            
            # Validate required columns
            required_cols = ['date', 'catchment']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            # Convert date column
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            
            # Ensure at least one parameter column exists
            param_cols = [col for col in ['gwr', 'gwl', 'gwb'] if col in df.columns]
            if not param_cols:
                raise ValueError("No groundwater parameter columns found (GWR, GWL, or GWB)")
            
            # Convert numeric columns
            for col in param_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Remove rows with all NaN parameters
            df = df.dropna(subset=param_cols, how='all')
            
            if df.empty:
                raise ValueError("No valid data rows after cleaning")
            
            # Insert raw data
            raw_data_inserted = 0
            processed_data_inserted = 0
            
            for _, row in df.iterrows():
                try:
                    # Get or create catchment
                    catchment_id = db.get_catchment_id(row['catchment'])
                    
                    # Insert raw data
                    raw_query = """
                    INSERT INTO dbo.RawData 
                    (source_id, catchment_id, measurement_date, gwr_mm, gwl_m, gwb_m3s)
                    OUTPUT INSERTED.raw_id
                    VALUES (?, ?, ?, ?, ?, ?)
                    """
                    
                    raw_result = db.execute_query(
                        raw_query,
                        (source_id, catchment_id, row['date'].date(),
                         row.get('gwr'), row.get('gwl'), row.get('gwb')),
                        fetch=True
                    )
                    
                    if raw_result:
                        raw_data_inserted += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to insert row: {e}")
                    continue
            
            # Process data by catchment for normalization
            catchments = df['catchment'].unique()
            
            for catchment_name in catchments:
                catchment_data = df[df['catchment'] == catchment_name].copy()
                catchment_id = db.get_catchment_id(catchment_name)
                
                # Calculate statistics and z-scores for each parameter
                for param in param_cols:
                    if param not in catchment_data.columns:
                        continue
                        
                    values = catchment_data[param].dropna().values
                    if len(values) == 0:
                        continue
                    
                    z_scores, mean_val, std_val = analyzer.calculate_zscore(values)
                    
                    # Update catchment_data with z-scores and classifications
                    param_idx = catchment_data[param].notna()
                    catchment_data.loc[param_idx, f'{param}_zscore'] = z_scores
                    catchment_data.loc[param_idx, f'{param}_mean'] = mean_val
                    catchment_data.loc[param_idx, f'{param}_stddev'] = std_val
                    
                    # Apply classifications
                    for idx, z_score in zip(catchment_data.index[param_idx], z_scores):
                        classification = analyzer.classify_threshold(z_score)
                        catchment_data.loc[idx, f'{param}_classification'] = classification['level']
                        catchment_data.loc[idx, f'{param}_is_failure'] = classification['is_failure']
                        catchment_data.loc[idx, f'{param}_severity'] = classification['severity']
                
                # Insert processed data
                for _, row in catchment_data.iterrows():
                    try:
                        processed_query = """
                        INSERT INTO dbo.ProcessedData 
                        (source_id, catchment_id, measurement_date, 
                         gwr_original, gwl_original, gwb_original,
                         gwr_mean, gwr_stddev, gwl_mean, gwl_stddev, gwb_mean, gwb_stddev,
                         gwr_zscore, gwl_zscore, gwb_zscore,
                         gwr_classification, gwl_classification, gwb_classification,
                         gwr_is_failure, gwl_is_failure, gwb_is_failure,
                         gwr_severity_level, gwl_severity_level, gwb_severity_level)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                        
                        db.execute_query(
                            processed_query,
                            (source_id, catchment_id, row['date'].date(),
                             row.get('gwr'), row.get('gwl'), row.get('gwb'),
                             row.get('gwr_mean'), row.get('gwr_stddev'),
                             row.get('gwl_mean'), row.get('gwl_stddev'),
                             row.get('gwb_mean'), row.get('gwb_stddev'),
                             row.get('gwr_zscore'), row.get('gwl_zscore'), row.get('gwb_zscore'),
                             row.get('gwr_classification'), row.get('gwl_classification'), row.get('gwb_classification'),
                             row.get('gwr_is_failure'), row.get('gwl_is_failure'), row.get('gwb_is_failure'),
                             row.get('gwr_severity'), row.get('gwl_severity'), row.get('gwb_severity')),
                            fetch=False
                        )
                        processed_data_inserted += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to insert processed row: {e}")
                        continue
            
            # Calculate and store performance metrics
            for catchment_name in catchments:
                catchment_id = db.get_catchment_id(catchment_name)
                catchment_data = df[df['catchment'] == catchment_name]
                
                date_range = (catchment_data['date'].min().date(), catchment_data['date'].max().date())
                
                for param in param_cols:
                    if param not in catchment_data.columns:
                        continue
                        
                    param_data = catchment_data[param].dropna()
                    if len(param_data) == 0:
                        continue
                    
                    z_scores, _, _ = analyzer.calculate_zscore(param_data.values)
                    is_failure = np.array([analyzer.classify_threshold(z)['is_failure'] for z in z_scores])
                    
                    metrics = analyzer.calculate_performance_metrics(z_scores, is_failure)
                    
                    # Insert performance metrics
                    metrics_query = """
                    INSERT INTO dbo.PerformanceMetrics 
                    (source_id, catchment_id, parameter_type, analysis_start_date, analysis_end_date,
                     total_records, reliability, resilience, vulnerability, sustainability,
                     total_failures, failure_sequences, avg_failure_duration, max_failure_duration,
                     avg_failure_severity, max_failure_severity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    db.execute_query(
                        metrics_query,
                        (source_id, catchment_id, param.upper(), date_range[0], date_range[1],
                         len(param_data), metrics['reliability'], metrics['resilience'],
                         metrics['vulnerability'], metrics['sustainability'],
                         metrics['total_failures'], metrics['failure_sequences'],
                         metrics['avg_failure_duration'], metrics['max_failure_duration'],
                         metrics['avg_failure_severity'], metrics['max_failure_severity']),
                        fetch=False
                    )
            
            # Update data source status
            db.update_data_source_status(
                source_id, 'Completed', None, processed_data_inserted, 
                (df['date'].min().date(), df['date'].max().date())
            )
            
            logger.info(f"Processing completed: {processed_data_inserted} records processed")
            
            return jsonify({
                'status': 'success',
                'source_id': source_id,
                'filename': filename,
                'raw_records': raw_data_inserted,
                'processed_records': processed_data_inserted,
                'catchments': len(catchments),
                'parameters': param_cols,
                'date_range': {
                    'start': df['date'].min().isoformat(),
                    'end': df['date'].max().isoformat()
                }
            })
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            
            db.update_data_source_status(source_id, 'Failed', error_msg)
            
            # Clean up file on error
            if os.path.exists(filepath):
                os.remove(filepath)
                
            return jsonify({'error': error_msg}), 500
    
    except Exception as e:
        logger.error(f"Upload failed: {e}")
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
    """Get processed data with filters"""
    try:
        # Parse query parameters
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', 'GWR').upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        source_id = request.args.get('source_id')
        
        # Build query
        query = """
        SELECT pd.measurement_date, c.catchment_name, pd.source_id,
               CASE 
                   WHEN ? = 'GWR' THEN pd.gwr_original
                   WHEN ? = 'GWL' THEN pd.gwl_original  
                   WHEN ? = 'GWB' THEN pd.gwb_original
               END as original_value,
               CASE 
                   WHEN ? = 'GWR' THEN pd.gwr_zscore
                   WHEN ? = 'GWL' THEN pd.gwl_zscore
                   WHEN ? = 'GWB' THEN pd.gwb_zscore
               END as zscore,
               CASE 
                   WHEN ? = 'GWR' THEN pd.gwr_classification
                   WHEN ? = 'GWL' THEN pd.gwl_classification
                   WHEN ? = 'GWB' THEN pd.gwb_classification
               END as classification,
               CASE 
                   WHEN ? = 'GWR' THEN pd.gwr_is_failure
                   WHEN ? = 'GWL' THEN pd.gwl_is_failure
                   WHEN ? = 'GWB' THEN pd.gwb_is_failure
               END as is_failure,
               CASE 
                   WHEN ? = 'GWR' THEN pd.gwr_severity_level
                   WHEN ? = 'GWL' THEN pd.gwl_severity_level
                   WHEN ? = 'GWB' THEN pd.gwb_severity_level
               END as severity_level
        FROM dbo.ProcessedData pd
        INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
        WHERE 1=1
        """
        
        params = [parameter] * 12  # Parameter repeated for each CASE statement
        
        if catchment_name:
            query += " AND c.catchment_name = ?"
            params.append(catchment_name)
            
        if start_date:
            query += " AND pd.measurement_date >= ?"
            params.append(start_date)
            
        if end_date:
            query += " AND pd.measurement_date <= ?"
            params.append(end_date)
            
        if source_id:
            query += " AND pd.source_id = ?"
            params.append(int(source_id))
        
        query += " ORDER BY pd.measurement_date"
        
        data = db.execute_query(query, tuple(params))
        
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

@app.route('/api/metrics', methods=['GET'])
def get_performance_metrics():
    """Get performance metrics with filters"""
    try:
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', 'GWR').upper()
        source_id = request.args.get('source_id')
        
        query = """
        SELECT pm.*, c.catchment_name
        FROM dbo.PerformanceMetrics pm
        INNER JOIN dbo.Catchments c ON pm.catchment_id = c.catchment_id
        WHERE pm.parameter_type = ?
        """
        
        params = [parameter]
        
        if catchment_name:
            query += " AND c.catchment_name = ?"
            params.append(catchment_name)
            
        if source_id:
            query += " AND pm.source_id = ?"
            params.append(int(source_id))
        
        query += " ORDER BY c.catchment_name, pm.analysis_start_date"
        
        metrics = db.execute_query(query, tuple(params))
        
        return jsonify({
            'metrics': metrics,
            'parameter': parameter
        })
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/failure-analysis', methods=['GET'])
def get_failure_analysis():
    """Get failure analysis summary"""
    try:
        catchment_name = request.args.get('catchment')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = """
        SELECT * FROM vw_FailureAnalysis
        WHERE 1=1
        """
        
        params = []
        
        if catchment_name:
            query += " AND catchment_name = ?"
            params.append(catchment_name)
            
        # Add date filtering if needed
        if start_date and end_date:
            query += " AND DATEFROMPARTS(year, month, 1) BETWEEN ? AND ?"
            params.extend([start_date, end_date])
        
        query += " ORDER BY catchment_name, year, month"
        
        analysis = db.execute_query(query, tuple(params))
        
        return jsonify({'failure_analysis': analysis})
        
    except Exception as e:
        logger.error(f"Failed to get failure analysis: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sources', methods=['GET'])
def get_data_sources():
    """Get list of uploaded data sources"""
    try:
        query = """
        SELECT ds.*, 
               COUNT(DISTINCT pd.catchment_id) as catchments_count,
               COUNT(pd.processed_id) as processed_records
        FROM dbo.DataSources ds
        LEFT JOIN dbo.ProcessedData pd ON ds.source_id = pd.source_id
        GROUP BY ds.source_id, ds.file_name, ds.upload_date, ds.file_size_kb, 
                 ds.total_records, ds.date_range_start, ds.date_range_end, 
                 ds.processing_status, ds.error_message, ds.created_at, ds.updated_at
        ORDER BY ds.upload_date DESC
        """
        
        sources = db.execute_query(query)
        return jsonify({'sources': sources})
        
    except Exception as e:
        logger.error(f"Failed to get data sources: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['GET'])
def export_data():
    """Export processed data to Excel"""
    try:
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', 'GWR').upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get data
        data_response = get_data()
        if data_response.status_code != 200:
            return data_response
            
        data = json.loads(data_response.data)['data']
        
        if not data:
            return jsonify({'error': 'No data to export'}), 400
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Data sheet
            df.to_excel(writer, sheet_name='Processed_Data', index=False)
            
            # Get and add metrics sheet
            metrics_response = get_performance_metrics()
            if metrics_response.status_code == 200:
                metrics_data = json.loads(metrics_response.data)['metrics']
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

if __name__ == '__main__':
    logger.info("Starting Groundwater Analysis API Server")
    logger.info(f"Database: {config.SQL_SERVER}/{config.SQL_DATABASE}")
    logger.info(f"Upload folder: {config.UPLOAD_FOLDER}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)