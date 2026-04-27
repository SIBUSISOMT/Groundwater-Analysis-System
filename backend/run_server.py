import os
import sys
import logging

# Force UTF-8 output on Windows so unicode characters don't crash the terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from app import app, db
from config import Config

def setup_logging():
    """Setup application logging"""
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Config.LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )

def validate_environment():
    """Validate environment before starting"""
    print("Validating environment...")
        

    config_errors = Config.validate()
    if config_errors:
        print("Configuration errors:")
        for error in config_errors:
            print(f"  - {error}")
        return False
        
  
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
    print(f"API Host: {Config.API_HOST}:{Config.API_PORT}")
    print(f"Database: {Config.SQL_SERVER}/{Config.SQL_DATABASE}")
    print(f"Upload folder: {Config.UPLOAD_FOLDER}")
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
            debug=Config.DEBUG,
            host=Config.API_HOST,
            port=Config.API_PORT,
            threaded=True  # Enable threading for multiple requests
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()