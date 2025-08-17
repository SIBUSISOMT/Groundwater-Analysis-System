# requirements.txt
# Groundwater Analysis System Dependencies

# Core Flask and API
Flask==2.3.3
Flask-CORS==4.0.0

# Database connectivity
pyodbc==4.0.39

# Data processing and analysis
pandas==2.0.3
numpy==1.24.3
openpyxl==3.1.2
xlrd==2.0.1

# Scientific computing for advanced calculations
scipy==1.11.2

# Utilities
Werkzeug==2.3.7
python-dotenv==1.0.0

# Development and testing
pytest==7.4.2
pytest-cov==4.1.0

# ================================
# setup_environment.py
# Environment setup and validation script

import os
import sys
import pyodbc
import pandas as pd
import numpy as np
from datetime import datetime

def check_sql_server_connection():
    """Test SQL Server connection"""
    print("Testing SQL Server connection...")
    
    # Try different connection methods
    connection_strings = [
        # Windows Authentication
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=master;Trusted_Connection=yes;",
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=master;Trusted_Connection=yes;TrustServerCertificate=yes;",
        # SQL Server Authentication (if needed)
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=master;UID=sa;PWD=YourPassword;",
    ]
    
    for i, conn_str in enumerate(connection_strings):
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            print(f"✓ Connected to SQL Server: {version[:50]}...")
            conn.close()
            return True
        except Exception as e:
            print(f"Connection attempt {i+1} failed: {e}")
    
    print("✗ Could not connect to SQL Server")
    return False

def create_sample_data():
    """Create sample Excel data for testing"""
    print("Creating sample data...")
    
    # Generate sample groundwater data
    dates = pd.date_range('2020-01-01', '2024-12-31', freq='M')
    catchments = ['Crocodile', 'Komati', 'Sabie-Sand', 'Usuthu']
    
    data = []
    np.random.seed(42)  # For reproducible data
    
    for catchment in catchments:
        for date in dates:
            # Simulate seasonal patterns and drought effects
            month = date.month
            year = date.year
            
            # Base values with seasonal variation
            gwr_base = 50 + 30 * np.sin(2 * np.pi * month / 12)  # Seasonal recharge
            gwl_base = 10 + 2 * np.sin(2 * np.pi * month / 12)   # Seasonal level variation
            gwb_base = 5 + 3 * np.sin(2 * np.pi * month / 12)    # Seasonal baseflow
            
            # Add drought effects (2015-2016 and 2019-2020)
            drought_factor = 1.0
            if 2015 <= year <= 2016:
                drought_factor = 0.3  # Severe drought
            elif 2019 <= year <= 2020:
                drought_factor = 0.6  # Moderate drought
            
            # Add random noise
            gwr = max(0, gwr_base * drought_factor + np.random.normal(0, 10))
            gwl = max(0, gwl_base * drought_factor + np.random.normal(0, 2))
            gwb = max(0, gwb_base * drought_factor + np.random.normal(0, 1))
            
            data.append({
                'Date': date.strftime('%Y-%m-%d'),
                'Catchment': catchment,
                'GWR': round(gwr, 2),
                'GWL': round(gwl, 2),
                'GWB': round(gwb, 4)
            })
    
    # Create DataFrame and save to Excel
    df = pd.DataFrame(data)
    
    # Create sample files directory
    os.makedirs('sample_data', exist_ok=True)
    
    # Save complete dataset
    df.to_excel('sample_data/groundwater_complete_dataset.xlsx', index=False)
    
    # Save individual catchment datasets
    for catchment in catchments:
        catchment_data = df[df['Catchment'] == catchment]
        filename = f'sample_data/groundwater_{catchment.lower()}_data.xlsx'
        catchment_data.to_excel(filename, index=False)
    
    print(f"✓ Created sample datasets with {len(df)} records")
    print("Sample files saved in 'sample_data/' directory:")
    for file in os.listdir('sample_data'):
        if file.endswith('.xlsx'):
            print(f"  - {file}")
    
    return True

def validate_dependencies():
    """Check if all required packages are installed"""
    print("Validating Python dependencies...")
    
    required_packages = [
        'flask', 'pandas', 'numpy', 'pyodbc', 'openpyxl', 
        'scipy', 'werkzeug', 'flask_cors'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} - MISSING")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\nInstall missing packages with:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def setup_database():
    """Setup database schema"""
    print("Setting up database schema...")
    
    try:
        conn_str = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=master;Trusted_Connection=yes;"
        conn = pyodbc.connect(conn_str)
        
        # Read and execute schema SQL
        with open('sql_schema.sql', 'r') as f:
            schema_sql = f.read()
        
        # Execute schema in batches (SQL Server doesn't like multiple statements)
        batches = schema_sql.split('GO')
        cursor = conn.cursor()
        
        for batch in batches:
            batch = batch.strip()
            if batch and not batch.startswith('--'):
                try:
                    cursor.execute(batch)
                    conn.commit()
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning executing batch: {e}")
        
        cursor.close()
        conn.close()
        print("✓ Database schema setup completed")
        return True
        
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        return False

def main():
    """Main setup function"""
    print("=== Groundwater Analysis System Setup ===\n")
    
    success = True
    
    # 1. Validate dependencies
    if not validate_dependencies():
        success = False
        print("\nPlease install missing dependencies first:")
        print("pip install -r requirements.txt")
    
    # 2. Test database connection
    if not check_sql_server_connection():
        success = False
        print("\nPlease ensure SQL Server is running and accessible")
    
    # 3. Create sample data
    if not create_sample_data():
        success = False
    
    # 4. Setup database (if schema file exists)
    if os.path.exists('sql_schema.sql'):
        if not setup_database():
            print("Warning: Could not setup database schema automatically")
            print("Please run the SQL schema script manually in SQL Server Management Studio")
    
    if success:
        print("\n=== Setup completed successfully! ===")
        print("\nNext steps:")
        print("1. Run the API server: python app.py")
        print("2. Open the React frontend in a browser")
        print("3. Upload sample Excel files from 'sample_data/' directory")
        print("4. Analyze groundwater performance metrics")
        print("\nAPI will be available at: http://localhost:5000")
        print("Sample data files created in: ./sample_data/")
    else:
        print("\n=== Setup encountered issues ===")
        print("Please resolve the above issues before running the system")

if __name__ == "__main__":
    main()

# ================================
# config.py
# Configuration management

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration"""
    
    # SQL Server Configuration
    SQL_SERVER = os.getenv('SQL_SERVER', 'localhost')
    SQL_DATABASE = os.getenv('SQL_DATABASE', 'GroundwaterAnalysis')
    SQL_USERNAME = os.getenv('SQL_USERNAME', '')  # Empty for Windows Auth
    SQL_PASSWORD = os.getenv('SQL_PASSWORD', '')
    
    # File Upload Configuration
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 16 * 1024 * 1024))  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    
    # Analysis Parameters (from Shakhane et al. study)
    THRESHOLDS = {
        'normal_upper': float(os.getenv('THRESHOLD_NORMAL_UPPER', 0.5)),
        'normal_lower': float(os.getenv('THRESHOLD_NORMAL_LOWER', -0.5)),
        'moderate_lower': float(os.getenv('THRESHOLD_MODERATE_LOWER', -1.0)),
        'severe_lower': float(os.getenv('THRESHOLD_SEVERE_LOWER', -1.5)),
        'extreme_lower': float(os.getenv('THRESHOLD_EXTREME_LOWER', -2.0))
    }
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'groundwater_analysis.log')
    
    # API Configuration
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        
        if not cls.SQL_SERVER:
            errors.append("SQL_SERVER not configured")
            
        if not cls.SQL_DATABASE:
            errors.append("SQL_DATABASE not configured")
            
        if not os.path.exists(cls.UPLOAD_FOLDER):
            try:
                os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create upload folder: {e}")
        
        return errors

# ================================
# advanced_calculations.py
# Advanced groundwater analysis calculations

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class AdvancedGroundwaterAnalyzer:
    """
    Advanced groundwater analysis implementing additional calculations
    from the Shakhane et al. methodology
    """
    
    @staticmethod
    def calculate_failure_intensity(z_scores: np.array, failure_mask: np.array) -> Dict:
        """
        Calculate failure intensity (Equation 4 from paper)
        Fm = Σ|SI| / (tn - tp)
        """
        if not np.any(failure_mask):
            return {'intensity': 0, 'duration': 0, 'severity_sum': 0}
        
        # Find continuous failure sequences
        sequences = []
        current_seq = []
        
        for i, is_failure in enumerate(failure_mask):
            if is_failure:
                current_seq.append({'index': i, 'severity': abs(z_scores[i])})
            else:
                if current_seq:
                    sequences.append(current_seq)
                    current_seq = []
        
        if current_seq:  # Handle sequence ending in failure
            sequences.append(current_seq)
        
        if not sequences:
            return {'intensity': 0, 'duration': 0, 'severity_sum': 0}
        
        # Calculate intensity for each sequence
        intensities = []
        for seq in sequences:
            duration = len(seq)
            severity_sum = sum(point['severity'] for point in seq)
            intensity = severity_sum / duration if duration > 0 else 0
            intensities.append({
                'duration': duration,
                'severity_sum': severity_sum,
                'intensity': intensity
            })
        
        # Overall metrics
        total_duration = sum(seq['duration'] for seq in intensities)
        total_severity = sum(seq['severity_sum'] for seq in intensities)
        avg_intensity = total_severity / total_duration if total_duration > 0 else 0
        
        return {
            'intensity': avg_intensity,
            'duration': total_duration,
            'severity_sum': total_severity,
            'sequences': len(sequences),
            'avg_sequence_duration': total_duration / len(sequences),
            'max_sequence_duration': max(seq['duration'] for seq in intensities)
        }
    
    @staticmethod
    def calculate_return_period(failures: List[float], threshold: float = -0.5) -> Dict:
        """
        Calculate return periods using threshold level approach (Equation 6)
        T(x) = 1/[(1-F(x))RF]
        """
        if not failures:
            return {'return_period': float('inf'), 'frequency': 0}
        
        failures = np.array(failures)
        
        # Calculate relative failure frequency
        total_years = len(failures)
        failure_years = np.sum(failures < threshold)
        relative_frequency = failure_years / total_years if total_years > 0 else 0
        
        if relative_frequency == 0:
            return {'return_period': float('inf'), 'frequency': 0}
        
        # Sort failures for cumulative distribution
        sorted_failures = np.sort(failures[failures < threshold])
        
        if len(sorted_failures) == 0:
            return {'return_period': float('inf'), 'frequency': 0}
        
        # Calculate return periods for different severity levels
        return_periods = {}
        severity_thresholds = [-0.5, -1.0, -1.5, -2.0]
        
        for thresh in severity_thresholds:
            severe_failures = failures[failures < thresh]
            if len(severe_failures) > 0:
                rf = len(severe_failures) / total_years
                return_period = 1 / rf if rf > 0 else float('inf')
                return_periods[f'threshold_{abs(thresh)}'] = return_period
        
        # Overall return period
        overall_return_period = 1 / relative_frequency
        
        return {
            'return_period': overall_return_period,
            'frequency': relative_frequency,
            'failure_years': failure_years,
            'total_years': total_years,
            'severity_return_periods': return_periods
        }
    
    @staticmethod
    def calculate_confidence_intervals(data: np.array, confidence: float = 0.95) -> Dict:
        """
        Calculate confidence intervals for reliability estimates
        """
        if len(data) == 0:
            return {'lower': 0, 'upper': 0, 'mean': 0}
        
        mean = np.mean(data)
        sem = stats.sem(data)  # Standard error of mean
        
        # Calculate confidence interval
        alpha = 1 - confidence
        dof = len(data) - 1
        
        if dof > 0:
            t_value = stats.t.ppf(1 - alpha/2, dof)
            margin_error = t_value * sem
            
            ci_lower = mean - margin_error
            ci_upper = mean + margin_error
        else:
            ci_lower = ci_upper = mean
        
        return {
            'mean': float(mean),
            'lower': float(ci_lower),
            'upper': float(ci_upper),
            'margin_error': float(margin_error) if dof > 0 else 0,
            'confidence': confidence
        }
    
    @staticmethod
    def seasonal_analysis(df: pd.DataFrame, date_col: str, value_col: str) -> Dict:
        """
        Perform seasonal analysis of groundwater parameters
        """
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        df['month'] = df[date_col].dt.month
        df['season'] = df['month'].map({
            12: 'Summer', 1: 'Summer', 2: 'Summer',
            3: 'Autumn', 4: 'Autumn', 5: 'Autumn',
            6: 'Winter', 7: 'Winter', 8: 'Winter',
            9: 'Spring', 10: 'Spring', 11: 'Spring'
        })
        
        # Calculate seasonal statistics
        seasonal_stats = df.groupby('season')[value_col].agg([
            'count', 'mean', 'std', 'min', 'max'
        ]).round(4)
        
        # Monthly statistics
        monthly_stats = df.groupby('month')[value_col].agg([
            'count', 'mean', 'std', 'min', 'max'
        ]).round(4)
        
        # Seasonal failure analysis if z-scores are available
        if f'{value_col}_zscore' in df.columns:
            seasonal_failures = df.groupby('season').apply(
                lambda x: (x[f'{value_col}_zscore'] < -0.5).sum()
            )
            total_by_season = df.groupby('season').size()
            failure_rates = (seasonal_failures / total_by_season * 100).round(2)
        else:
            failure_rates = None
        
        return {
            'seasonal_stats': seasonal_stats.to_dict(),
            'monthly_stats': monthly_stats.to_dict(),
            'seasonal_failure_rates': failure_rates.to_dict() if failure_rates is not None else None
        }
    
    @staticmethod
    def drought_characterization(z_scores: np.array, dates: pd.DatetimeIndex) -> Dict:
        """
        Characterize drought events based on z-score sequences
        """
        drought_threshold = -0.5
        severe_threshold = -1.5
        
        # Identify drought periods
        is_drought = z_scores < drought_threshold
        drought_events = []
        
        in_drought = False
        drought_start = None
        current_drought = []
        
        for i, (date, is_drought_point, z_score) in enumerate(zip(dates, is_drought, z_scores)):
            if is_drought_point and not in_drought:
                # Start of drought
                in_drought = True
                drought_start = date
                current_drought = [{'date': date, 'zscore': z_score}]
                
            elif is_drought_point and in_drought:
                # Continue drought
                current_drought.append({'date': date, 'zscore': z_score})
                
            elif not is_drought_point and in_drought:
                # End of drought
                drought_end = dates[i-1] if i > 0 else date
                duration = len(current_drought)
                severity = np.mean([abs(p['zscore']) for p in current_drought])
                intensity = sum(abs(p['zscore']) for p in current_drought) / duration
                
                drought_events.append({
                    'start_date': drought_start.strftime('%Y-%m-%d'),
                    'end_date': drought_end.strftime('%Y-%m-%d'),
                    'duration_months': duration,
                    'severity': round(severity, 4),
                    'intensity': round(intensity, 4),
                    'max_deficit': round(min(p['zscore'] for p in current_drought), 4),
                    'is_severe': severity > abs(severe_threshold)
                })
                
                in_drought = False
                current_drought = []
        
        # Handle drought that continues to end of data
        if in_drought and current_drought:
            duration = len(current_drought)
            severity = np.mean([abs(p['zscore']) for p in current_drought])
            intensity = sum(abs(p['zscore']) for p in current_drought) / duration
            
            drought_events.append({
                'start_date': drought_start.strftime('%Y-%m-%d'),
                'end_date': dates[-1].strftime('%Y-%m-%d'),
                'duration_months': duration,
                'severity': round(severity, 4),
                'intensity': round(intensity, 4),
                'max_deficit': round(min(p['zscore'] for p in current_drought), 4),
                'is_severe': severity > abs(severe_threshold),
                'ongoing': True
            })
        
        # Summary statistics
        if drought_events:
            durations = [e['duration_months'] for e in drought_events]
            severities = [e['severity'] for e in drought_events]
            
            summary = {
                'total_droughts': len(drought_events),
                'severe_droughts': sum(1 for e in drought_events if e['is_severe']),
                'avg_duration': round(np.mean(durations), 2),
                'max_duration': max(durations),
                'avg_severity': round(np.mean(severities), 4),
                'max_severity': round(max(severities), 4),
                'total_drought_months': sum(durations),
                'drought_frequency': round(sum(durations) / len(z_scores) * 100, 2)  # % of time in drought
            }
        else:
            summary = {
                'total_droughts': 0,
                'severe_droughts': 0,
                'avg_duration': 0,
                'max_duration': 0,
                'avg_severity': 0,
                'max_severity': 0,
                'total_drought_months': 0,
                'drought_frequency': 0
            }
        
        return {
            'drought_events': drought_events,
            'summary': summary
        }

# ================================
# run_server.py
# Main application runner

import os
import sys
import logging
from app import app, config, db

def setup_logging():
    """Setup application logging"""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )

def validate_environment():
    """Validate environment before starting"""
    print("Validating environment...")
    
    # Check configuration
    config_errors = config.Config.validate()
    if config_errors:
        print("Configuration errors:")
        for error in config_errors:
            print(f"  - {error}")
        return False
    
    # Test database connection
    try:
        db.execute_query("SELECT 1")
        print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    print("✓ Environment validation passed")
    return True

def main():
    """Main application entry point"""
    print("=== Groundwater Analysis System Server ===")
    print(f"API Host: {config.API_HOST}:{config.API_PORT}")
    print(f"Database: {config.SQL_SERVER}/{config.SQL_DATABASE}")
    print(f"Upload folder: {config.UPLOAD_FOLDER}")
    print()
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Start server
    logger.info("Starting Groundwater Analysis API Server")
    
    try:
        app.run(
            debug=config.DEBUG,
            host=config.API_HOST,
            port=config.API_PORT,
            threaded=True  # Enable threading for multiple requests
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

# ================================
# .env.example
# Example environment configuration file
# Copy to .env and modify as needed

# SQL Server Configuration
SQL_SERVER=localhost
SQL_DATABASE=GroundwaterAnalysis
SQL_USERNAME=
SQL_PASSWORD=

# File Upload Configuration  
UPLOAD_FOLDER=uploads
MAX_FILE_SIZE=16777216

# Threshold Configuration (Shakhane et al. study)
THRESHOLD_NORMAL_UPPER=0.5
THRESHOLD_NORMAL_LOWER=-0.5
THRESHOLD_MODERATE_LOWER=-1.0
THRESHOLD_SEVERE_LOWER=-1.5
THRESHOLD_EXTREME_LOWER=-2.0

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=groundwater_analysis.log

# API Configuration
API_HOST=0.0.0.0
API_PORT=5000
DEBUG=True

# ================================
# Installation and Setup Instructions

"""
Groundwater Analysis System - Installation Instructions

1. Prerequisites:
   - Python 3.8+
   - SQL Server (Express or full version)
   - SQL Server Management Studio (SSMS)

2. Install SQL Server ODBC Driver:
   - Download and install Microsoft ODBC Driver 17 for SQL Server
   - https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

3. Setup Python Environment:
   pip install -r requirements.txt

4. Configure Environment:
   - Copy .env.example to .env
   - Update SQL Server connection details

5. Setup Database:
   - Run SQL schema script in SSMS: sql_schema.sql
   - Or use: python setup_environment.py

6. Generate Sample Data:
   python setup_environment.py

7. Start the API Server:
   python run_server.py

8. Test the System:
   - API available at: http://localhost:5000
   - Upload sample Excel files from sample_data/ directory
   - Use frontend React app or API endpoints directly

9. API Endpoints:
   GET  /api/health              - Health check
   POST /api/upload              - Upload Excel file
   GET  /api/catchments          - List catchments
   GET  /api/data                - Get processed data
   GET  /api/metrics             - Get performance metrics
   GET  /api/failure-analysis    - Get failure analysis
   GET  /api/sources             - List data sources
   GET  /api/export              - Export data to Excel
   GET  /api/thresholds          - Get threshold configuration

10. Troubleshooting:
    - Check log file: groundwater_analysis.log
    - Ensure SQL Server is running
    - Verify ODBC driver installation
    - Check firewall settings for SQL Server
"""