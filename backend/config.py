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