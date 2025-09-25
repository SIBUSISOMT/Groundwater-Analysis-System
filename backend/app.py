# AI-Enhanced Groundwater Analysis System Backend API
# Complete implementation with advanced AI capabilities
# Ready for production - works with existing database

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
from typing import Dict, List, Tuple, Optional, Any
import io
import json
import asyncio
from dataclasses import dataclass, asdict

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('groundwater_analysis.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Try to import OpenAI - optional dependency
try:
    import openai
    OPENAI_AVAILABLE = True
    logger.info("OpenAI library imported successfully")
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI library not installed - AI features will be limited to rule-based responses")

# Initialize Flask app
app = Flask(__name__, 
           template_folder='../frontend',
           static_folder='../frontend')
CORS(app)

# Configuration
class Config:
    SQL_SERVER = os.getenv('SQL_SERVER', 'localhost')
    SQL_DATABASE = os.getenv('SQL_DATABASE', 'GroundwaterAnalysis') 
    SQL_USERNAME = os.getenv('SQL_USERNAME', '')
    SQL_PASSWORD = os.getenv('SQL_PASSWORD', '')
    
    # Add missing attributes for app.run()
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    API_HOST = os.getenv('API_HOST', '127.0.0.1')
    API_PORT = int(os.getenv('API_PORT', '5000'))
    
    UPLOAD_FOLDER = 'uploads'
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', None)
    AI_ENABLED = bool(os.getenv('OPENAI_API_KEY', None))
    
    # Shakhane et al. thresholds (EXACT from study)
    THRESHOLDS = {
        'normal_upper': 0.5,
        'normal_lower': -0.5,
        'moderate_lower': -1.0,
        'severe_lower': -1.5,
        'extreme_lower': -2.0
    }

config = Config()
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

@dataclass
class AIInsight:
    category: str
    confidence: float
    message: str
    recommendation: str
    data_context: Dict

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self):
        self.connection_string = self._build_connection_string()
    
    def _build_connection_string(self):
        if Config.SQL_USERNAME:
            return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={Config.SQL_SERVER};DATABASE={Config.SQL_DATABASE};UID={Config.SQL_USERNAME};PWD={Config.SQL_PASSWORD}"
        else:
            return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={Config.SQL_SERVER};DATABASE={Config.SQL_DATABASE};Trusted_Connection=yes;"
    
    def get_connection(self):
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True):
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
        query = """
        INSERT INTO dbo.DataSources (file_name, file_size_kb, processing_status, category, subcatchment)
        OUTPUT INSERTED.source_id
        VALUES (?, ?, 'Processing', ?, ?)
        """
        result = self.execute_query(query, (file_name, file_size, category, subcatchment), fetch=True)
        return result[0]['source_id'] if result else None
    
    def update_data_source_status(self, source_id: int, status: str, error_message: str = None, 
                                  total_records: int = None, date_range: tuple = None):
        query = """
        UPDATE dbo.DataSources 
        SET processing_status = ?, error_message = ?, total_records = ?,
            date_range_start = ?, date_range_end = ?, updated_at = GETDATE()
        WHERE source_id = ?
        """
        
        start_date_str = None
        end_date_str = None
        if date_range:
            start_date_str, end_date_str = date_range
        
        self.execute_query(query, (status, error_message, total_records, start_date_str, end_date_str, source_id), fetch=False)
    
    def get_catchment_id(self, catchment_name: str) -> Optional[int]:
        query = "SELECT catchment_id FROM dbo.Catchments WHERE catchment_name = ?"
        result = self.execute_query(query, (catchment_name,))
        
        if result:
            return result[0]['catchment_id']
        else:
            insert_query = """
            INSERT INTO dbo.Catchments (catchment_name) 
            OUTPUT INSERTED.catchment_id
            VALUES (?)
            """
            result = self.execute_query(insert_query, (catchment_name,), fetch=True)
            return result[0]['catchment_id'] if result else None

    def insert_raw_data(self, values: dict):
        query = """
        INSERT INTO dbo.RawData (
            source_id, catchment_id, measurement_date, category,
            recharge_inches, recharge_converted, average_recharge, recharge_stdev, drought_index_recharge,
            baseflow_value, average_baseflow, baseflow_stdev, standardized_baseflow,
            gw_level, average_gw_level, gw_level_stdev, standardized_gw_level,
            original_sheet_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        params = (
            values.get('source_id'), values.get('catchment_id'), values.get('measurement_date'),
            values.get('category'), values.get('recharge_inches'), values.get('recharge_converted'),
            values.get('average_recharge'), values.get('recharge_stdev'), values.get('drought_index_recharge'),
            values.get('baseflow_value'), values.get('average_baseflow'), values.get('baseflow_stdev'),
            values.get('standardized_baseflow'), values.get('gw_level'), values.get('average_gw_level'),
            values.get('gw_level_stdev'), values.get('standardized_gw_level'), values.get('original_sheet_name')
        )
        
        self.execute_query(query, params, fetch=False)

class GroundwaterAnalyzer:
    """Shakhane et al. methodology implementation"""
    
    @staticmethod
    def calculate_zscore(values: np.array) -> tuple:
        clean_values = values[~np.isnan(values)]
        if len(clean_values) == 0:
            return np.zeros_like(values), 0, 0
        
        mean_val = np.mean(clean_values)
        std_val = np.std(clean_values, ddof=1)
        
        if std_val == 0:
            z_scores = np.zeros_like(values)
        else:
            z_scores = (values - mean_val) / std_val
        
        return z_scores, mean_val, std_val
    
    @staticmethod
    def classify_threshold(z_score: float) -> dict:
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

class AIAssistant:
    """AI Assistant for groundwater analysis"""
    
    def __init__(self, db_manager, openai_api_key: str = None):
        self.db = db_manager
        self.ai_enabled = bool(openai_api_key)
        if openai_api_key and OPENAI_AVAILABLE:
            try:
                import openai
                openai.api_key = openai_api_key
            except ImportError:
                logger.warning("OpenAI not installed - AI features limited")
                self.ai_enabled = False
        
        self.methodology_knowledge = {
            "zscore_formula": {
                "equation": "Z = (X - μ) / σ",
                "description": "Z-score normalization where X is observed value, μ is mean, σ is standard deviation",
                "purpose": "Standardizes values to identify deviations from normal conditions"
            },
            "reliability": {
                "equation": "R = (T - F) / T",
                "description": "Reliability is ratio of satisfactory to total periods",
                "interpretation": "Values closer to 1.0 indicate better reliability"
            },
            "resilience": {
                "equation": "γ = (1/ρ * Σα(j))^-1",
                "description": "Resilience measures recovery speed from failures",
                "interpretation": "Higher values indicate faster recovery"
            },
            "vulnerability": {
                "equation": "V = E[S|F] / max(S)",
                "description": "Vulnerability is average failure severity normalized by maximum",
                "interpretation": "Lower values indicate less severe impacts"
            },
            "sustainability": {
                "equation": "S = R × γ × (1 - V)",
                "description": "Sustainability combines reliability, resilience, and vulnerability",
                "interpretation": "Higher values indicate better overall performance"
            }
        }
    
    def analyze_upload_data(self, df: pd.DataFrame, category: str, subcatchment: str) -> Dict:
        try:
            insights = {
                "data_quality": self._assess_data_quality(df),
                "column_analysis": self._analyze_columns(df, category),
                "temporal_analysis": self._analyze_temporal_coverage(df),
                "recommendations": []
            }
            
            quality_score = insights["data_quality"]["quality_score"]
            if quality_score == "Poor":
                insights["recommendations"].append("Data quality is poor - review missing values and duplicates")
            elif quality_score == "Fair":
                insights["recommendations"].append("Data quality is fair - consider addressing missing values")
            
            missing_cols = insights["column_analysis"]["missing_columns"]
            if missing_cols:
                insights["recommendations"].append(f"Missing required columns: {missing_cols}")
            
            return insights
            
        except Exception as e:
            logger.error(f"Upload analysis failed: {e}")
            return {"error": str(e), "recommendations": ["Please check data format and try again"]}
    
    def _assess_data_quality(self, df: pd.DataFrame) -> Dict:
        total_rows = len(df)
        
        quality_metrics = {
            "total_rows": total_rows,
            "total_columns": len(df.columns),
            "missing_data_percentage": (df.isnull().sum().sum() / (total_rows * len(df.columns))) * 100 if total_rows > 0 else 0,
            "duplicate_rows": df.duplicated().sum(),
            "empty_rows": (df.isnull().all(axis=1)).sum()
        }
        
        if quality_metrics["missing_data_percentage"] > 50:
            quality_metrics["quality_score"] = "Poor"
        elif quality_metrics["missing_data_percentage"] > 20:
            quality_metrics["quality_score"] = "Fair"
        else:
            quality_metrics["quality_score"] = "Good"
        
        return quality_metrics
    
    def _analyze_columns(self, df: pd.DataFrame, category: str) -> Dict:
        df_columns_lower = [col.lower().strip() for col in df.columns]
        
        expected_columns = {
            "recharge": ['date', 'recharge (inches)', 'recharge', 'average recharge', 'stdev', 'drought index - recharge'],
            "baseflow": ['date', 'baseflow', 'average baseflow', 'stdev', 'standardized baseflow'],
            "gwlevel": ['date', 'gw level', 'average gw level', 'stdev', 'standardized gw level']
        }
        
        expected = expected_columns.get(category.lower(), [])
        
        return {
            "detected_columns": list(df.columns),
            "expected_columns": expected,
            "missing_columns": [col for col in expected if col not in df_columns_lower]
        }
    
    def _analyze_temporal_coverage(self, df: pd.DataFrame) -> Dict:
        temporal_analysis = {"has_date_column": False}
        
        date_columns = [col for col in df.columns if 'date' in col.lower()]
        
        if date_columns:
            temporal_analysis["has_date_column"] = True
            date_col = date_columns[0]
            
            try:
                df_temp = df.copy()
                df_temp[date_col] = pd.to_datetime(df_temp[date_col], errors='coerce')
                valid_dates = df_temp[date_col].dropna()
                
                if len(valid_dates) > 0:
                    temporal_analysis.update({
                        "date_range_start": valid_dates.min().strftime('%Y-%m-%d'),
                        "date_range_end": valid_dates.max().strftime('%Y-%m-%d'),
                        "total_time_points": len(valid_dates)
                    })
            except Exception as e:
                temporal_analysis["date_parsing_error"] = str(e)
        
        return temporal_analysis
    
    def analyze_processed_data(self, data: List[Dict], filters: Dict) -> Dict:
        try:
            if not data:
                return {"message": "No data available for analysis"}
            
            df = pd.DataFrame(data)
            
            failure_patterns = {}
            if 'classification' in df.columns:
                classification_counts = df['classification'].value_counts().to_dict()
                total_records = len(df)
                
                failure_classifications = ['Moderate_Deficit', 'Severe_Deficit', 'Extreme_Deficit']
                total_failures = sum(classification_counts.get(cls, 0) for cls in failure_classifications)
                
                failure_patterns = {
                    "total_failures": total_failures,
                    "failure_rate": (total_failures / total_records) * 100 if total_records > 0 else 0,
                    "classification_distribution": classification_counts
                }
            
            insights = []
            recommendations = []
            
            if failure_patterns.get('failure_rate', 0) > 40:
                insights.append(AIInsight(
                    category="critical",
                    confidence=0.9,
                    message=f"High failure rate detected ({failure_patterns['failure_rate']:.1f}%). System shows significant stress.",
                    recommendation="Implement emergency water management protocols immediately.",
                    data_context={"failure_rate": failure_patterns['failure_rate']}
                ))
            elif failure_patterns.get('failure_rate', 0) > 20:
                insights.append(AIInsight(
                    category="warning",
                    confidence=0.8,
                    message=f"Moderate failure rate ({failure_patterns['failure_rate']:.1f}%) indicates potential stress.",
                    recommendation="Monitor trends and prepare contingency plans.",
                    data_context={"failure_rate": failure_patterns['failure_rate']}
                ))
            
            if failure_patterns.get('failure_rate', 0) > 25:
                recommendations.append("High failure rate suggests need for adaptive management strategies")
            
            return {
                "failure_patterns": failure_patterns,
                "insights": [{"category": i.category, "message": i.message, "recommendation": i.recommendation} for i in insights],
                "recommendations": recommendations
            }
            
        except Exception as e:
            logger.error(f"Data analysis failed: {e}")
            return {"error": str(e)}
    
    def handle_chat_message(self, message: str, context: Dict = None) -> Dict[str, str]:
        try:
            message = message.strip().lower()
            
            # Methodology questions
            if any(term in message for term in ['z-score', 'zscore', 'formula']):
                formula_info = self.methodology_knowledge["zscore_formula"]
                return {
                    "content": f"The Z-score formula is: {formula_info['equation']}. {formula_info['description']}. {formula_info['purpose']}.",
                    "type": "methodology"
                }
            
            if 'reliability' in message:
                rel_info = self.methodology_knowledge["reliability"]
                return {
                    "content": f"Reliability: {rel_info['equation']}. {rel_info['description']}. {rel_info['interpretation']}.",
                    "type": "methodology"
                }
            
            if 'resilience' in message:
                res_info = self.methodology_knowledge["resilience"]
                return {
                    "content": f"Resilience: {res_info['equation']}. {res_info['description']}. {res_info['interpretation']}.",
                    "type": "methodology"
                }
            
            if 'vulnerability' in message:
                vul_info = self.methodology_knowledge["vulnerability"]
                return {
                    "content": f"Vulnerability: {vul_info['equation']}. {vul_info['description']}. {vul_info['interpretation']}.",
                    "type": "methodology"
                }
            
            if 'sustainability' in message:
                sus_info = self.methodology_knowledge["sustainability"]
                return {
                    "content": f"Sustainability: {sus_info['equation']}. {sus_info['description']}. {sus_info['interpretation']}.",
                    "type": "methodology"
                }
            
            # General help
            if any(term in message for term in ['upload', 'file', 'data']):
                return {
                    "content": "To upload data: 1) Select category and subcatchment, 2) Upload Excel file with required columns. The system validates data automatically.",
                    "type": "help"
                }
            
            if any(term in message for term in ['help', 'features']):
                return {
                    "content": "I can help with methodology explanations, data interpretation, upload guidance, and troubleshooting. What specific aspect interests you?",
                    "type": "help"
                }
            
            return {
                "content": "I can help you understand the groundwater analysis system. Ask me about methodology, formulas, data interpretation, or system functionality.",
                "type": "info"
            }
                
        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            return {
                "content": "I encountered an error. Please try rephrasing your question.",
                "type": "error"
            }

# Initialize components
db = DatabaseManager()
analyzer = GroundwaterAnalyzer()
ai_assistant = AIAssistant(db, config.OPENAI_API_KEY)

# ROUTES

@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"<h1>AI-Enhanced Groundwater Analysis System</h1><p>Error: {e}</p>"

@app.route('/<path:filename>')
def serve_static_files(filename):
    try:
        return send_from_directory('../frontend', filename)
    except Exception as e:
        return f"File not found: {filename}", 404

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        db.execute_query("SELECT 1 as test")
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected',
            'ai_enabled': ai_assistant.ai_enabled,
            'features': {
                'data_upload': True,
                'ai_analysis': True,
                'chat_assistant': True,
                'methodology_help': True
            }
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'database': 'disconnected',
            'error': str(e)
        }), 500

@app.route('/api/sources', methods=['GET'])
def get_data_sources():
    try:
        query = """
        SELECT source_id, file_name, category, subcatchment, upload_date, 
               file_size_kb, total_records, date_range_start, date_range_end, 
               processing_status, error_message, updated_at
        FROM dbo.DataSources
        ORDER BY upload_date DESC
        """
        sources = db.execute_query(query)
        
        # Convert dates to strings for JSON serialization
        for source in sources:
            if source.get('upload_date'):
                source['upload_date'] = source['upload_date'].isoformat() if hasattr(source['upload_date'], 'isoformat') else str(source['upload_date'])
            if source.get('updated_at'):
                source['updated_at'] = source['updated_at'].isoformat() if hasattr(source['updated_at'], 'isoformat') else str(source['updated_at'])
        
        return jsonify({'sources': sources}), 200
    except Exception as e:
        logger.error(f"Failed to get data sources: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    """Get threshold configuration"""
    return jsonify({
        'thresholds': Config.THRESHOLDS,
        'classifications': {
            'Normal': {'range': '[-0.5, 0.5]', 'color': '#22c55e'},
            'Moderate_Deficit': {'range': '[-1.0, -0.5)', 'color': '#eab308'},
            'Severe_Deficit': {'range': '[-1.5, -1.0)', 'color': '#f97316'},
            'Extreme_Deficit': {'range': '< -1.5', 'color': '#ef4444'},
            'Surplus': {'range': '> 0.5', 'color': '#3b82f6'}
        }
    })

@app.route('/api/catchments', methods=['GET'])
def get_catchments():
    try:
        query = """
        SELECT c.catchment_id, c.catchment_name, c.catchment_code, c.area_km2,
               COUNT(DISTINCT rd.source_id) as datasets,
               MIN(rd.measurement_date) as earliest_date,
               MAX(rd.measurement_date) as latest_date,
               COUNT(rd.raw_id) as total_records
        FROM dbo.Catchments c
        LEFT JOIN dbo.RawData rd ON c.catchment_id = rd.catchment_id
        GROUP BY c.catchment_id, c.catchment_name, c.catchment_code, c.area_km2
        ORDER BY c.catchment_name
        """
        catchments = db.execute_query(query)
        
        # Convert dates to strings
        for catchment in catchments:
            if catchment.get('earliest_date'):
                catchment['earliest_date'] = catchment['earliest_date'].strftime('%Y-%m-%d') if hasattr(catchment['earliest_date'], 'strftime') else str(catchment['earliest_date'])
            if catchment.get('latest_date'):
                catchment['latest_date'] = catchment['latest_date'].strftime('%Y-%m-%d') if hasattr(catchment['latest_date'], 'strftime') else str(catchment['latest_date'])
        
        return jsonify({'catchments': catchments})
    except Exception as e:
        logger.error(f"Failed to get catchments: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data', methods=['GET'])
def get_data():
    try:
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', '').upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        source_id = request.args.get('source_id')
        
        parameter_mapping = {
            'GWL': 'gwlevel',
            'GWLEVEL': 'gwlevel',
            'RECHARGE': 'recharge', 
            'BASEFLOW': 'baseflow'
        }
        
        db_category = parameter_mapping.get(parameter, 'recharge')
        
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
        WHERE rd.category = ?
        """
        
        conditions = []
        params = [db_category]
        
        if catchment_name and catchment_name.upper() != 'ALL':
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if start_date:
            conditions.append("rd.measurement_date >= ?")
            params.append(start_date)
                
        if end_date:
            conditions.append("rd.measurement_date <= ?")
            params.append(end_date)
            
        if source_id:
            conditions.append("rd.source_id = ?")
            params.append(int(source_id))
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " ORDER BY rd.measurement_date DESC"
        
        limit = min(int(request.args.get('limit', 1000)), 10000)
        base_query += f" OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
        
        data = db.execute_query(base_query, tuple(params))
        
        if not data:
            return jsonify({
                'data': [],
                'message': 'No data found for the specified filters',
                'filters_applied': {
                    'catchment': catchment_name,
                    'parameter': parameter,
                    'db_category': db_category
                }
            }), 200
        
        # Format data
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
            
            # Add classification
            if formatted_row['zscore'] is not None:
                classification = analyzer.classify_threshold(formatted_row['zscore'])
                formatted_row.update({
                    'classification': classification['level'],
                    'is_failure': classification['is_failure'],
                    'severity_level': classification['severity']
                })
            
            formatted_data.append(formatted_row)
        
        return jsonify({
            'data': formatted_data,
            'count': len(formatted_data),
            'parameter': parameter,
            'db_category': db_category
        }), 200
            
    except Exception as e:
        logger.error(f"Data API error: {e}")
        return jsonify({
            'error': 'Failed to retrieve data',
            'details': str(e)
        }), 500

@app.route('/api/failure-analysis', methods=['GET'])
def get_failure_analysis():
    try:
        catchment_name = request.args.get('catchment')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        base_query = """
        SELECT 
            c.catchment_name,
            YEAR(rd.measurement_date) as year,
            MONTH(rd.measurement_date) as month,
            COUNT(*) as total_records,
            SUM(CASE WHEN rd.category = 'recharge' AND rd.drought_index_recharge < -0.5 THEN 1 ELSE 0 END) as gwr_failures,
            SUM(CASE WHEN rd.category = 'gwlevel' AND rd.standardized_gw_level < -0.5 THEN 1 ELSE 0 END) as gwl_failures,
            SUM(CASE WHEN rd.category = 'baseflow' AND rd.standardized_baseflow < -0.5 THEN 1 ELSE 0 END) as gwb_failures
        FROM dbo.RawData rd
        INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
        WHERE 1=1
        """
        
        conditions = []
        params = []
        
        if catchment_name:
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if start_date:
            conditions.append("rd.measurement_date >= ?")
            params.append(start_date)
            
        if end_date:
            conditions.append("rd.measurement_date <= ?")
            params.append(end_date)
            
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
            
        base_query += " GROUP BY c.catchment_name, YEAR(rd.measurement_date), MONTH(rd.measurement_date)"
        base_query += " ORDER BY c.catchment_name, YEAR(rd.measurement_date), MONTH(rd.measurement_date)"
        
        analysis = db.execute_query(base_query, tuple(params) if params else None)
        
        return jsonify({'failure_analysis': analysis})
        
    except Exception as e:
        logger.error(f"Failed to get failure analysis: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        category = request.form.get('category')
        subcatchment = request.form.get('subcatchment')

        if not file or not category or not subcatchment:
            return jsonify({'error': 'File, category, and subcatchment are required.'}), 400

        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'Please select an Excel file (.xlsx or .xls)'}), 400

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)
        file_size_kb = os.path.getsize(filepath) // 1024

        # Check file size against config
        if os.path.getsize(filepath) > Config.MAX_FILE_SIZE:
            os.remove(filepath)  # Clean up
            return jsonify({'error': f'File size exceeds maximum allowed size of {Config.MAX_FILE_SIZE // (1024*1024)}MB'}), 400

        # AI Pre-analysis
        ai_insights = {}
        try:
            df = pd.read_excel(filepath)
            ai_insights = ai_assistant.analyze_upload_data(df, category, subcatchment)
        except Exception as ai_error:
            logger.warning(f"AI pre-analysis failed: {ai_error}")
            ai_insights = {'error': 'AI analysis unavailable', 'recommendations': []}

        # Create data source record
        source_id = db.insert_data_source(filename, file_size_kb, category, subcatchment)
        if not source_id:
            return jsonify({'error': 'Failed to create data source record'}), 500

        # Process Excel file
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
            
            return jsonify({
                'error': error_msg,
                'ai_help': {
                    'missing_columns': missing,
                    'suggestions': f"Please ensure your Excel file has these exact column names: {required}",
                    'ask_ai': 'Use the chat assistant for column mapping help'
                }
            }), 400

        # Process records
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
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                raw_date = row['date']
                
                # Skip rows with empty/null dates
                if pd.isna(raw_date) or raw_date == '' or raw_date is None:
                    continue
                
                # Parse date
                parsed_date = None
                date_str_for_range = None
                
                try:
                    if isinstance(raw_date, (pd.Timestamp, datetime)):
                        parsed_date = raw_date.date()
                        date_str_for_range = raw_date.strftime('%Y-%m-%d')
                    elif isinstance(raw_date, date):
                        parsed_date = raw_date
                        date_str_for_range = raw_date.strftime('%Y-%m-%d')
                    else:
                        # Try to parse as string or number
                        temp_date = pd.to_datetime(raw_date, errors='coerce')
                        if pd.notna(temp_date):
                            parsed_date = temp_date.date()
                            date_str_for_range = temp_date.strftime('%Y-%m-%d')
                        else:
                            continue

                except Exception as date_error:
                    logger.warning(f"Row {idx}: Date parsing error for '{raw_date}': {str(date_error)}")
                    continue

                if not parsed_date:
                    continue

                # Track date range
                if not date_range_start or date_str_for_range < date_range_start:
                    date_range_start = date_str_for_range
                if not date_range_end or date_str_for_range > date_range_end:
                    date_range_end = date_str_for_range

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

                # Prepare values for database
                values = {
                    'source_id': source_id,
                    'catchment_id': catchment_id,
                    'measurement_date': parsed_date,
                    'category': category,
                    'original_sheet_name': subcatchment
                }

                # Category-specific processing
                if category.lower() == 'gwlevel':
                    gw_level = safe_float(row.get('gw level'))
                    avg_gw_level = safe_float(row.get('average gw level'))
                    gw_stdev = safe_float(row.get('stdev'))
                    std_gw_level = safe_float(row.get('standardized gw level'))
                    
                    values.update({
                        'gw_level': gw_level,
                        'average_gw_level': avg_gw_level,
                        'gw_level_stdev': gw_stdev,
                        'standardized_gw_level': std_gw_level,
                        'recharge_inches': None, 'recharge_converted': None, 'average_recharge': None,
                        'recharge_stdev': None, 'drought_index_recharge': None,
                        'baseflow_value': None, 'average_baseflow': None, 'baseflow_stdev': None,
                        'standardized_baseflow': None
                    })
                    
                elif category.lower() == 'recharge':
                    recharge_inches = safe_float(row.get('recharge (inches)'))
                    recharge_converted = safe_float(row.get('recharge'))
                    avg_recharge = safe_float(row.get('average recharge'))
                    recharge_stdev = safe_float(row.get('stdev'))
                    drought_index = safe_float(row.get('drought index - recharge'))
                    
                    values.update({
                        'recharge_inches': recharge_inches, 'recharge_converted': recharge_converted,
                        'average_recharge': avg_recharge, 'recharge_stdev': recharge_stdev,
                        'drought_index_recharge': drought_index,
                        'baseflow_value': None, 'average_baseflow': None, 'baseflow_stdev': None,
                        'standardized_baseflow': None, 'gw_level': None, 'average_gw_level': None,
                        'gw_level_stdev': None, 'standardized_gw_level': None
                    })
                    
                elif category.lower() == 'baseflow':
                    baseflow_val = safe_float(row.get('baseflow'))
                    avg_baseflow = safe_float(row.get('average baseflow'))
                    baseflow_stdev = safe_float(row.get('stdev'))
                    std_baseflow = safe_float(row.get('standardized baseflow'))
                    
                    values.update({
                        'baseflow_value': baseflow_val, 'average_baseflow': avg_baseflow,
                        'baseflow_stdev': baseflow_stdev, 'standardized_baseflow': std_baseflow,
                        'recharge_inches': None, 'recharge_converted': None, 'average_recharge': None,
                        'recharge_stdev': None, 'drought_index_recharge': None,
                        'gw_level': None, 'average_gw_level': None, 'gw_level_stdev': None,
                        'standardized_gw_level': None
                    })
                
                # Insert record
                try:
                    db.insert_raw_data(values)
                    total_inserted += 1
                except Exception as insert_error:
                    error_msg = f"Row {idx}: Insert failed - {str(insert_error)}"
                    errors.append(error_msg)
                    continue
                
            except Exception as row_error:
                error_msg = f"Row {idx}: Processing error - {str(row_error)}"
                errors.append(error_msg)
                continue

        # Update status and return response
        if total_inserted == 0:
            error_summary = f"Failed to process any records. Sample errors: {'; '.join(errors[:3])}"
            db.update_data_source_status(source_id, 'Failed', error_summary, 0, None)
            return jsonify({
                'error': 'Failed to process any records',
                'details': errors[:10],
                'total_errors': len(errors),
                'ai_help': 'Ask the AI assistant about these specific errors for troubleshooting help'
            }), 400
        else:
            if errors:
                error_summary = f"Processed {total_inserted} records with {len(errors)} errors."
                status = 'Completed with Errors'
            else:
                error_summary = None
                status = 'Completed'
                
            db.update_data_source_status(source_id, status, error_summary, 
                                        total_inserted, (date_range_start, date_range_end))

        # Clean up uploaded file
        try:
            os.remove(filepath)
        except:
            pass

        # Try to run stored procedure for processing
        try:
            db.execute_query("EXEC sp_ProcessRawData ?", (source_id,), fetch=False)
            logger.info(f"Stored procedure executed for source_id: {source_id}")
        except Exception as proc_error:
            logger.warning(f"Stored procedure execution failed: {proc_error}")

        return jsonify({
            'message': 'File uploaded and processed successfully with AI analysis.',
            'processed_records': total_inserted,
            'errors': len(errors),
            'error_details': errors[:10] if errors else None,
            'date_range': f"{date_range_start} to {date_range_end}" if date_range_start and date_range_end else None,
            'source_id': source_id,
            'ai_insights': ai_insights,
            'data_quality_score': ai_insights.get('data_quality', {}).get('quality_score', 'Unknown')
        }), 200

    except Exception as e:
        logger.error(f"Enhanced upload failed: {e}")
        return jsonify({
            'error': str(e),
            'ai_support': 'Contact AI assistant for troubleshooting help'
        }), 500

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
            try:
                db.execute_query(query, (source_id,), fetch=False)
            except Exception as del_error:
                logger.warning(f"Delete query failed: {query} - {del_error}")
                continue
        
        return jsonify({'status': 'success', 'message': 'Data source deleted successfully'})
        
    except Exception as e:
        logger.error(f"Failed to delete source: {e}")
        return jsonify({'error': str(e)}), 500
    


@app.route('/api/ai/context', methods=['POST'])
def update_ai_context():
    """Update AI context with current application state"""
    try:
        # Handle missing or malformed JSON
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id', 'anonymous')
        context_data = data.get('context', {})
        
        # Validate context data structure
        if context_data and isinstance(context_data, dict):
            # Log useful context information
            data_count = 0
            if context_data.get('data') and isinstance(context_data['data'], list):
                data_count = len(context_data['data'])
            
            logger.info(f"AI context updated for user {user_id} - Data records: {data_count}")
        else:
            logger.info(f"AI context updated for user {user_id} - No data context")
        
        return jsonify({
            'status': 'context_updated',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Context update failed: {e}")
        logger.error(f"Request data: {request.data}")
        return jsonify({'error': 'Context update failed', 'details': str(e)}), 500
    

@app.route('/api/debug/context', methods=['POST'])
def debug_context():
    """Debug endpoint to see what context data is being sent"""
    try:
        logger.info(f"Raw request data: {request.data}")
        logger.info(f"Content type: {request.content_type}")
        
        data = request.get_json(silent=True)
        logger.info(f"Parsed JSON: {data}")
        
        return jsonify({'received': data, 'status': 'debug_ok'})
        
    except Exception as e:
        logger.error(f"Debug context failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['GET'])
def export_data():
    """Export processed data to Excel"""
    try:
        catchment_name = request.args.get('catchment')
        parameter = request.args.get('parameter', 'RECHARGE').upper()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Map parameter to database category
        parameter_mapping = {'GWL': 'gwlevel', 'RECHARGE': 'recharge', 'BASEFLOW': 'baseflow'}
        db_category = parameter_mapping.get(parameter, 'recharge')
        
        # Build export query
        base_query = """
        SELECT rd.measurement_date, c.catchment_name, rd.source_id,
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
               END as zscore
        FROM dbo.RawData rd
        INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
        WHERE rd.category = ?
        """
        
        conditions = []
        params = [db_category]
        
        if catchment_name:
            conditions.append("c.catchment_name = ?")
            params.append(catchment_name)
            
        if start_date:
            conditions.append("rd.measurement_date >= ?")
            params.append(start_date)
            
        if end_date:
            conditions.append("rd.measurement_date <= ?")
            params.append(end_date)
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " ORDER BY rd.measurement_date"
        
        data = db.execute_query(base_query, tuple(params))
        
        if not data:
            return jsonify({'error': 'No data to export'}), 400
        
        # Convert to DataFrame and add classifications
        df = pd.DataFrame(data)
        
        # Add classification column
        def classify_zscore(zscore):
            if pd.isna(zscore):
                return 'Normal'
            classification = analyzer.classify_threshold(zscore)
            return classification['level']
        
        if 'zscore' in df.columns:
            df['classification'] = df['zscore'].apply(classify_zscore)
            df['is_failure'] = df['zscore'].apply(lambda z: analyzer.classify_threshold(z)['is_failure'] if pd.notna(z) else False)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Processed_Data', index=False)
        
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

# AI-SPECIFIC ROUTES

@app.route('/api/ai/chat-advanced', methods=['POST'])
def ai_chat_advanced():
    """Advanced AI chat endpoint with full conversational capabilities like ChatGPT"""
    try:
        data = request.json
        message = data.get('message', '').strip()
        user_id = data.get('user_id', 'anonymous')
        context_data = data.get('context', {})
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Check if OpenAI is available for true conversational AI
        if OPENAI_AVAILABLE and config.OPENAI_API_KEY:
            try:
                return handle_openai_conversation(message, user_id, context_data)
            except Exception as openai_error:
                logger.warning(f"OpenAI API failed: {openai_error}")
                # Fall through to enhanced rule-based response
        
        # Enhanced conversational AI without OpenAI
        response = generate_advanced_conversational_response(message, context_data)
        
        return jsonify({
            'content': response['content'],
            'type': response['type'],
            'suggestions': response.get('suggestions', []),
            'context_actions': response.get('context_actions', [])
        })
        
    except Exception as e:
        logger.error(f"Advanced AI chat failed: {e}")
        return jsonify({
            'content': 'I encountered an issue processing your request. Please try rephrasing your question.',
            'type': 'error'
        }), 500

def handle_openai_conversation(message, user_id, context_data):
    """Handle OpenAI-powered conversational AI"""
    try:
        import openai
        
        # Build context-aware system message
        system_message = build_system_message(context_data)
        
        # Create conversation with OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or "gpt-4" if you have access
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Generate contextual suggestions
        suggestions = generate_contextual_suggestions(message, context_data)
        
        return jsonify({
            'content': ai_response,
            'type': 'conversational',
            'suggestions': suggestions,
            'context_actions': determine_context_actions(message, context_data)
        })
        
    except Exception as e:
        logger.error(f"OpenAI conversation failed: {e}")
        raise

def build_system_message(context_data):
    """Build a comprehensive system message for OpenAI"""
    base_prompt = """You are an expert AI assistant for groundwater analysis systems. You specialize in:

1. Groundwater hydrology and management
2. Statistical analysis and Z-score methodologies
3. Performance metrics (reliability, resilience, vulnerability, sustainability)
4. Data interpretation and system diagnostics
5. Excel data processing and quality assessment

You provide conversational, helpful responses that are:
- Technical but accessible
- Contextually aware of the user's current data and system state
- Actionable with specific recommendations
- Educational about groundwater concepts

Current user context:"""
    
    # Add context about user's current state
    if context_data:
        if context_data.get('data') and len(context_data['data']) > 0:
            data_count = len(context_data['data'])
            failure_count = sum(1 for d in context_data['data'] if d.get('is_failure') == 1)
            failure_rate = (failure_count / data_count) * 100 if data_count > 0 else 0
            
            base_prompt += f"""
- User has {data_count} data records loaded
- Current failure rate: {failure_rate:.1f}%
- System performance: {'High stress' if failure_rate > 30 else 'Moderate stress' if failure_rate > 15 else 'Good performance'}
"""
        
        filters = context_data.get('filters', {})
        if filters:
            active_filters = {k: v for k, v in filters.items() if v}
            if active_filters:
                base_prompt += f"- Active filters: {active_filters}\n"
        
        charts = context_data.get('charts', {})
        if charts.get('visible'):
            base_prompt += f"- Visible charts: {charts['visible']}\n"
    
    base_prompt += "\nRespond conversationally and provide specific, actionable advice based on this context."
    
    return base_prompt

def generate_advanced_conversational_response(message, context_data):
    """Generate advanced conversational responses without OpenAI"""
    message_lower = message.lower()
    
    # Analyze user intent and context
    intent = analyze_user_intent(message_lower)
    current_data = context_data.get('data', [])
    
    # Generate contextual response based on intent and data
    if intent == 'data_analysis' and current_data:
        return generate_data_analysis_response(message_lower, current_data)
    elif intent == 'methodology':
        return generate_methodology_response(message_lower)
    elif intent == 'troubleshooting':
        return generate_troubleshooting_response(message_lower, context_data)
    elif intent == 'interpretation':
        return generate_interpretation_response(message_lower, current_data)
    elif intent == 'comparison':
        return generate_comparison_response(message_lower, current_data)
    elif intent == 'prediction':
        return generate_prediction_response(message_lower, current_data)
    else:
        return generate_general_conversational_response(message_lower, context_data)

def analyze_user_intent(message):
    """Analyze user intent from message"""
    intents = {
        'data_analysis': ['analyze', 'analysis', 'pattern', 'trend', 'what does', 'interpret'],
        'methodology': ['formula', 'calculate', 'equation', 'method', 'how is', 'definition'],
        'troubleshooting': ['error', 'problem', 'issue', 'fix', 'help', 'trouble', 'wrong'],
        'interpretation': ['mean', 'means', 'significance', 'important', 'tell me', 'explain'],
        'comparison': ['compare', 'versus', 'vs', 'difference', 'better', 'worse'],
        'prediction': ['predict', 'forecast', 'future', 'expect', 'likely', 'will']
    }
    
    for intent, keywords in intents.items():
        if any(keyword in message for keyword in keywords):
            return intent
    
    return 'general'

def generate_data_analysis_response(message, current_data):
    """Generate intelligent data analysis responses"""
    if not current_data:
        return {
            'content': "I don't see any data loaded currently. To get meaningful analysis, please apply filters to load your groundwater data first. Once you have data, I can help you understand patterns, identify issues, and provide insights about your groundwater system's performance.",
            'type': 'help',
            'suggestions': ['Apply filters to load data', 'Upload new data file', 'Check data sources']
        }
    
    # Calculate key statistics
    total_records = len(current_data)
    failure_count = sum(1 for d in current_data if d.get('is_failure') == 1)
    failure_rate = (failure_count / total_records) * 100
    
    # Classification analysis
    classifications = {}
    for record in current_data:
        classification = record.get('classification', 'Unknown')
        classifications[classification] = classifications.get(classification, 0) + 1
    
    # Generate contextual analysis
    analysis_content = f"Looking at your current dataset with {total_records} records, here's what I see:\n\n"
    
    # Performance assessment
    if failure_rate > 30:
        analysis_content += f"🔴 **High Stress Alert**: {failure_rate:.1f}% failure rate indicates your groundwater system is under significant stress. This requires immediate attention."
    elif failure_rate > 15:
        analysis_content += f"🟡 **Moderate Concern**: {failure_rate:.1f}% failure rate suggests some stress in the system. Monitor closely."
    else:
        analysis_content += f"🟢 **Good Performance**: {failure_rate:.1f}% failure rate indicates relatively stable conditions."
    
    # Classification breakdown
    if classifications:
        analysis_content += f"\n\n**Performance Distribution:**\n"
        for classification, count in classifications.items():
            percentage = (count / total_records) * 100
            analysis_content += f"• {classification.replace('_', ' ')}: {count} records ({percentage:.1f}%)\n"
    
    # Contextual insights
    if 'Extreme_Deficit' in classifications and classifications['Extreme_Deficit'] > 0:
        analysis_content += f"\n⚠️ **Critical Finding**: {classifications['Extreme_Deficit']} records show extreme deficit conditions. These periods likely represent severe drought stress that could impact long-term sustainability."
    
    if 'trend' in message or 'pattern' in message:
        analysis_content += "\n\n**Trend Analysis**: Look at your time series chart to identify seasonal patterns. Declining trends over time may indicate long-term aquifer depletion, while cyclical patterns often reflect natural seasonal variations."
    
    suggestions = []
    if failure_rate > 25:
        suggestions.extend(['What causes these high failure rates?', 'How can I reduce system stress?', 'What are the long-term implications?'])
    else:
        suggestions.extend(['Show me seasonal patterns', 'Compare with other catchments', 'Explain the methodology'])
    
    return {
        'content': analysis_content,
        'type': 'data_analysis',
        'suggestions': suggestions[:3],
        'context_actions': ['update_charts'] if failure_rate > 20 else []
    }

def generate_methodology_response(message):
    """Generate detailed methodology explanations"""
    responses = {
        'z-score': {
            'content': """**Z-Score Standardization**: Z = (X - μ) / σ

This formula transforms your raw groundwater measurements into standardized values:
• **X**: Your observed value (recharge, level, or baseflow)
• **μ (mu)**: Long-term average for your location
• **σ (sigma)**: Standard deviation showing natural variability

**Interpretation:**
• Z > 0.5: Above normal (surplus conditions)
• -0.5 to 0.5: Normal range
• -0.5 to -1.0: Moderate deficit (early drought stress)
• -1.0 to -1.5: Severe deficit (significant drought)
• < -1.5: Extreme deficit (critical drought conditions)

This standardization allows comparison across different locations and time periods.""",
            'suggestions': ['How is the average calculated?', 'What causes high standard deviation?', 'Show me threshold examples']
        },
        'reliability': {
            'content': """**Reliability Index**: R = (T - F) / T

Measures what percentage of time your groundwater system performs satisfactorily:
• **T**: Total time periods in your analysis
• **F**: Number of failure periods (when Z-score < -0.5)

**Real-world meaning:**
• R = 0.85 means system performs well 85% of the time
• R < 0.7 suggests frequent stress periods requiring management intervention
• R > 0.9 indicates highly reliable system

**Management implications**: Low reliability suggests need for adaptive strategies, water demand management, or alternative supply development.""",
            'suggestions': ['What reliability level is acceptable?', 'How to improve reliability?', 'Compare my reliability score']
        },
        'resilience': {
            'content': """**Resilience Index**: γ = (1/ρ * Σα(j))⁻¹

Measures how quickly your system recovers from drought failures:
• **ρ**: Number of distinct failure sequences
• **α(j)**: Duration of each failure sequence
• Higher values = faster recovery

**What it means:**
• High resilience: System bounces back quickly from droughts
• Low resilience: Extended recovery periods after stress
• Critical for understanding drought vulnerability

**Management insight**: Low resilience may indicate aquifer depletion, reduced recharge capacity, or structural changes requiring long-term planning.""",
            'suggestions': ['What affects resilience?', 'How to build system resilience?', 'Interpret my resilience score']
        }
    }
    
    # Find the most relevant response
    for key, response in responses.items():
        if key in message:
            return {
                'content': response['content'],
                'type': 'methodology',
                'suggestions': response['suggestions']
            }
    
    # General methodology response
    return {
        'content': """I can explain several groundwater analysis methodologies:

**Core Metrics:**
1. **Z-Score Standardization** - Transforms raw data for comparison
2. **Reliability** - Frequency of satisfactory performance
3. **Resilience** - Speed of recovery from failures
4. **Vulnerability** - Severity of failure impacts
5. **Sustainability Index** - Combined performance measure

Which specific methodology would you like me to explain in detail?""",
        'type': 'methodology',
        'suggestions': ['Explain Z-score formula', 'How is reliability calculated?', 'What is the sustainability index?']
    }

def generate_contextual_suggestions(message, context_data):
    """Generate smart follow-up suggestions"""
    suggestions = []
    current_data = context_data.get('data', [])
    
    if current_data:
        failure_count = sum(1 for d in current_data if d.get('is_failure') == 1)
        failure_rate = (failure_count / len(current_data)) * 100
        
        if failure_rate > 25:
            suggestions.extend(['What actions should I take?', 'How can I improve performance?', 'What are the risks?'])
        elif 'explain' in message.lower():
            suggestions.extend(['Show me examples', 'How does this compare?', 'What should I monitor?'])
        elif 'analysis' in message.lower():
            suggestions.extend(['What patterns do you see?', 'Are there seasonal trends?', 'Compare with benchmarks'])
    else:
        suggestions.extend(['Help me upload data', 'Explain the methodology', 'What data do I need?'])
    
    return suggestions[:3]

def determine_context_actions(message, context_data):
    """Determine actions the UI should take based on conversation"""
    actions = []
    message_lower = message.lower()
    
    if 'chart' in message_lower or 'graph' in message_lower:
        actions.append('update_charts')
    elif 'upload' in message_lower or 'data' in message_lower:
        actions.append('show_upload_section')
    elif 'export' in message_lower or 'download' in message_lower:
        actions.append('enable_export')
    
    return actions

def generate_troubleshooting_response(message, context_data):
    """Generate troubleshooting responses"""
    if 'upload' in message and 'error' in message:
        return {
            'content': """**Upload Troubleshooting Guide:**

Common issues and solutions:
1. **File Format**: Ensure you're using .xlsx or .xls files
2. **Column Names**: Check that column headers match exactly (case-sensitive)
3. **Data Types**: Dates should be in Excel date format, numbers as numeric values
4. **Missing Data**: Too many empty cells can cause issues
5. **File Size**: Keep files under 16MB

**Quick fixes:**
• Clear browser cache and try again
• Save Excel file in a different format
• Check that category and subcatchment are selected

What specific error message are you seeing?""",
            'type': 'troubleshooting',
            'suggestions': ['Check my column names', 'Validate data format', 'Test with sample file']
        }
    
    return {
        'content': """I'm here to help troubleshoot any issues. Common problems include:

• **Data Upload Issues** - File format, column naming, data validation
• **Analysis Problems** - Missing data, calculation errors, methodology questions  
• **System Errors** - Connection issues, performance problems
• **Interpretation Help** - Understanding results, making decisions

What specific problem are you experiencing?""",
        'type': 'troubleshooting',
        'suggestions': ['Upload problems', 'Analysis questions', 'System errors']
    }

def generate_general_conversational_response(message, context_data):
    """Generate general conversational responses"""
    current_data = context_data.get('data', [])
    
    # Greeting responses
    if any(greeting in message for greeting in ['hello', 'hi', 'hey']):
        if current_data:
            data_summary = f"I see you have {len(current_data)} records loaded. "
        else:
            data_summary = "I notice you don't have any data loaded yet. "
        
        return {
            'content': f"Hello! I'm your groundwater analysis assistant. {data_summary}I can help you understand your data, explain methodologies, troubleshoot issues, or provide insights about groundwater system performance. What would you like to explore?",
            'type': 'conversational',
            'suggestions': ['Analyze my current data', 'Explain the methodology', 'Help with data upload']
        }
    
    # Default helpful response
    return {
        'content': """I'm here to help with your groundwater analysis. I can assist with:

🔍 **Data Analysis** - Interpreting patterns, trends, and performance metrics
📊 **Methodology** - Explaining formulas, calculations, and scientific concepts  
🛠️ **Troubleshooting** - Solving upload issues, errors, and system problems
💡 **Insights** - Providing recommendations and actionable advice

What aspect would you like to explore? Feel free to ask me anything about your groundwater system!""",
        'type': 'conversational',
        'suggestions': ['Analyze my data patterns', 'Explain reliability metrics', 'Help me interpret results']
    }

@app.route('/api/ai/analyze-upload', methods=['POST'])
def ai_analyze_upload():
    """Analyze uploaded data before processing"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        category = request.form.get('category', '')
        subcatchment = request.form.get('subcatchment', '')
        
        if not category or not subcatchment:
            return jsonify({'error': 'Category and subcatchment required'}), 400
        
        # Read Excel file for analysis
        df = pd.read_excel(file)
        
        # Get AI insights
        insights = ai_assistant.analyze_upload_data(df, category, subcatchment)
        
        return jsonify({
            'insights': insights,
            'recommendations': insights.get('recommendations', []),
            'data_quality_score': insights.get('data_quality', {}).get('quality_score', 'Unknown')
        })
        
    except Exception as e:
        logger.error(f"AI upload analysis failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/analyze-data', methods=['POST'])
def ai_analyze_data():
    """Analyze processed data and provide insights"""
    try:
        data = request.json
        current_data = data.get('data', [])
        filters = data.get('filters', {})
        
        # Get AI analysis
        analysis = ai_assistant.analyze_processed_data(current_data, filters)
        
        return jsonify(analysis)
        
    except Exception as e:
        logger.error(f"AI data analysis failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    """Handle basic chat interactions with AI assistant"""
    try:
        data = request.json
        message = data.get('message', '').strip()
        context = data.get('context', {})
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Get chat response
        response = ai_assistant.handle_chat_message(message, context)
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"AI chat failed: {e}")
        return jsonify({
            'content': 'I encountered an error processing your question. Please try again.',
            'type': 'error'
        }), 500

@app.route('/api/ai/methodology', methods=['GET'])
def ai_methodology_info():
    """Get detailed methodology information"""
    try:
        methodology = ai_assistant.methodology_knowledge
        
        return jsonify({
            'methodology': methodology,
            'calculation_examples': {
                'zscore_example': {
                    'scenario': 'Recharge value: 50mm, Average: 45mm, Std Dev: 10mm',
                    'calculation': '(50 - 45) / 10 = 0.5',
                    'interpretation': 'Moderate surplus condition'
                },
                'reliability_example': {
                    'scenario': '100 time periods, 20 failures',
                    'calculation': '(100 - 20) / 100 = 0.8',
                    'interpretation': '80% reliability - system performs well most of the time'
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Methodology info failed: {e}")
        return jsonify({'error': str(e)}), 500

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
        
        try:
            catchments_result = db.execute_query(catchments_query)
            catchments = [row['catchment_name'] for row in catchments_result]
        except Exception as db_error:
            logger.warning(f"Filter options query failed: {db_error}")
            catchments = []
        
        # Get unique categories
        categories_query = """
        SELECT DISTINCT rd.category
        FROM dbo.RawData rd
        WHERE rd.category IS NOT NULL
        ORDER BY rd.category
        """
        
        try:
            categories_result = db.execute_query(categories_query)
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
        except Exception as db_error:
            logger.warning(f"Parameters query failed: {db_error}")
            parameters = ['RECHARGE', 'GWL', 'BASEFLOW']
        
        return jsonify({
            'catchments': catchments,
            'parameters': parameters
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get filter options: {e}")
        return jsonify({
            'catchments': [],
            'parameters': ['RECHARGE', 'GWL', 'BASEFLOW']
        }), 200

@app.route('/api/metrics', methods=['GET'])
def get_performance_metrics():
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

# Application startup and configuration
def initialize_app():
    """Initialize the application with proper configuration"""
    logger.info("Starting AI-Enhanced Groundwater Analysis API Server")
    logger.info(f"Database: {Config.SQL_SERVER}/{Config.SQL_DATABASE}")
    logger.info(f"Upload folder: {Config.UPLOAD_FOLDER}")
    logger.info(f"AI Features: {'Enabled' if ai_assistant.ai_enabled else 'Disabled'}")
    logger.info(f"OpenAI Available: {OPENAI_AVAILABLE}")
    
    # Test database connection on startup
    try:
        db.execute_query("SELECT 1")
        logger.info("Database connection successful")
    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
        logger.warning("Application will run in limited mode - some features may not be available")
    
    # Ensure required directories exist
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    # Initialize AI assistant
    if ai_assistant.ai_enabled and OPENAI_AVAILABLE:
        logger.info("AI Assistant initialized with OpenAI integration")
    else:
        logger.info("AI Assistant running in rule-based mode")

if __name__ == '__main__':
    initialize_app()
    app.run(
        debug=Config.DEBUG, 
        host=Config.API_HOST, 
        port=Config.API_PORT,
        threaded=True
    )