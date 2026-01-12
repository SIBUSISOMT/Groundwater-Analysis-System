-- ============================================================================
-- COMPLETE GROUNDWATER ANALYSIS DATABASE SETUP SCRIPT - UPDATED
-- ============================================================================
-- Creates database from scratch and adds all tables, constraints, and views
-- for the groundwater analysis system with deviation column support
-- ✅ INCLUDES subcatchment_name field in DataSources table
--
-- Usage: 
-- 1. Connect to SQL Server (Master database)
-- 2. Run entire script
-- ============================================================================

-- ============================================================================
-- STEP 1: CREATE DATABASE
-- ============================================================================

-- Drop database if exists (optional - comment out to preserve existing data)
IF EXISTS (SELECT * FROM sys.databases WHERE name = 'GroundwaterAnalysis')
BEGIN
    ALTER DATABASE GroundwaterAnalysis SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE GroundwaterAnalysis;
    PRINT 'Dropped existing GroundwaterAnalysis database';
END
GO

-- Create the database
CREATE DATABASE GroundwaterAnalysis;
PRINT 'Created GroundwaterAnalysis database';
GO

USE GroundwaterAnalysis;
GO

-- ============================================================================
-- STEP 2: CREATE TABLES
-- ============================================================================

-- Table: Catchments
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Catchments')
BEGIN
    CREATE TABLE dbo.Catchments (
        catchment_id INT PRIMARY KEY IDENTITY(1,1),
        catchment_name NVARCHAR(255) NOT NULL UNIQUE,
        parent_catchment NVARCHAR(255),
        description NVARCHAR(MAX),
        location NVARCHAR(255),
        area_sqkm FLOAT,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );
    PRINT 'Created Catchments table';
END
GO

-- Table: DataSources (✅ UPDATED - includes subcatchment_name)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DataSources')
BEGIN
    CREATE TABLE dbo.DataSources (
        source_id INT PRIMARY KEY IDENTITY(1,1),
        file_name NVARCHAR(255) NOT NULL,
        category NVARCHAR(50) NOT NULL,
        subcatchment_name NVARCHAR(255),           -- ✅ NEW FIELD
        upload_date DATETIME DEFAULT GETDATE(),
        processing_status NVARCHAR(50) DEFAULT 'Pending',
        error_message NVARCHAR(MAX), 
        records_processed INT DEFAULT 0,
        date_range_start DATE,
        date_range_end DATE,
        updated_at DATETIME DEFAULT GETDATE()
    );
    PRINT 'Created DataSources table with subcatchment_name field';
END
GO

-- Table: RawData
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'RawData')
BEGIN
    CREATE TABLE dbo.RawData (
        raw_id INT PRIMARY KEY IDENTITY(1,1),
        source_id INT NOT NULL,
        catchment_id INT NOT NULL,
        measurement_date DATE NOT NULL,
        category NVARCHAR(50) NOT NULL,
        original_sheet_name NVARCHAR(255),
        
        -- Recharge columns
        recharge_inches FLOAT,
        recharge_converted FLOAT,
        average_recharge FLOAT,
        recharge_stdev FLOAT,
        drought_index_recharge FLOAT,
        recharge_deviation FLOAT,
        
        -- Baseflow columns
        baseflow_value FLOAT,
        average_baseflow FLOAT,
        baseflow_stdev FLOAT,
        standardized_baseflow FLOAT,
        baseflow_deviation FLOAT,
        
        -- GW Level columns
        gw_level FLOAT,
        average_gw_level FLOAT,
        gw_level_stdev FLOAT,
        standardized_gw_level FLOAT,
        gw_level_deviation FLOAT,
        
        created_at DATETIME DEFAULT GETDATE(),
        FOREIGN KEY (source_id) REFERENCES dbo.DataSources(source_id),
        FOREIGN KEY (catchment_id) REFERENCES dbo.Catchments(catchment_id)
    );
    PRINT 'Created RawData table';
END
GO

-- Table: ProcessedData
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ProcessedData')
BEGIN
    CREATE TABLE dbo.ProcessedData (
        processed_id INT PRIMARY KEY IDENTITY(1,1),
        raw_id INT NOT NULL,
        source_id INT NOT NULL,
        catchment_id INT NOT NULL,
        measurement_date DATE NOT NULL,
        parameter_type NVARCHAR(50) NOT NULL,
        original_value FLOAT,
        mean_value FLOAT,
        std_deviation FLOAT,
        standardized_value FLOAT,
        parameter_deviation FLOAT,
        drought_index FLOAT,
        classification NVARCHAR(50),
        is_failure BIT DEFAULT 0,
        severity_level INT,
        created_at DATETIME DEFAULT GETDATE(),
        FOREIGN KEY (raw_id) REFERENCES dbo.RawData(raw_id),
        FOREIGN KEY (source_id) REFERENCES dbo.DataSources(source_id),
        FOREIGN KEY (catchment_id) REFERENCES dbo.Catchments(catchment_id)
    );
    PRINT 'Created ProcessedData table';
END
GO

-- Table: PerformanceMetrics
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PerformanceMetrics')
BEGIN
    CREATE TABLE dbo.PerformanceMetrics (
        metric_id INT PRIMARY KEY IDENTITY(1,1),
        catchment_id INT NOT NULL,
        parameter_type NVARCHAR(50) NOT NULL,
        metric_date DATE,
        drought_severity_index FLOAT,
        failure_rate FLOAT,
        days_below_threshold INT,
        avg_value FLOAT,
        min_value FLOAT,
        max_value FLOAT,
        created_at DATETIME DEFAULT GETDATE(),
        FOREIGN KEY (catchment_id) REFERENCES dbo.Catchments(catchment_id)
    );
    PRINT 'Created PerformanceMetrics table';
END
GO

-- ============================================================================
-- STEP 3: CREATE INDEXES
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_RawData_MeasurementDate')
    CREATE INDEX idx_RawData_MeasurementDate ON dbo.RawData(measurement_date);
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_RawData_Category')
    CREATE INDEX idx_RawData_Category ON dbo.RawData(category);
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_ProcessedData_MeasurementDate')
    CREATE INDEX idx_ProcessedData_MeasurementDate ON dbo.ProcessedData(measurement_date);
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_ProcessedData_ParameterType')
    CREATE INDEX idx_ProcessedData_ParameterType ON dbo.ProcessedData(parameter_type);
GO

-- ✅ NEW: Index on subcatchment_name for faster filtering
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_DataSources_Subcatchment')
    CREATE INDEX idx_DataSources_Subcatchment ON dbo.DataSources(subcatchment_name);
GO

PRINT 'Created indexes';
GO

-- ============================================================================
-- STEP 4: CREATE CHECK CONSTRAINTS (Case-Insensitive)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CHK_DataSources_Category')
BEGIN
    ALTER TABLE dbo.DataSources
    ADD CONSTRAINT CHK_DataSources_Category 
    CHECK (LOWER(category) IN ('recharge', 'baseflow', 'gwlevel'));
    PRINT 'Added category constraint to DataSources';
END
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CHK_PerformanceMetrics_ParameterType')
BEGIN
    ALTER TABLE dbo.PerformanceMetrics
    ADD CONSTRAINT CHK_PerformanceMetrics_ParameterType 
    CHECK (LOWER(parameter_type) IN ('recharge', 'baseflow', 'gwlevel'));
    PRINT 'Added parameter_type constraint to PerformanceMetrics';
END
GO

-- ============================================================================
-- STEP 5: CREATE VIEWS
-- ============================================================================

IF OBJECT_ID('dbo.vw_RawDataStructured', 'V') IS NOT NULL
    DROP VIEW dbo.vw_RawDataStructured;
GO

CREATE VIEW vw_RawDataStructured AS
SELECT 
    rd.raw_id,
    rd.measurement_date,
    c.catchment_name,
    c.parent_catchment,
    ds.file_name,
    ds.subcatchment_name,      -- ✅ ADDED to view
    rd.category,
    
    CASE 
        WHEN LOWER(rd.category) = 'recharge' THEN rd.recharge_converted
        WHEN LOWER(rd.category) = 'baseflow' THEN rd.baseflow_value
        WHEN LOWER(rd.category) = 'gwlevel' THEN rd.gw_level
    END as primary_value,
    
    CASE 
        WHEN LOWER(rd.category) = 'recharge' THEN rd.average_recharge
        WHEN LOWER(rd.category) = 'baseflow' THEN rd.average_baseflow
        WHEN LOWER(rd.category) = 'gwlevel' THEN rd.average_gw_level
    END as average_value,
    
    CASE 
        WHEN LOWER(rd.category) = 'recharge' THEN rd.recharge_stdev
        WHEN LOWER(rd.category) = 'baseflow' THEN rd.baseflow_stdev
        WHEN LOWER(rd.category) = 'gwlevel' THEN rd.gw_level_stdev
    END as std_deviation,
    
    CASE 
        WHEN LOWER(rd.category) = 'recharge' THEN rd.recharge_deviation
        WHEN LOWER(rd.category) = 'baseflow' THEN rd.baseflow_deviation
        WHEN LOWER(rd.category) = 'gwlevel' THEN rd.gw_level_deviation
    END as parameter_deviation,
    
    CASE 
        WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
        WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
        WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
    END as standardized_value,
    
    rd.original_sheet_name,
    rd.created_at
FROM dbo.RawData rd
INNER JOIN dbo.Catchments c ON rd.catchment_id = c.catchment_id
INNER JOIN dbo.DataSources ds ON rd.source_id = ds.source_id;
GO

PRINT 'Created vw_RawDataStructured view';
GO

-- ============================================================================
-- STEP 6: CREATE STORED PROCEDURES
-- ============================================================================

IF OBJECT_ID('dbo.sp_ProcessRawData', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_ProcessRawData;
GO

CREATE PROCEDURE sp_ProcessRawData
    @SourceId INT
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @ProcessedCount INT = 0;
    
    INSERT INTO dbo.ProcessedData (
        raw_id, source_id, catchment_id, measurement_date, parameter_type,
        original_value, mean_value, std_deviation, standardized_value,
        parameter_deviation, drought_index, classification, is_failure, severity_level
    )
    SELECT
        rd.raw_id,
        rd.source_id,
        rd.catchment_id,
        rd.measurement_date,
        LOWER(rd.category) as parameter_type,
        
        CASE 
            WHEN LOWER(rd.category) = 'recharge' THEN rd.recharge_converted
            WHEN LOWER(rd.category) = 'baseflow' THEN rd.baseflow_value
            WHEN LOWER(rd.category) = 'gwlevel' THEN rd.gw_level
        END as original_value,
        
        CASE 
            WHEN LOWER(rd.category) = 'recharge' THEN rd.average_recharge
            WHEN LOWER(rd.category) = 'baseflow' THEN rd.average_baseflow
            WHEN LOWER(rd.category) = 'gwlevel' THEN rd.average_gw_level
        END as mean_value,
        
        CASE 
            WHEN LOWER(rd.category) = 'recharge' THEN rd.recharge_stdev
            WHEN LOWER(rd.category) = 'baseflow' THEN rd.baseflow_stdev
            WHEN LOWER(rd.category) = 'gwlevel' THEN rd.gw_level_stdev
        END as std_deviation,
        
        CASE 
            WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
            WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
            WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
        END as standardized_value,
        
        CASE 
            WHEN LOWER(rd.category) = 'recharge' THEN rd.recharge_deviation
            WHEN LOWER(rd.category) = 'baseflow' THEN rd.baseflow_deviation
            WHEN LOWER(rd.category) = 'gwlevel' THEN rd.gw_level_deviation
        END as parameter_deviation,
        
        rd.drought_index_recharge,
        
        CASE 
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END > 0.5 THEN 'Surplus'
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END BETWEEN -0.5 AND 0.5 THEN 'Normal'
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END BETWEEN -1.0 AND -0.5 THEN 'Moderate_Deficit'
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END BETWEEN -1.5 AND -1.0 THEN 'Severe_Deficit'
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END < -1.5 THEN 'Extreme_Deficit'
            ELSE 'Normal'
        END as classification,
        
        CASE 
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END < -0.5 THEN 1 
            ELSE 0 
        END as is_failure,
        
        CASE 
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END > 0.5 THEN -1
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END BETWEEN -0.5 AND 0.5 THEN 0
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END BETWEEN -1.0 AND -0.5 THEN 1
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END BETWEEN -1.5 AND -1.0 THEN 2
            WHEN CASE 
                WHEN LOWER(rd.category) = 'recharge' THEN rd.drought_index_recharge
                WHEN LOWER(rd.category) = 'baseflow' THEN rd.standardized_baseflow
                WHEN LOWER(rd.category) = 'gwlevel' THEN rd.standardized_gw_level
            END < -1.5 THEN 3
            ELSE 0
        END as severity_level
        
    FROM dbo.RawData rd
    WHERE rd.source_id = @SourceId
      AND NOT EXISTS (
          SELECT 1 FROM dbo.ProcessedData pd 
          WHERE pd.raw_id = rd.raw_id
      );
    
    SET @ProcessedCount = @@ROWCOUNT;
     
    UPDATE dbo.DataSources 
    SET processing_status = 'Completed',
        updated_at = GETDATE()
    WHERE source_id = @SourceId;
    
    PRINT 'Processed ' + CAST(@ProcessedCount AS VARCHAR(10)) + ' records for source ' + CAST(@SourceId AS VARCHAR(10));
END;
GO

PRINT 'Created sp_ProcessRawData procedure';
GO

-- ============================================================================
-- STEP 7: INSERT SAMPLE CATCHMENT DATA
-- ============================================================================

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Crocodile')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Crocodile', 'Limpopo', 'Crocodile River Catchment');
    PRINT 'Inserted sample catchment: Crocodile';
END

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Assegai')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Assegai', 'Limpopo', 'Assegai River Catchment');
    PRINT 'Inserted sample catchment: Assegai';
END

-- ✅ NEW: Add more catchments referenced in your frontend
IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Lower Komati')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Lower Komati', 'Inkomati', 'Lower Komati River Catchment');
    PRINT 'Inserted sample catchment: Lower Komati';
END

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Lower Sabie')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Lower Sabie', 'Inkomati', 'Lower Sabie River Catchment');
    PRINT 'Inserted sample catchment: Lower Sabie';
END

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Ngwempisi')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Ngwempisi', 'Inkomati', 'Ngwempisi River Catchment');
    PRINT 'Inserted sample catchment: Ngwempisi';
END

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Sand')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Sand', 'Inkomati', 'Sand River Catchment');
    PRINT 'Inserted sample catchment: Sand';
END

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Upper Komati')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Upper Komati', 'Inkomati', 'Upper Komati River Catchment');
    PRINT 'Inserted sample catchment: Upper Komati';
END

IF NOT EXISTS (SELECT * FROM dbo.Catchments WHERE catchment_name = 'Upper Sabie')
BEGIN
    INSERT INTO dbo.Catchments (catchment_name, parent_catchment, description)
    VALUES ('Upper Sabie', 'Inkomati', 'Upper Sabie River Catchment');
    PRINT 'Inserted sample catchment: Upper Sabie';
END
GO

PRINT '';
PRINT '========================================';
PRINT 'DATABASE SETUP COMPLETE!';
PRINT '========================================';
PRINT 'Database: GroundwaterAnalysis';
PRINT 'Tables created:';
PRINT '  - Catchments (8 sample catchments)';
PRINT '  - DataSources (✅ with subcatchment_name field)';
PRINT '  - RawData (with deviation columns)';
PRINT '  - ProcessedData (with parameter_deviation)';
PRINT '  - PerformanceMetrics';
PRINT '';
PRINT 'Views created:';
PRINT '  - vw_RawDataStructured (✅ includes subcatchment_name)';
PRINT '';
PRINT 'Procedures created:';
PRINT '  - sp_ProcessRawData';
PRINT '';
PRINT 'Indexes created:';
PRINT '  - Standard performance indexes';
PRINT '  - ✅ Index on subcatchment_name';
PRINT '';
PRINT 'Ready to accept:';
PRINT '  - Recharge deviation (recharge_deviation)';
PRINT '  - Baseflow deviation (baseflow_deviation)';
PRINT '  - GW Level deviation (gw_level_deviation)';
PRINT '  - ✅ Subcatchment tracking (subcatchment_name)';
PRINT '========================================';
GO