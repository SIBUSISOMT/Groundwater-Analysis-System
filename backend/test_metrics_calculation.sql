-- ============================================================================
-- TEST QUERY: Verify Performance Metrics Calculations
-- ============================================================================
-- Run this query in SQL Server Management Studio to see detailed metrics breakdown
-- and verify calculations align with your interpretation guide

USE GroundwaterAnalysis;
GO

-- Sample data breakdown for a specific catchment
DECLARE @TestCatchment NVARCHAR(255) = 'Crocodile'; -- Change to test different catchments
DECLARE @TestParameter NVARCHAR(50) = 'recharge'; -- Change to: recharge, baseflow, gwlevel

SELECT
    c.catchment_name,
    pd.parameter_type,

    -- ===== RAW COUNTS =====
    COUNT(*) as total_records,
    SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) as satisfactory_records,
    SUM(CASE WHEN pd.standardized_value < -0.5 THEN 1 ELSE 0 END) as failure_records,
    SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) as flagged_failures,

    -- ===== SEVERITY BREAKDOWN =====
    AVG(CAST(pd.severity_level AS FLOAT)) as avg_severity_level,
    SUM(CASE WHEN pd.severity_level = -1 THEN 1 ELSE 0 END) as surplus_count,
    SUM(CASE WHEN pd.severity_level = 0 THEN 1 ELSE 0 END) as normal_count,
    SUM(CASE WHEN pd.severity_level = 1 THEN 1 ELSE 0 END) as moderate_deficit_count,
    SUM(CASE WHEN pd.severity_level = 2 THEN 1 ELSE 0 END) as severe_deficit_count,
    SUM(CASE WHEN pd.severity_level = 3 THEN 1 ELSE 0 END) as extreme_deficit_count,

    -- ===== CALCULATED METRICS =====

    -- RELIABILITY: % of time satisfactory (z-score >= -0.5)
    CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
    NULLIF(COUNT(*), 0) as reliability,

    -- Reliability classification
    CASE
        WHEN CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
             NULLIF(COUNT(*), 0) > 0.80 THEN 'Excellent (>80%)'
        WHEN CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
             NULLIF(COUNT(*), 0) BETWEEN 0.60 AND 0.80 THEN 'Good (60-80%)'
        WHEN CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
             NULLIF(COUNT(*), 0) BETWEEN 0.40 AND 0.60 THEN 'Moderate (40-60%)'
        WHEN CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
             NULLIF(COUNT(*), 0) BETWEEN 0.20 AND 0.40 THEN 'Poor (20-40%)'
        ELSE 'Critical (<20%)'
    END as reliability_class,

    -- RESILIENCE: Recovery speed (inverse of avg severity)
    CASE
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0.5
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) <= 0 THEN 1.0
        ELSE 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)
    END as resilience,

    -- Resilience classification
    CASE
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 'Unknown'
        WHEN 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0) > 0.5 THEN 'Fast Recovery (>0.5)'
        WHEN 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0) BETWEEN 0.25 AND 0.5 THEN 'Moderate Recovery (0.25-0.5)'
        WHEN 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0) BETWEEN 0.1 AND 0.25 THEN 'Slow Recovery (0.1-0.25)'
        ELSE 'Very Slow (<0.1)'
    END as resilience_class,

    -- VULNERABILITY: Avg severity as percentage
    CASE
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0
        ELSE AVG(CAST(pd.severity_level AS FLOAT)) / 3.0
    END as vulnerability,

    -- Vulnerability classification
    CASE
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) / 3.0 < 0.40 THEN 'Low Impact (<40%)'
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) / 3.0 BETWEEN 0.40 AND 0.60 THEN 'Moderate Impact (40-60%)'
        WHEN AVG(CAST(pd.severity_level AS FLOAT)) / 3.0 BETWEEN 0.60 AND 0.80 THEN 'High Impact (60-80%)'
        ELSE 'Severe Impact (>80%)'
    END as vulnerability_class,

    -- SUSTAINABILITY: Combined metric
    CASE
        WHEN COUNT(*) = 0 THEN 0
        ELSE
            (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) *
            CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0.5
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) <= 0 THEN 1.0
                ELSE 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)
            END *
            (1.0 - CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0
                ELSE AVG(CAST(pd.severity_level AS FLOAT)) / 3.0
            END)
    END as sustainability,

    -- Sustainability classification
    CASE
        WHEN (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) *
             CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0.5
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) <= 0 THEN 1.0
                ELSE 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)
             END *
             (1.0 - CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0
                ELSE AVG(CAST(pd.severity_level AS FLOAT)) / 3.0
             END) > 0.5 THEN 'Sustainable (>0.5)'
        WHEN (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) *
             CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0.5
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) <= 0 THEN 1.0
                ELSE 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)
             END *
             (1.0 - CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0
                ELSE AVG(CAST(pd.severity_level AS FLOAT)) / 3.0
             END) BETWEEN 0.3 AND 0.5 THEN 'Moderately Sustainable (0.3-0.5)'
        WHEN (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) *
             CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0.5
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) <= 0 THEN 1.0
                ELSE 1.0 - (AVG(CAST(pd.severity_level AS FLOAT)) / 3.0)
             END *
             (1.0 - CASE
                WHEN AVG(CAST(pd.severity_level AS FLOAT)) IS NULL THEN 0
                ELSE AVG(CAST(pd.severity_level AS FLOAT)) / 3.0
             END) BETWEEN 0.1 AND 0.3 THEN 'At Risk (0.1-0.3)'
        ELSE 'Unsustainable (<0.1)'
    END as sustainability_class

FROM dbo.ProcessedData pd
JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = @TestCatchment
  AND LOWER(pd.parameter_type) = @TestParameter
GROUP BY c.catchment_name, pd.parameter_type;

-- ============================================================================
-- DETAILED RECORD BREAKDOWN
-- ============================================================================
PRINT '';
PRINT '========================================';
PRINT 'DETAILED BREAKDOWN BY Z-SCORE RANGES';
PRINT '========================================';

SELECT
    c.catchment_name,
    pd.parameter_type,

    -- Z-score ranges
    'Z-Score Distribution' as metric_type,
    SUM(CASE WHEN pd.standardized_value > 0.5 THEN 1 ELSE 0 END) as above_normal_count,
    SUM(CASE WHEN pd.standardized_value BETWEEN -0.5 AND 0.5 THEN 1 ELSE 0 END) as normal_range_count,
    SUM(CASE WHEN pd.standardized_value BETWEEN -1.0 AND -0.5 THEN 1 ELSE 0 END) as moderate_deficit_count,
    SUM(CASE WHEN pd.standardized_value BETWEEN -1.5 AND -1.0 THEN 1 ELSE 0 END) as severe_deficit_count,
    SUM(CASE WHEN pd.standardized_value < -1.5 THEN 1 ELSE 0 END) as extreme_deficit_count,

    -- Percentages
    CAST(SUM(CASE WHEN pd.standardized_value > 0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100 as above_normal_pct,
    CAST(SUM(CASE WHEN pd.standardized_value BETWEEN -0.5 AND 0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100 as normal_pct,
    CAST(SUM(CASE WHEN pd.standardized_value BETWEEN -1.0 AND -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100 as moderate_deficit_pct,
    CAST(SUM(CASE WHEN pd.standardized_value BETWEEN -1.5 AND -1.0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100 as severe_deficit_pct,
    CAST(SUM(CASE WHEN pd.standardized_value < -1.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100 as extreme_deficit_pct

FROM dbo.ProcessedData pd
JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = @TestCatchment
  AND LOWER(pd.parameter_type) = @TestParameter
GROUP BY c.catchment_name, pd.parameter_type;

PRINT '';
PRINT '========================================';
PRINT 'TEST COMPLETE';
PRINT '========================================';
PRINT 'Compare the calculated values above with your interpretation guide';
PRINT 'to ensure classifications match expected ranges.';
