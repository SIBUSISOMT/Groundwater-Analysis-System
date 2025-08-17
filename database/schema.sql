-- Groundwater Analysis System Database Schema
-- Based on Shakhane et al. methodology

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
    upload_date DATETIME2 DEFAULT GETDATE(),
    file_size_kb INT,
    total_records INT,
    date_range_start DATE,
    date_range_end DATE,
    processing_status NVARCHAR(50) DEFAULT 'Pending', -- Pending, Processing, Completed, Failed
    error_message NVARCHAR(MAX),
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);
GO

-- 2. Catchments Table - Master list of catchments
CREATE TABLE dbo.Catchments (
    catchment_id INT IDENTITY(1,1) PRIMARY KEY,
    catchment_name NVARCHAR(100) NOT NULL UNIQUE,
    catchment_code NVARCHAR(20),
    area_km2 DECIMAL(10,2),
    description NVARCHAR(500),
    created_at DATETIME2 DEFAULT GETDATE()
);
GO

-- Insert default catchments from the study
INSERT INTO dbo.Catchments (catchment_name, catchment_code, area_km2, description) VALUES
('Crocodile', 'CRC', 10446, 'Crocodile River catchment draining into Mozambique'),
('Komati', 'KOM', 8621, 'Komati River catchment flowing through eSwatini'),
('Sabie-Sand', 'SAB', 9304, 'Sabie-Sand catchment in the eastern region'),
('Usuthu', 'USU', 7915, 'Usuthu catchment shared with eSwatini'),
('Upper Komati', 'UKOM', NULL, 'Upper section of Komati catchment'),
('Lower Komati', 'LKOM', NULL, 'Lower section of Komati catchment'),
('Ngwempisi', 'NGW', NULL, 'Ngwempisi sub-catchment of Usuthu'),
('Assegai', 'ASS', NULL, 'Assegai sub-catchment of Usuthu'),
('Sabie', 'SAB1', NULL, 'Sabie sub-catchment'),
('Sand', 'SAND', NULL, 'Sand sub-catchment');
GO

-- 3. Raw Data Table - Original Excel data
CREATE TABLE dbo.RawData (
    raw_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    source_id INT FOREIGN KEY REFERENCES dbo.DataSources(source_id),
    catchment_id INT FOREIGN KEY REFERENCES dbo.Catchments(catchment_id),
    measurement_date DATE NOT NULL,
    
    -- Groundwater parameters (original values)
    gwr_mm DECIMAL(10,4), -- Groundwater Recharge in mm
    gwl_m DECIMAL(10,4),  -- Groundwater Level in meters
    gwb_m3s DECIMAL(12,6), -- Groundwater Baseflow in m³/s
    
    -- Additional optional fields
    rainfall_mm DECIMAL(8,2),
    temperature_c DECIMAL(5,2),
    
    -- Metadata
    row_number INT,
    data_quality NVARCHAR(20) DEFAULT 'Good', -- Good, Warning, Poor
    quality_notes NVARCHAR(500),
    created_at DATETIME2 DEFAULT GETDATE(),
    
    -- Composite index for performance
    INDEX IX_RawData_Date_Catchment (measurement_date, catchment_id),
    INDEX IX_RawData_Source (source_id)
);
GO

-- 4. Processed Data Table - Z-score normalized and classified data
CREATE TABLE dbo.ProcessedData (
    processed_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    raw_id BIGINT FOREIGN KEY REFERENCES dbo.RawData(raw_id),
    source_id INT FOREIGN KEY REFERENCES dbo.DataSources(source_id),
    catchment_id INT FOREIGN KEY REFERENCES dbo.Catchments(catchment_id),
    measurement_date DATE NOT NULL,
    
    -- Original values
    gwr_original DECIMAL(10,4),
    gwl_original DECIMAL(10,4),
    gwb_original DECIMAL(12,6),
    
    -- Statistical parameters for normalization
    gwr_mean DECIMAL(10,4),
    gwr_stddev DECIMAL(10,4),
    gwl_mean DECIMAL(10,4),
    gwl_stddev DECIMAL(10,4),
    gwb_mean DECIMAL(12,6),
    gwb_stddev DECIMAL(12,6),
    
    -- Z-scores (Equation 3: Z = (p - p̄) / σ)
    gwr_zscore DECIMAL(8,4),
    gwl_zscore DECIMAL(8,4),
    gwb_zscore DECIMAL(8,4),
    
    -- Classification based on thresholds
    gwr_classification NVARCHAR(20), -- Normal, Moderate_Deficit, Severe_Deficit, Extreme_Deficit, Surplus
    gwl_classification NVARCHAR(20),
    gwb_classification NVARCHAR(20),
    
    -- Failure indicators
    gwr_is_failure BIT, -- 1 if z-score < -0.5
    gwl_is_failure BIT,
    gwb_is_failure BIT,
    
    -- Severity levels (0=Normal, 1=Moderate, 2=Severe, 3=Extreme, -1=Surplus)
    gwr_severity_level TINYINT,
    gwl_severity_level TINYINT,
    gwb_severity_level TINYINT,
    
    processing_date DATETIME2 DEFAULT GETDATE(),
    
    -- Indexes for performance
    INDEX IX_ProcessedData_Date_Catchment (measurement_date, catchment_id),
    INDEX IX_ProcessedData_Classifications (gwr_classification, gwl_classification, gwb_classification),
    INDEX IX_ProcessedData_Failures (gwr_is_failure, gwl_is_failure, gwb_is_failure)
);
GO

-- 5. Performance Metrics Table - Calculated reliability, resilience, vulnerability
CREATE TABLE dbo.PerformanceMetrics (
    metrics_id INT IDENTITY(1,1) PRIMARY KEY,
    source_id INT FOREIGN KEY REFERENCES dbo.DataSources(source_id),
    catchment_id INT FOREIGN KEY REFERENCES dbo.Catchments(catchment_id),
    parameter_type NVARCHAR(10) CHECK (parameter_type IN ('GWR', 'GWL', 'GWB')),
    
    -- Date range for analysis
    analysis_start_date DATE,
    analysis_end_date DATE,
    total_records INT,
    
    -- Performance metrics based on Shakhane et al. formulas
    reliability DECIMAL(6,4), -- Probability of satisfactory performance
    resilience DECIMAL(8,6),  -- Recovery speed (Equation 8)
    vulnerability DECIMAL(6,4), -- Average severity of failures (Equations 9-10)
    sustainability DECIMAL(6,4), -- Combined index (Equation 11)
    
    -- Failure statistics
    total_failures INT,
    failure_sequences INT, -- Number of continuous failure periods
    avg_failure_duration DECIMAL(6,2),
    max_failure_duration INT,
    avg_failure_severity DECIMAL(8,4),
    max_failure_severity DECIMAL(8,4),
    
    -- Failure intensity and return periods
    failure_intensity DECIMAL(8,4), -- Equation 4: Fm = Σ|SI| / (tn - tp)
    failure_return_period DECIMAL(8,2), -- Equation 6: T(x) = 1/[(1-F(x))RF]
    
    -- Confidence intervals (95%)
    reliability_ci_lower DECIMAL(6,4),
    reliability_ci_upper DECIMAL(6,4),
    
    calculation_date DATETIME2 DEFAULT GETDATE(),
    
    -- Unique constraint to prevent duplicates
    UNIQUE (source_id, catchment_id, parameter_type, analysis_start_date, analysis_end_date)
);
GO

-- 6. Create views for easy data access

-- View: Latest processed data with catchment names
CREATE VIEW vw_LatestProcessedData AS
SELECT 
    pd.processed_id,
    pd.measurement_date,
    c.catchment_name,
    c.catchment_code,
    ds.file_name,
    
    -- Original values
    pd.gwr_original,
    pd.gwl_original, 
    pd.gwb_original,
    
    -- Z-scores
    pd.gwr_zscore,
    pd.gwl_zscore,
    pd.gwb_zscore,
    
    -- Classifications
    pd.gwr_classification,
    pd.gwl_classification,
    pd.gwb_classification,
    
    -- Failure flags
    pd.gwr_is_failure,
    pd.gwl_is_failure,
    pd.gwb_is_failure,
    
    pd.processing_date
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
INNER JOIN dbo.DataSources ds ON pd.source_id = ds.source_id
WHERE ds.processing_status = 'Completed';
GO

-- View: Performance summary by catchment
CREATE VIEW vw_PerformanceSummary AS
SELECT 
    c.catchment_name,
    pm.parameter_type,
    pm.analysis_start_date,
    pm.analysis_end_date,
    pm.total_records,
    pm.reliability,
    pm.resilience,
    pm.vulnerability,
    pm.sustainability,
    pm.total_failures,
    pm.avg_failure_duration,
    pm.failure_return_period,
    pm.calculation_date
FROM dbo.PerformanceMetrics pm
INNER JOIN dbo.Catchments c ON pm.catchment_id = c.catchment_id;
GO

-- View: Failure analysis
CREATE VIEW vw_FailureAnalysis AS
SELECT 
    c.catchment_name,
    YEAR(pd.measurement_date) as year,
    MONTH(pd.measurement_date) as month,
    COUNT(*) as total_records,
    
    -- GWR failures
    SUM(CASE WHEN pd.gwr_is_failure = 1 THEN 1 ELSE 0 END) as gwr_failures,
    AVG(CASE WHEN pd.gwr_is_failure = 1 THEN ABS(pd.gwr_zscore) END) as gwr_avg_severity,
    
    -- GWL failures  
    SUM(CASE WHEN pd.gwl_is_failure = 1 THEN 1 ELSE 0 END) as gwl_failures,
    AVG(CASE WHEN pd.gwl_is_failure = 1 THEN ABS(pd.gwl_zscore) END) as gwl_avg_severity,
    
    -- GWB failures
    SUM(CASE WHEN pd.gwb_is_failure = 1 THEN 1 ELSE 0 END) as gwb_failures,
    AVG(CASE WHEN pd.gwb_is_failure = 1 THEN ABS(pd.gwb_zscore) END) as gwb_avg_severity
    
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
GROUP BY c.catchment_name, YEAR(pd.measurement_date), MONTH(pd.measurement_date);
GO

-- 7. Stored procedures for common operations

-- Procedure: Get data for date range and parameters
CREATE PROCEDURE sp_GetDataForAnalysis
    @CatchmentName NVARCHAR(100) = NULL,
    @StartDate DATE,
    @EndDate DATE,
    @ParameterType NVARCHAR(10) = 'GWR' -- GWR, GWL, or GWB
AS
BEGIN
    SET NOCOUNT ON;
    
    SELECT 
        pd.measurement_date,
        c.catchment_name,
        CASE 
            WHEN @ParameterType = 'GWR' THEN pd.gwr_original
            WHEN @ParameterType = 'GWL' THEN pd.gwl_original  
            WHEN @ParameterType = 'GWB' THEN pd.gwb_original
        END as original_value,
        CASE 
            WHEN @ParameterType = 'GWR' THEN pd.gwr_zscore
            WHEN @ParameterType = 'GWL' THEN pd.gwl_zscore
            WHEN @ParameterType = 'GWB' THEN pd.gwb_zscore
        END as zscore,
        CASE 
            WHEN @ParameterType = 'GWR' THEN pd.gwr_classification
            WHEN @ParameterType = 'GWL' THEN pd.gwl_classification
            WHEN @ParameterType = 'GWB' THEN pd.gwb_classification
        END as classification,
        CASE 
            WHEN @ParameterType = 'GWR' THEN pd.gwr_is_failure
            WHEN @ParameterType = 'GWL' THEN pd.gwl_is_failure
            WHEN @ParameterType = 'GWB' THEN pd.gwb_is_failure
        END as is_failure
    FROM dbo.ProcessedData pd
    INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
    WHERE pd.measurement_date BETWEEN @StartDate AND @EndDate
      AND (@CatchmentName IS NULL OR c.catchment_name = @CatchmentName)
    ORDER BY pd.measurement_date;
END;
GO

-- Procedure: Calculate and store performance metrics
CREATE PROCEDURE sp_CalculatePerformanceMetrics
    @SourceId INT,
    @CatchmentId INT = NULL,
    @ParameterType NVARCHAR(10) = 'GWR',
    @StartDate DATE = NULL,
    @EndDate DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @TotalRecords INT;
    DECLARE @TotalFailures INT;
    DECLARE @Reliability DECIMAL(6,4);
    DECLARE @Vulnerability DECIMAL(6,4);
    DECLARE @AvgFailureSeverity DECIMAL(8,4);
    DECLARE @MaxFailureSeverity DECIMAL(8,4);
    
    -- Get the appropriate failure column and z-score column
    DECLARE @FailureColumn NVARCHAR(20) = @ParameterType + '_is_failure';
    DECLARE @ZScoreColumn NVARCHAR(20) = @ParameterType + '_zscore';
    
    -- Build dynamic query for flexibility
    DECLARE @SQL NVARCHAR(MAX);
    
    SET @SQL = N'
    SELECT @TotalRecords = COUNT(*),
           @TotalFailures = SUM(CASE WHEN ' + @FailureColumn + ' = 1 THEN 1 ELSE 0 END),
           @AvgFailureSeverity = AVG(CASE WHEN ' + @FailureColumn + ' = 1 THEN ABS(' + @ZScoreColumn + ') END),
           @MaxFailureSeverity = MAX(CASE WHEN ' + @FailureColumn + ' = 1 THEN ABS(' + @ZScoreColumn + ') END)
    FROM dbo.ProcessedData 
    WHERE source_id = @SourceId';
    
    IF @CatchmentId IS NOT NULL
        SET @SQL += N' AND catchment_id = @CatchmentId';
        
    IF @StartDate IS NOT NULL
        SET @SQL += N' AND measurement_date >= @StartDate';
        
    IF @EndDate IS NOT NULL  
        SET @SQL += N' AND measurement_date <= @EndDate';
    
    EXEC sp_executesql @SQL, 
        N'@SourceId INT, @CatchmentId INT, @StartDate DATE, @EndDate DATE, @TotalRecords INT OUTPUT, @TotalFailures INT OUTPUT, @AvgFailureSeverity DECIMAL(8,4) OUTPUT, @MaxFailureSeverity DECIMAL(8,4) OUTPUT',
        @SourceId, @CatchmentId, @StartDate, @EndDate, @TotalRecords OUTPUT, @TotalFailures OUTPUT, @AvgFailureSeverity OUTPUT, @MaxFailureSeverity OUTPUT;
    
    -- Calculate reliability
    SET @Reliability = CASE WHEN @TotalRecords > 0 THEN CAST(@TotalRecords - @TotalFailures AS DECIMAL(6,4)) / @TotalRecords ELSE 0 END;
    
    -- Calculate vulnerability (relative to maximum)
    SET @Vulnerability = CASE WHEN @MaxFailureSeverity > 0 THEN @AvgFailureSeverity / @MaxFailureSeverity ELSE 0 END;
    
    -- Note: Resilience calculation requires more complex sequence analysis
    -- This would be better handled in the Python backend for accuracy
    
    PRINT 'Metrics calculated - Records: ' + CAST(@TotalRecords AS VARCHAR) + ', Failures: ' + CAST(@TotalFailures AS VARCHAR) + ', Reliability: ' + CAST(@Reliability AS VARCHAR);
END;
GO

-- 8. Sample data insertion for testing
PRINT 'Database schema created successfully!';
PRINT 'Tables created: DataSources, Catchments, RawData, ProcessedData, PerformanceMetrics';
PRINT 'Views created: vw_LatestProcessedData, vw_PerformanceSummary, vw_FailureAnalysis';
PRINT 'Stored procedures created: sp_GetDataForAnalysis, sp_CalculatePerformanceMetrics';
GO