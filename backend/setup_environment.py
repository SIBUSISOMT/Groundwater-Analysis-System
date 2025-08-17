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
        schema_path = os.path.join('..', 'database', 'schema.sql')
        if not os.path.exists(schema_path):
            schema_path = 'schema.sql'  # Try current directory
        
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
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
        else:
            print("✗ Database schema file not found")
            print("Please run the schema.sql file manually in SQL Server Management Studio")
            return False
        
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        return False

def test_api_endpoints():
    """Test if all required API endpoints are working"""
    print("Testing API endpoints...")
    
    try:
        import requests
        base_url = "http://localhost:5000/api"
        
        # Test health endpoint
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✓ API health endpoint working")
            return True
        else:
            print("✗ API server not responding")
            return False
    except ImportError:
        print("✓ Skipping API test (requests not installed)")
        return True
    except Exception as e:
        print(f"✗ API test failed: {e}")
        return False

def create_env_file():
    """Create .env file if it doesn't exist"""
    print("Creating environment configuration...")
    
    env_content = """# SQL Server Configuration
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
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✓ Created .env configuration file")
    else:
        print("✓ .env file already exists")
    
    return True

def main():
    """Main setup function"""
    print("=== Groundwater Analysis System Setup ===\n")
    
    success = True
    
    # 1. Create environment file
    if not create_env_file():
        success = False
    
    # 2. Validate dependencies
    if not validate_dependencies():
        success = False
        print("\nPlease install missing dependencies first:")
        print("pip install -r requirements.txt")
    
    # 3. Test database connection
    if not check_sql_server_connection():
        success = False
        print("\nPlease ensure SQL Server is running and accessible")
    
    # 4. Setup database schema
    if not setup_database():
        print("Warning: Could not setup database schema automatically")
        print("Please run the database/schema.sql script manually in SQL Server Management Studio")
    
    # 5. Create sample data
    if not create_sample_data():
        success = False
    
    if success:
        print("\n=== Setup completed successfully! ===")
        print("\nNext steps:")
        print("1. Run the API server: python app.py")
        print("2. Open the React frontend in a browser")
        print("3. Upload sample Excel files from 'sample_data/' directory")
        print("4. Analyze groundwater performance metrics")
        print("\nAPI will be available at: http://localhost:5000")
        print("Sample data files created in: ./sample_data/")
        
        # Create uploads directory
        os.makedirs('uploads', exist_ok=True)
        print("✓ Created uploads directory")
        
    else:
        print("\n=== Setup encountered issues ===")
        print("Please resolve the above issues before running the system")

if __name__ == "__main__":
    main()