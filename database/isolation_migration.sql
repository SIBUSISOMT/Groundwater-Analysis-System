-- ============================================================================
-- HydroCore Tenant Isolation Migration
-- Run ONCE against GroundwaterAnalysis database.
-- Safe to re-run (all statements are idempotent).
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- ─── 1. Organizations (tenant table) ─────────────────────────────────────────
IF OBJECT_ID('dbo.Organizations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Organizations (
        org_id      INT             IDENTITY(1,1) NOT NULL,
        name        NVARCHAR(100)   NOT NULL,
        [plan]      NVARCHAR(20)    NOT NULL CONSTRAINT DF_Orgs_Plan    DEFAULT 'basic',
        is_active   BIT             NOT NULL CONSTRAINT DF_Orgs_Active  DEFAULT 1,
        created_at  DATETIME2       NOT NULL CONSTRAINT DF_Orgs_Created DEFAULT GETDATE(),
        CONSTRAINT PK_Organizations PRIMARY KEY (org_id),
        CONSTRAINT UQ_Orgs_Name    UNIQUE (name),
        CONSTRAINT CK_Orgs_Plan    CHECK ([plan] IN ('basic', 'pro'))
    );
    PRINT 'Created dbo.Organizations';
END
GO

-- Seed the default org (id will be 1 since table is new)
IF NOT EXISTS (SELECT 1 FROM dbo.Organizations WHERE name = 'Default')
BEGIN
    INSERT INTO dbo.Organizations (name, [plan]) VALUES ('Default', 'pro');
    PRINT 'Inserted Default organization';
END
GO

-- ─── 2. org_id on Users ───────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'org_id')
BEGIN
    ALTER TABLE dbo.Users ADD org_id INT NULL;
    UPDATE dbo.Users SET org_id = (SELECT TOP 1 org_id FROM dbo.Organizations WHERE name = 'Default')
    WHERE org_id IS NULL;
    ALTER TABLE dbo.Users ALTER COLUMN org_id INT NOT NULL;
    ALTER TABLE dbo.Users ADD CONSTRAINT FK_Users_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    CREATE INDEX IX_Users_OrgId ON dbo.Users(org_id);
    PRINT 'Added org_id to dbo.Users';
END
GO

-- ─── 3. uploaded_by on DataSources ───────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.DataSources') AND name = 'uploaded_by')
BEGIN
    ALTER TABLE dbo.DataSources ADD uploaded_by INT NULL;
    ALTER TABLE dbo.DataSources ADD CONSTRAINT FK_DS_UploadedBy
        FOREIGN KEY (uploaded_by) REFERENCES dbo.Users(user_id);
    PRINT 'Added uploaded_by to dbo.DataSources';
END
GO

-- ─── 4. org_id on DataSources ────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.DataSources') AND name = 'org_id')
BEGIN
    ALTER TABLE dbo.DataSources ADD org_id INT NULL;
    UPDATE dbo.DataSources SET org_id = (SELECT TOP 1 org_id FROM dbo.Organizations WHERE name = 'Default')
    WHERE org_id IS NULL;
    ALTER TABLE dbo.DataSources ALTER COLUMN org_id INT NOT NULL;
    ALTER TABLE dbo.DataSources ADD CONSTRAINT FK_DS_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    CREATE INDEX IX_DS_OrgId ON dbo.DataSources(org_id);
    PRINT 'Added org_id to dbo.DataSources';
END
GO

-- ─── 5. org_id on RawData ────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.RawData') AND name = 'org_id')
BEGIN
    ALTER TABLE dbo.RawData ADD org_id INT NULL;
    UPDATE dbo.RawData SET org_id = (SELECT TOP 1 org_id FROM dbo.Organizations WHERE name = 'Default')
    WHERE org_id IS NULL;
    ALTER TABLE dbo.RawData ALTER COLUMN org_id INT NOT NULL;
    ALTER TABLE dbo.RawData ADD CONSTRAINT FK_RD_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    CREATE INDEX IX_RD_OrgId ON dbo.RawData(org_id);
    PRINT 'Added org_id to dbo.RawData';
END
GO

-- ─── 6. org_id on ProcessedData ──────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.ProcessedData') AND name = 'org_id')
BEGIN
    ALTER TABLE dbo.ProcessedData ADD org_id INT NULL;
    UPDATE dbo.ProcessedData SET org_id = (SELECT TOP 1 org_id FROM dbo.Organizations WHERE name = 'Default')
    WHERE org_id IS NULL;
    ALTER TABLE dbo.ProcessedData ALTER COLUMN org_id INT NOT NULL;
    ALTER TABLE dbo.ProcessedData ADD CONSTRAINT FK_PD_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    CREATE INDEX IX_PD_OrgId ON dbo.ProcessedData(org_id);
    PRINT 'Added org_id to dbo.ProcessedData';
END
GO

-- ─── 7. Rebuild sp_ProcessRawData to propagate org_id ────────────────────────
IF OBJECT_ID('dbo.sp_ProcessRawData', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_ProcessRawData;
GO

CREATE PROCEDURE dbo.sp_ProcessRawData
    @SourceId INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ProcessedCount INT = 0;

    INSERT INTO dbo.ProcessedData (
        raw_id, source_id, catchment_id, measurement_date, parameter_type,
        original_value, mean_value, std_deviation, standardized_value,
        parameter_deviation, drought_index, classification, is_failure, severity_level,
        org_id
    )
    SELECT
        rd.raw_id,
        rd.source_id,
        rd.catchment_id,
        rd.measurement_date,
        LOWER(rd.category) AS parameter_type,

        CASE LOWER(rd.category)
            WHEN 'recharge' THEN rd.recharge_converted
            WHEN 'baseflow' THEN rd.baseflow_value
            WHEN 'gwlevel'  THEN rd.gw_level
        END AS original_value,

        CASE LOWER(rd.category)
            WHEN 'recharge' THEN rd.average_recharge
            WHEN 'baseflow' THEN rd.average_baseflow
            WHEN 'gwlevel'  THEN rd.average_gw_level
        END AS mean_value,

        CASE LOWER(rd.category)
            WHEN 'recharge' THEN rd.recharge_stdev
            WHEN 'baseflow' THEN rd.baseflow_stdev
            WHEN 'gwlevel'  THEN rd.gw_level_stdev
        END AS std_deviation,

        CASE LOWER(rd.category)
            WHEN 'recharge' THEN rd.drought_index_recharge
            WHEN 'baseflow' THEN rd.standardized_baseflow
            WHEN 'gwlevel'  THEN rd.standardized_gw_level
        END AS standardized_value,

        CASE LOWER(rd.category)
            WHEN 'recharge' THEN rd.recharge_deviation
            WHEN 'baseflow' THEN rd.baseflow_deviation
            WHEN 'gwlevel'  THEN rd.gw_level_deviation
        END AS parameter_deviation,

        rd.drought_index_recharge AS drought_index,

        CASE
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END >  0.5  THEN 'Surplus'
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END BETWEEN -0.5 AND  0.5  THEN 'Normal'
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END BETWEEN -1.0 AND -0.5  THEN 'Moderate_Deficit'
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END BETWEEN -1.5 AND -1.0  THEN 'Severe_Deficit'
            ELSE 'Extreme_Deficit'
        END AS classification,

        CASE
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END < -0.5 THEN 1
            ELSE 0
        END AS is_failure,

        CASE
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END >  0.5  THEN -1
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END BETWEEN -0.5 AND 0.5   THEN 0
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END BETWEEN -1.0 AND -0.5  THEN 1
            WHEN CASE LOWER(rd.category)
                    WHEN 'recharge' THEN rd.drought_index_recharge
                    WHEN 'baseflow' THEN rd.standardized_baseflow
                    WHEN 'gwlevel'  THEN rd.standardized_gw_level
                 END BETWEEN -1.5 AND -1.0  THEN 2
            ELSE 3
        END AS severity_level,

        rd.org_id

    FROM dbo.RawData rd
    WHERE rd.source_id = @SourceId
      AND NOT EXISTS (
          SELECT 1 FROM dbo.ProcessedData pd WHERE pd.raw_id = rd.raw_id
      );

    SET @ProcessedCount = @@ROWCOUNT;

    UPDATE dbo.DataSources
    SET processing_status = 'Completed', updated_at = GETDATE()
    WHERE source_id = @SourceId;

    PRINT 'Processed ' + CAST(@ProcessedCount AS VARCHAR(10))
        + ' records for source ' + CAST(@SourceId AS VARCHAR(10));
END;
GO

PRINT '';
PRINT '========================================';
PRINT 'Tenant isolation migration complete.';
PRINT '  - dbo.Organizations created';
PRINT '  - org_id added to Users, DataSources, RawData, ProcessedData';
PRINT '  - uploaded_by added to DataSources';
PRINT '  - sp_ProcessRawData updated to propagate org_id';
PRINT '';
PRINT 'Next: deploy updated auth.py and app.py';
PRINT '========================================';
GO
