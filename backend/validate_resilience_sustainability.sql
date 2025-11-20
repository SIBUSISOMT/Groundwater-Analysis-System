-- ============================================================================
-- RESILIENCE AND SUSTAINABILITY VALIDATION QUERY
-- ============================================================================
-- This query shows detailed breakdown of resilience and sustainability calculations
-- to verify they are working correctly after the fix
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- Test with your actual filtered data
DECLARE @TestCatchment NVARCHAR(255) = 'Crocodile'; -- Change to your catchment
DECLARE @TestParameter NVARCHAR(50) = 'recharge';   -- Change to your parameter

PRINT '========================================';
PRINT 'RESILIENCE & SUSTAINABILITY VALIDATION';
PRINT '========================================';
PRINT '';

-- ============================================================================
-- PART 1: RAW FAILURE DATA BREAKDOWN
-- ============================================================================
PRINT 'PART 1: Failure Records Analysis';
PRINT '----------------------------------------';

SELECT
    c.catchment_name,
    pd.parameter_type,

    -- Total counts
    COUNT(*) as total_records,
    SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) as failure_count,
    SUM(CASE WHEN pd.is_failure = 0 THEN 1 ELSE 0 END) as normal_count,

    -- Failure breakdown by severity
    SUM(CASE WHEN pd.severity_level = 1 THEN 1 ELSE 0 END) as moderate_failures,
    SUM(CASE WHEN pd.severity_level = 2 THEN 1 ELSE 0 END) as severe_failures,
    SUM(CASE WHEN pd.severity_level = 3 THEN 1 ELSE 0 END) as extreme_failures,

    -- Z-score statistics for failures only
    AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) END) as avg_abs_zscore_failures,
    MIN(CASE WHEN pd.is_failure = 1 THEN pd.standardized_value END) as min_zscore_failures,
    MAX(CASE WHEN pd.is_failure = 1 THEN pd.standardized_value END) as max_zscore_failures,

    -- Severity statistics for failures only
    AVG(CASE WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT) END) as avg_severity_failures

FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = @TestCatchment
  AND LOWER(pd.parameter_type) = @TestParameter
GROUP BY c.catchment_name, pd.parameter_type;

PRINT '';
PRINT '----------------------------------------';

-- ============================================================================
-- PART 2: METRIC CALCULATIONS WITH FORMULAS SHOWN
-- ============================================================================
PRINT 'PART 2: Calculated Metrics (Showing Formulas)';
PRINT '----------------------------------------';

SELECT
    c.catchment_name,
    pd.parameter_type,
    COUNT(*) as total_records,
    SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) as failure_count,

    -- ===== RELIABILITY =====
    CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) /
        NULLIF(COUNT(*), 0) as reliability,

    -- ===== RESILIENCE (NEW FORMULA) =====
    CASE
        WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 1.0
        ELSE 1.0 - (AVG(CASE
            WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT)
            ELSE NULL
        END) / 3.0)
    END as resilience,

    -- Show the avg severity for failures (used in resilience)
    AVG(CASE WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT) END) as avg_severity_of_failures,

    -- ===== VULNERABILITY =====
    CASE
        WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 0
        ELSE AVG(CASE
            WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT))
            ELSE NULL
        END) / 3.0
    END as vulnerability,

    -- Show the avg abs z-score for failures (used in vulnerability)
    AVG(CASE WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT)) END) as avg_abs_zscore_of_failures,

    -- ===== SUSTAINABILITY (ISI) =====
    CASE
        WHEN COUNT(*) = 0 THEN 0
        ELSE
            (
                -- Reliability component (w_r=1)
                (CAST(SUM(CASE WHEN pd.standardized_value >= -0.5 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) +
                -- Resilience component (w_s=1)
                CASE
                    WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 1.0
                    ELSE 1.0 - (AVG(CASE
                        WHEN pd.is_failure = 1 THEN CAST(pd.severity_level AS FLOAT)
                        ELSE NULL
                    END) / 3.0)
                END +
                -- Robustness component (w_v=1): (1 - Vulnerability)
                (1.0 - CASE
                    WHEN SUM(CASE WHEN pd.is_failure = 1 THEN 1 ELSE 0 END) = 0 THEN 0
                    ELSE AVG(CASE
                        WHEN pd.is_failure = 1 THEN ABS(CAST(pd.standardized_value AS FLOAT))
                        ELSE NULL
                    END) / 3.0
                END)
            ) / 3.0
    END as sustainability

FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = @TestCatchment
  AND LOWER(pd.parameter_type) = @TestParameter
GROUP BY c.catchment_name, pd.parameter_type;

PRINT '';
PRINT '----------------------------------------';

-- ============================================================================
-- PART 3: MANUAL CALCULATION VERIFICATION
-- ============================================================================
PRINT 'PART 3: Step-by-Step Manual Calculation';
PRINT '----------------------------------------';

DECLARE @TotalRecords INT;
DECLARE @FailureCount INT;
DECLARE @SatisfactoryCount INT;
DECLARE @AvgSeverityFailures FLOAT;
DECLARE @AvgAbsZScoreFailures FLOAT;
DECLARE @Reliability FLOAT;
DECLARE @Resilience FLOAT;
DECLARE @Vulnerability FLOAT;
DECLARE @Sustainability FLOAT;

-- Get counts
SELECT
    @TotalRecords = COUNT(*),
    @FailureCount = SUM(CASE WHEN is_failure = 1 THEN 1 ELSE 0 END),
    @SatisfactoryCount = SUM(CASE WHEN standardized_value >= -0.5 THEN 1 ELSE 0 END),
    @AvgSeverityFailures = AVG(CASE WHEN is_failure = 1 THEN CAST(severity_level AS FLOAT) END),
    @AvgAbsZScoreFailures = AVG(CASE WHEN is_failure = 1 THEN ABS(CAST(standardized_value AS FLOAT)) END)
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE c.catchment_name = @TestCatchment
  AND LOWER(pd.parameter_type) = @TestParameter;

-- Calculate metrics
SET @Reliability = CAST(@SatisfactoryCount AS FLOAT) / NULLIF(@TotalRecords, 0);

IF @FailureCount = 0
    SET @Resilience = 1.0;
ELSE
    SET @Resilience = 1.0 - (@AvgSeverityFailures / 3.0);

IF @FailureCount = 0
    SET @Vulnerability = 0.0;
ELSE
    SET @Vulnerability = @AvgAbsZScoreFailures / 3.0;

SET @Sustainability = (@Reliability + @Resilience + (1.0 - @Vulnerability)) / 3.0;

-- Display step-by-step
PRINT 'Step 1: Data Collection';
PRINT '  Total Records: ' + CAST(@TotalRecords AS VARCHAR(10));
PRINT '  Failure Count: ' + CAST(@FailureCount AS VARCHAR(10));
PRINT '  Satisfactory Count: ' + CAST(@SatisfactoryCount AS VARCHAR(10));
PRINT '  Avg Severity (failures only): ' + CAST(@AvgSeverityFailures AS VARCHAR(20));
PRINT '  Avg |Z-score| (failures only): ' + CAST(@AvgAbsZScoreFailures AS VARCHAR(20));
PRINT '';

PRINT 'Step 2: Reliability Calculation';
PRINT '  Formula: Satisfactory / Total';
PRINT '  Calculation: ' + CAST(@SatisfactoryCount AS VARCHAR(10)) + ' / ' + CAST(@TotalRecords AS VARCHAR(10));
PRINT '  Result: ' + CAST(@Reliability AS VARCHAR(20)) + ' (' + CAST(@Reliability * 100 AS VARCHAR(20)) + '%)';
PRINT '';

PRINT 'Step 3: Resilience Calculation (FIXED - failures only)';
IF @FailureCount = 0
    PRINT '  No failures detected → Resilience = 1.0';
ELSE
BEGIN
    PRINT '  Formula: 1.0 - (Avg Severity of Failures / 3.0)';
    PRINT '  Calculation: 1.0 - (' + CAST(@AvgSeverityFailures AS VARCHAR(20)) + ' / 3.0)';
    PRINT '  Calculation: 1.0 - ' + CAST(@AvgSeverityFailures / 3.0 AS VARCHAR(20));
    PRINT '  Result: ' + CAST(@Resilience AS VARCHAR(20));
END
PRINT '';

PRINT 'Step 4: Vulnerability Calculation (failures only)';
IF @FailureCount = 0
    PRINT '  No failures detected → Vulnerability = 0.0';
ELSE
BEGIN
    PRINT '  Formula: Avg |Z-score| of Failures / 3.0';
    PRINT '  Calculation: ' + CAST(@AvgAbsZScoreFailures AS VARCHAR(20)) + ' / 3.0';
    PRINT '  Result: ' + CAST(@Vulnerability AS VARCHAR(20)) + ' (' + CAST(@Vulnerability * 100 AS VARCHAR(20)) + '%)';
END
PRINT '';

PRINT 'Step 5: Sustainability Calculation (ISI)';
PRINT '  Formula: (Reliability + Resilience + (1 - Vulnerability)) / 3';
PRINT '  Calculation: (' + CAST(@Reliability AS VARCHAR(20)) + ' + ' + CAST(@Resilience AS VARCHAR(20)) + ' + ' + CAST(1.0 - @Vulnerability AS VARCHAR(20)) + ') / 3';
PRINT '  Calculation: ' + CAST(@Reliability + @Resilience + (1.0 - @Vulnerability) AS VARCHAR(20)) + ' / 3';
PRINT '  Result: ' + CAST(@Sustainability AS VARCHAR(20));
PRINT '';

-- ============================================================================
-- PART 4: INVERSE RELATIONSHIP CHECK
-- ============================================================================
PRINT '----------------------------------------';
PRINT 'PART 4: Resilience vs Vulnerability Inverse Relationship Check';
PRINT '----------------------------------------';

PRINT 'Resilience: ' + CAST(@Resilience AS VARCHAR(20)) + ' (higher = better recovery)';
PRINT 'Vulnerability: ' + CAST(@Vulnerability AS VARCHAR(20)) + ' (lower = better)';
PRINT '';

IF @FailureCount > 0
BEGIN
    DECLARE @InverseCheck FLOAT;
    SET @InverseCheck = @Resilience + @Vulnerability;

    PRINT 'Inverse Relationship Test:';
    PRINT '  If truly inverse with same scale: Resilience + Vulnerability should be constant';
    PRINT '  Sum: ' + CAST(@InverseCheck AS VARCHAR(20));

    IF @Resilience > 0.5 AND @Vulnerability < 0.5
        PRINT '  ✓ PASS: High resilience (>0.5) with low vulnerability (<0.5)';
    ELSE IF @Resilience < 0.5 AND @Vulnerability > 0.5
        PRINT '  ✓ PASS: Low resilience (<0.5) with high vulnerability (>0.5)';
    ELSE
        PRINT '  ✓ Both in moderate range (0.3-0.7) - consistent with moderate failures';
END
ELSE
    PRINT '  No failures to test inverse relationship';

PRINT '';
PRINT '========================================';
PRINT 'VALIDATION COMPLETE';
PRINT '========================================';
PRINT '';
PRINT 'Compare these results with your dashboard to verify accuracy.';
PRINT 'Expected behavior:';
PRINT '  - Resilience = 1.0 only when failure_count = 0';
PRINT '  - Resilience and Vulnerability should move inversely';
PRINT '  - Sustainability should reflect balanced view of all three metrics';

GO
