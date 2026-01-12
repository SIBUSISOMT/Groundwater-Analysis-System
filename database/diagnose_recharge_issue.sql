-- ====================================================================
-- DIAGNOSTIC SCRIPT: Find why Crocodile + recharge returns no data
-- ====================================================================

USE GroundwaterDB;
GO

PRINT '========================================';
PRINT 'DIAGNOSTIC 1: All parameter types in ProcessedData';
PRINT '========================================';
SELECT
    parameter_type,
    COUNT(*) as record_count,
    -- Show the actual case (if mixed case exists, it will show here)
    CASE
        WHEN parameter_type = LOWER(parameter_type) THEN 'lowercase ✓'
        ELSE 'MIXED/UPPER CASE ✗'
    END as case_status
FROM dbo.ProcessedData
GROUP BY parameter_type
ORDER BY parameter_type;

PRINT '';
PRINT '========================================';
PRINT 'DIAGNOSTIC 2: Crocodile catchment - all parameters';
PRINT '========================================';
SELECT
    c.catchment_name,
    pd.parameter_type,
    COUNT(*) as record_count
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = 'Crocodile'
GROUP BY c.catchment_name, pd.parameter_type
ORDER BY pd.parameter_type;

PRINT '';
PRINT '========================================';
PRINT 'DIAGNOSTIC 3: Check for "Recharge" variations';
PRINT '========================================';
SELECT DISTINCT
    parameter_type as actual_value_in_db,
    LOWER(parameter_type) as lowercase_version,
    COUNT(*) as count
FROM dbo.ProcessedData
WHERE LOWER(parameter_type) = 'recharge'
GROUP BY parameter_type
ORDER BY parameter_type;

PRINT '';
PRINT '========================================';
PRINT 'DIAGNOSTIC 4: All catchments with any data';
PRINT '========================================';
SELECT
    c.catchment_name,
    COUNT(DISTINCT pd.parameter_type) as parameter_types,
    COUNT(*) as total_records
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
GROUP BY c.catchment_name
ORDER BY c.catchment_name;

PRINT '';
PRINT '========================================';
PRINT 'DIAGNOSTIC 5: Sample of Crocodile data';
PRINT '========================================';
SELECT TOP 10
    c.catchment_name,
    pd.parameter_type,
    pd.measurement_date,
    pd.original_value,
    pd.classification
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = 'Crocodile'
ORDER BY pd.measurement_date DESC;

PRINT '';
PRINT '========================================';
PRINT 'DIAGNOSTIC 6: Check RawData category values';
PRINT '========================================';
SELECT DISTINCT
    rd.category as raw_category,
    LOWER(rd.category) as lowercase_version,
    COUNT(*) as count
FROM dbo.RawData rd
WHERE LOWER(rd.category) = 'recharge'
GROUP BY rd.category
ORDER BY rd.category;

PRINT '';
PRINT '========================================';
PRINT 'DIAGNOSTIC COMPLETE';
PRINT '========================================';
