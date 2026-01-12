-- Fix existing parameter_type values to be lowercase
-- This ensures compatibility with the API's case-insensitive filtering

USE GroundwaterDB;
GO

-- Update ProcessedData table to have lowercase parameter types
UPDATE dbo.ProcessedData
SET parameter_type = LOWER(parameter_type)
WHERE parameter_type != LOWER(parameter_type);

-- Check the results
SELECT
    parameter_type,
    COUNT(*) as record_count
FROM dbo.ProcessedData
GROUP BY parameter_type
ORDER BY parameter_type;

PRINT 'Parameter types normalized to lowercase successfully!';
