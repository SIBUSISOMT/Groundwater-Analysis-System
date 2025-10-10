-- Fixed Groundwater Analysis System Database Schema
-- Proper date handling for Excel data compatibility

USE master;
GO

-- Create database if it doesn't exist
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'GroundwaterAnalysis')
BEGIN
    CREATE DATABASE GroundwaterAnalysis;
END
GO

USE GroundwaterAnalysis;
GO

-- Drop tables if they exist (for fresh setup)
IF OBJECT_ID('dbo.PerformanceMetrics', 'U') IS NOT NULL DROP TABLE dbo.PerformanceMetrics;
IF OBJECT_ID('dbo.ProcessedData', 'U') IS NOT NULL DROP TABLE dbo.ProcessedData;
IF OBJECT_ID('dbo.RawData', 'U') IS NOT NULL DROP TABLE dbo.RawData;
IF OBJECT_ID('dbo.Catchments', 'U') IS NOT NULL DROP TABLE dbo.Catchments;
IF OBJECT_ID('dbo.DataSources', 'U') IS NOT NULL DROP TABLE dbo.DataSources;
GO

-- 1. Data Sources Table - Track uploaded Excel files
CREATE TABLE dbo.DataSources (
    source_id INT IDENTITY(1,1) PRIMARY KEY,
    file_name NVARCHAR(255) NOT NULL,
    category NVARCHAR(20) CHECK (category IN ('Recharge', 'Baseflow', 'GWLevel')) NOT NULL,
    subcatchment NVARCHAR(100) NOT NULL,
    upload_date DATETIME2 DEFAULT GETDATE(),
    file_size_kb INT,
    total_records INT,
    date_range_start NVARCHAR(10), -- Changed to NVARCHAR to store 'YYYY-MM-DD' format
    date_range_end NVARCHAR(10),   -- Changed to NVARCHAR to store 'YYYY-MM-DD' format
    processing_status NVARCHAR(50) DEFAULT 'Pending',
    error_message NVARCHAR(MAX),
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);
GO

-- 2. Catchments Table - Master list of subcatchments
CREATE TABLE dbo.Catchments (
    catchment_id INT IDENTITY(1,1) PRIMARY KEY,
    catchment_name NVARCHAR(100) NOT NULL UNIQUE,
    parent_catchment NVARCHAR(100),
    catchment_code NVARCHAR(20),
    area_km2 DECIMAL(10,2),
    description NVARCHAR(500),
    created_at DATETIME2 DEFAULT GETDATE()
);
GO

-- Insert subcatchments based on Excel sheet names
INSERT INTO dbo.Catchments (catchment_name, parent_catchment, catchment_code, description) VALUES
('Lower Sabie', 'Sabie', 'LSAB', 'Lower Sabie subcatchment'),
('Upper Sabie', 'Sabie', 'USAB', 'Upper Sabie subcatchment'),
('Lower Komati', 'Komati', 'LKOM', 'Lower Komati subcatchment'),
('Upper Komati', 'Komati', 'UKOM', 'Upper Komati subcatchment'),
('Ngwempisi', 'Usuthu', 'NGW', 'Ngwempisi subcatchment'),
('Assegai', 'Usuthu', 'ASS', 'Assegai subcatchment'),
('Sand', 'Sabie-Sand', 'SAND', 'Sand subcatchment'),
('Crocodile', 'Crocodile', 'CRC', 'Crocodile catchment');
GO

-- 3. Raw Data Table - FIXED DATE HANDLING
CREATE TABLE dbo.RawData (
    raw_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    source_id INT FOREIGN KEY REFERENCES dbo.DataSources(source_id),
    catchment_id INT FOREIGN KEY REFERENCES dbo.Catchments(catchment_id),
    measurement_date DATE NOT NULL,  -- CHANGED: Now using proper DATE type
    category NVARCHAR(20) NOT NULL,
    
    -- RECHARGE DATA COLUMNS
    recharge_inches DECIMAL(12,6),
    recharge_converted DECIMAL(12,6),
    average_recharge DECIMAL(12,6),
    recharge_stdev DECIMAL(12,6),
    drought_index_recharge DECIMAL(12,6),
    
    -- BASEFLOW DATA COLUMNS
    baseflow_value DECIMAL(15,8),
    average_baseflow DECIMAL(15,8),
    baseflow_stdev DECIMAL(15,8),
    standardized_baseflow DECIMAL(12,6),
    
    -- GROUNDWATER LEVEL COLUMNS
    gw_level DECIMAL(12,6),
    average_gw_level DECIMAL(12,6),
    gw_level_stdev DECIMAL(12,6),
    standardized_gw_level DECIMAL(12,6),
    
    -- Metadata
    row_number INT,
    original_sheet_name NVARCHAR(100),
    data_quality NVARCHAR(20) DEFAULT 'Good',
    quality_notes NVARCHAR(500),
    created_at DATETIME2 DEFAULT GETDATE(),
    
    -- Indexes
    INDEX IX_RawData_Date_Catchment_Category (measurement_date, catchment_id, category),
    INDEX IX_RawData_Source (source_id)
);
GO

-- 4. Processed Data Table - Unified analysis results
CREATE TABLE dbo.ProcessedData (
    processed_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    raw_id BIGINT FOREIGN KEY REFERENCES dbo.RawData(raw_id),
    source_id INT FOREIGN KEY REFERENCES dbo.DataSources(source_id),
    catchment_id INT FOREIGN KEY REFERENCES dbo.Catchments(catchment_id),
    measurement_date DATE NOT NULL,
    parameter_type NVARCHAR(20) NOT NULL,
    
    -- Primary value and standardized score
    original_value DECIMAL(15,8),
    mean_value DECIMAL(15,8),
    std_deviation DECIMAL(15,8),
    standardized_value DECIMAL(12,6),
    
    -- Classification based on standardized value thresholds
    classification NVARCHAR(30),
    is_failure BIT,
    severity_level TINYINT,
    
    -- Drought index (for recharge data)
    drought_index DECIMAL(12,6),
    
    processing_date DATETIME2 DEFAULT GETDATE(),
    
    -- Indexes for performance
    INDEX IX_ProcessedData_Date_Catchment_Type (measurement_date, catchment_id, parameter_type),
    INDEX IX_ProcessedData_Classifications (classification),
    INDEX IX_ProcessedData_Failures (is_failure, parameter_type)
);
GO

-- 5. Performance Metrics Table
CREATE TABLE dbo.PerformanceMetrics (
    metrics_id INT IDENTITY(1,1) PRIMARY KEY,
    source_id INT FOREIGN KEY REFERENCES dbo.DataSources(source_id),
    catchment_id INT FOREIGN KEY REFERENCES dbo.Catchments(catchment_id),
    parameter_type NVARCHAR(20) CHECK (parameter_type IN ('Recharge', 'Baseflow', 'GWLevel')),
    
    -- Date range for analysis
    analysis_start_date DATE,
    analysis_end_date DATE,
    total_records INT,
    
    -- Performance metrics based on Shakhane et al. formulas
    reliability DECIMAL(6,4),
    resilience DECIMAL(8,6),
    vulnerability DECIMAL(6,4),
    sustainability DECIMAL(6,4),
    
    -- Failure statistics
    total_failures INT,
    failure_sequences INT,
    avg_failure_duration DECIMAL(6,2),
    max_failure_duration INT,
    avg_failure_severity DECIMAL(8,4),
    max_failure_severity DECIMAL(8,4),
    
    -- Additional metrics
    failure_intensity DECIMAL(8,4),
    failure_return_period DECIMAL(8,2),
    
    -- Confidence intervals (95%)
    reliability_ci_lower DECIMAL(6,4),
    reliability_ci_upper DECIMAL(6,4),
    
    calculation_date DATETIME2 DEFAULT GETDATE(),
    
    UNIQUE (source_id, catchment_id, parameter_type, analysis_start_date, analysis_end_date)
);
GO

-- Updated Views
CREATE VIEW vw_LatestProcessedData AS
SELECT 
    pd.processed_id,
    pd.measurement_date,
    c.catchment_name,
    c.parent_catchment,
    c.catchment_code,
    ds.file_name,
    ds.category,
    pd.parameter_type,
    pd.original_value,
    pd.standardized_value,
    pd.classification,
    pd.is_failure,
    pd.severity_level,
    pd.drought_index,
    pd.processing_date
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
INNER JOIN dbo.DataSources ds ON pd.source_id = ds.source_id
WHERE ds.processing_status IN ('Completed', 'Completed with Errors');
GO

-- View: Raw data with proper structure
CREATE VIEW vw_RawDataStructured AS
SELECT 
    rd.raw_id,
    rd.measurement_date,
    c.catchment_name,
    c.parent_catchment,
    ds.file_name,
    rd.category,
    
    -- Unified value extraction based on category
    CASE 
        WHEN rd.category = 'Recharge' THEN rd.recharge_converted
        WHEN rd.category = 'Baseflow' THEN rd.baseflow_value
        WHEN rd.category = 'GWLevel' THEN rd.gw_level
    END as primary_value,
    
    CASE 
        WHEN rd.category = 'Recharge' THEN rd.average_recharge
        WHEN rd.category = 'Baseflow' THEN rd.average_baseflow
        WHEN rd.category = 'GWLevel' THEN rd.average_gw_level
    END as average_value,
    
    CASE 
        WHEN rd.category = 'Recharge' THEN rd.recharge_stdev
        WHEN rd.category = 'Baseflow' THEN rd.baseflow_stdev
        WHEN rd.category = 'GWLevel' THEN rd.gw_level_stdev
    END as std_deviation,
    
    CASE 
        WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
        WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
        WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
    END as standardized_value,
    
    rd.original_sheet_name,
    rd.created_at
FROM dbo.RawData rd
INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
INNER JOIN dbo.DataSources ds ON rd.source_id = ds.source_id;
GO

-- Updated stored procedure for processing
CREATE PROCEDURE sp_ProcessRawData
    @SourceId INT
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @ProcessedCount INT = 0;
    
    -- Process each category of data
    INSERT INTO dbo.ProcessedData (
        raw_id, source_id, catchment_id, measurement_date, parameter_type,
        original_value, mean_value, std_deviation, standardized_value,
        drought_index, classification, is_failure, severity_level
    )
    SELECT 
        rd.raw_id,
        rd.source_id,
        rd.catchment_id,
        rd.measurement_date,  -- Now it's already a DATE type, no conversion needed
        rd.category as parameter_type,
        
        -- Extract primary value based on category
        CASE 
            WHEN rd.category = 'Recharge' THEN rd.recharge_converted
            WHEN rd.category = 'Baseflow' THEN rd.baseflow_value
            WHEN rd.category = 'GWLevel' THEN rd.gw_level
        END as original_value,
        
        -- Extract mean value
        CASE 
            WHEN rd.category = 'Recharge' THEN rd.average_recharge
            WHEN rd.category = 'Baseflow' THEN rd.average_baseflow
            WHEN rd.category = 'GWLevel' THEN rd.average_gw_level
        END as mean_value,
        
        -- Extract standard deviation
        CASE 
            WHEN rd.category = 'Recharge' THEN rd.recharge_stdev
            WHEN rd.category = 'Baseflow' THEN rd.baseflow_stdev
            WHEN rd.category = 'GWLevel' THEN rd.gw_level_stdev
        END as std_deviation,
        
        -- Use existing standardized value
        CASE 
            WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
            WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
            WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
        END as standardized_value,
        
        -- Drought index (mainly for recharge)
        rd.drought_index_recharge,
        
        -- Classify based on standardized value (Z-score thresholds)
        CASE 
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END > 0.5 THEN 'Surplus'
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END BETWEEN -0.5 AND 0.5 THEN 'Normal'
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END BETWEEN -1.0 AND -0.5 THEN 'Moderate_Deficit'
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END BETWEEN -1.5 AND -1.0 THEN 'Severe_Deficit'
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END < -1.5 THEN 'Extreme_Deficit'
            ELSE 'Normal'
        END as classification,
        
        -- Failure flag (< -0.5 is considered failure)
        CASE 
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END < -0.5 THEN 1 
            ELSE 0 
        END as is_failure,
        
        -- Severity level
        CASE 
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END > 0.5 THEN -1 -- Surplus
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END BETWEEN -0.5 AND 0.5 THEN 0 -- Normal
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END BETWEEN -1.0 AND -0.5 THEN 1 -- Moderate
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END BETWEEN -1.5 AND -1.0 THEN 2 -- Severe
            WHEN CASE 
                WHEN rd.category = 'Recharge' THEN rd.drought_index_recharge
                WHEN rd.category = 'Baseflow' THEN rd.standardized_baseflow
                WHEN rd.category = 'GWLevel' THEN rd.standardized_gw_level
            END < -1.5 THEN 3 -- Extreme
            ELSE 0
        END as severity_level
        
    FROM dbo.RawData rd
    WHERE rd.source_id = @SourceId
      AND NOT EXISTS (
          SELECT 1 FROM dbo.ProcessedData pd 
          WHERE pd.raw_id = rd.raw_id
      );
    
    SET @ProcessedCount = @@ROWCOUNT;
     
    -- Update source status
    UPDATE dbo.DataSources 
    SET processing_status = 'Completed',
        updated_at = GETDATE()
    WHERE source_id = @SourceId;
    
    PRINT 'Processed ' + CAST(@ProcessedCount AS VARCHAR(10)) + ' records for source ' + CAST(@SourceId AS VARCHAR(10));
END;
GO

PRINT 'Fixed database schema created successfully!';
PRINT 'Key changes:';
PRINT '- RawData.measurement_date is now DATE type (not NVARCHAR)';
PRINT '- DataSources date range fields are NVARCHAR for flexibility';
PRINT '- All date handling is now consistent across tables';
PRINT '- Stored procedure updated to handle proper DATE types';
GO