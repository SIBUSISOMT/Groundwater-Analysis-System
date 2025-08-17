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