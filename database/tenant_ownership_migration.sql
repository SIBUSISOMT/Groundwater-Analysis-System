-- ============================================================================
-- HydroCore Tenant Ownership Migration
-- Run ONCE against GroundwaterAnalysis, AFTER isolation_migration.sql and
-- wq_schema_v2.sql. Safe to re-run (all statements are idempotent).
--
-- Makes Catchments and WQ_Indicators tenant-owned (previously global/shared),
-- introduces a genuine Catchment -> Sub Area hierarchy, closes the remaining
-- org_id/FK gaps (Users, WQ_Stations, WQ_Readings), and adds the
-- 'standard_user' role to the CK_Users_Role constraint.
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- ─── 1. SubAreas table (new) ──────────────────────────────────────────────────
IF OBJECT_ID('dbo.SubAreas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.SubAreas (
        sub_area_id  INT           IDENTITY(1,1) NOT NULL,
        catchment_id INT           NOT NULL,
        org_id       INT           NOT NULL,
        name         NVARCHAR(255) NOT NULL,
        is_active    BIT           NOT NULL CONSTRAINT DF_SubAreas_Active  DEFAULT 1,
        created_at   DATETIME2     NOT NULL CONSTRAINT DF_SubAreas_Created DEFAULT GETDATE(),
        CONSTRAINT PK_SubAreas            PRIMARY KEY (sub_area_id),
        CONSTRAINT FK_SubAreas_Catchment  FOREIGN KEY (catchment_id) REFERENCES dbo.Catchments(catchment_id),
        CONSTRAINT FK_SubAreas_Org        FOREIGN KEY (org_id)       REFERENCES dbo.Organizations(org_id),
        CONSTRAINT UQ_SubAreas_CatchmentName UNIQUE (catchment_id, name)
    );
    CREATE INDEX IX_SubAreas_Catchment ON dbo.SubAreas(catchment_id);
    CREATE INDEX IX_SubAreas_Org       ON dbo.SubAreas(org_id);
    PRINT 'Created dbo.SubAreas';
END
ELSE
    PRINT 'Table dbo.SubAreas already exists — skipped.';
GO

-- ─── 2. org_id on Catchments (tenant-owned) ──────────────────────────────────
-- Split into two batches: a freshly ADDed column can't reliably be referenced
-- by further ALTER TABLE statements in the SAME batch (SQL Server deferred
-- name resolution doesn't cover DDL-on-DDL within one compilation unit).
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Catchments') AND name = 'org_id')
    ALTER TABLE dbo.Catchments ADD org_id INT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Catchments_Org')
BEGIN
    UPDATE dbo.Catchments SET org_id = (SELECT TOP 1 org_id FROM dbo.Organizations WHERE name = 'Default')
    WHERE org_id IS NULL;
    ALTER TABLE dbo.Catchments ALTER COLUMN org_id INT NOT NULL;
    ALTER TABLE dbo.Catchments ADD CONSTRAINT FK_Catchments_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    CREATE INDEX IX_Catchments_OrgId ON dbo.Catchments(org_id);
    PRINT 'Added org_id to dbo.Catchments';
END
ELSE
    PRINT 'dbo.Catchments.org_id already fully migrated — skipped.';
GO

-- Swap the old GLOBAL unique constraint on catchment_name for a per-org one,
-- so two different tenants can each register their own "Sabie". The original
-- constraint (schema.sql: `catchment_name NVARCHAR(255) NOT NULL UNIQUE`) has
-- an auto-generated name, so it must be located dynamically.
IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_Catchments_OrgName')
BEGIN
    DECLARE @old_cc_name NVARCHAR(128);
    SELECT @old_cc_name = kc.name
    FROM sys.key_constraints kc
    JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
    JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE kc.parent_object_id = OBJECT_ID('dbo.Catchments')
      AND kc.type = 'UQ'
      AND c.name = 'catchment_name';

    IF @old_cc_name IS NOT NULL
        EXEC('ALTER TABLE dbo.Catchments DROP CONSTRAINT [' + @old_cc_name + ']');

    CREATE UNIQUE INDEX UQ_Catchments_OrgName ON dbo.Catchments(org_id, catchment_name);
    PRINT 'Replaced global catchment_name UNIQUE with per-org UQ_Catchments_OrgName';
END
ELSE
    PRINT 'UQ_Catchments_OrgName already exists — skipped.';
GO

-- ─── 3. org_id on WQ_Indicators (tenant-owned) ───────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WQ_Indicators') AND name = 'org_id')
    ALTER TABLE dbo.WQ_Indicators ADD org_id INT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_WQInd_Org')
BEGIN
    UPDATE dbo.WQ_Indicators SET org_id = (SELECT TOP 1 org_id FROM dbo.Organizations WHERE name = 'Default')
    WHERE org_id IS NULL;
    ALTER TABLE dbo.WQ_Indicators ALTER COLUMN org_id INT NOT NULL;
    ALTER TABLE dbo.WQ_Indicators ADD CONSTRAINT FK_WQInd_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    CREATE INDEX IX_WQInd_OrgId ON dbo.WQ_Indicators(org_id);
    PRINT 'Added org_id to dbo.WQ_Indicators';
END
ELSE
    PRINT 'dbo.WQ_Indicators.org_id already fully migrated — skipped.';
GO

-- Swap the global indicator_code UNIQUE for a per-org one — required because
-- every tenant will end up with their own copy of the same SANS 241 codes.
IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_WQInd_Code')
    ALTER TABLE dbo.WQ_Indicators DROP CONSTRAINT UQ_WQInd_Code;
GO
IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_WQInd_OrgCode')
BEGIN
    ALTER TABLE dbo.WQ_Indicators ADD CONSTRAINT UQ_WQInd_OrgCode UNIQUE (org_id, indicator_code);
    PRINT 'Replaced global indicator_code UNIQUE with per-org UQ_WQInd_OrgCode';
END
GO

-- Backfill a full copy of org 1's 43 indicators for org 3 ("Offingteck (Pty) Ltd"),
-- which already has real WQ_Stations/upload data from before this migration and
-- would otherwise end up with zero indicators once WQ_Indicators is tenant-scoped.
IF EXISTS (SELECT 1 FROM dbo.Organizations WHERE org_id = 3)
   AND NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id = 3)
BEGIN
    INSERT INTO dbo.WQ_Indicators
        (org_id, indicator_code, indicator_name, unit, lower_std, upper_std, std_reference, display_order,
         risk_class, sans_class1_limit, sans_class2_limit, method_detection_limit, equivalent_weight, ion_type, blue_drop_category)
    SELECT
        3, indicator_code, indicator_name, unit, lower_std, upper_std, std_reference, display_order,
        risk_class, sans_class1_limit, sans_class2_limit, method_detection_limit, equivalent_weight, ion_type, blue_drop_category
    FROM dbo.WQ_Indicators
    WHERE org_id = 1;
    PRINT 'Seeded a copy of org 1''s WQ_Indicators for org 3';
END
GO

-- ─── 4. sub_area_id on DataSources (additive, nullable — subcatchment_name is
--        left completely untouched for backward compatibility) ──────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.DataSources') AND name = 'sub_area_id')
    ALTER TABLE dbo.DataSources ADD sub_area_id INT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DS_SubArea')
BEGIN
    ALTER TABLE dbo.DataSources ADD CONSTRAINT FK_DS_SubArea
        FOREIGN KEY (sub_area_id) REFERENCES dbo.SubAreas(sub_area_id);
    CREATE INDEX IX_DS_SubAreaId ON dbo.DataSources(sub_area_id);
    PRINT 'Added sub_area_id to dbo.DataSources';
END
ELSE
    PRINT 'dbo.DataSources.sub_area_id already fully migrated — skipped.';
GO

-- ─── 5. Default org (1) backfill: one Sub Area per existing catchment, same
--        name as the catchment, so org 1's upload workflow is unchanged on
--        day one. They can register more granular sub-areas later.       ───
INSERT INTO dbo.SubAreas (catchment_id, org_id, name)
SELECT c.catchment_id, c.org_id, c.catchment_name
FROM dbo.Catchments c
WHERE c.org_id = 1
  AND NOT EXISTS (
      SELECT 1 FROM dbo.SubAreas sa WHERE sa.catchment_id = c.catchment_id AND sa.name = c.catchment_name
  );
GO

-- ─── 6. Users.org_id FK fix — guard on the FK's existence, not the column's,
--        since auth_schema.sql adds the column without a FK and
--        isolation_migration.sql only adds the FK if the column was absent.
--        Depending on which ran first historically, the FK may be missing
--        today even though the column always exists.                    ───
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Users_Org')
BEGIN
    ALTER TABLE dbo.Users ADD CONSTRAINT FK_Users_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    PRINT 'Added missing FK_Users_Org (column pre-existed without FK)';
END
ELSE
    PRINT 'FK_Users_Org already exists — skipped.';
GO

-- ─── 7. WQ_Stations / WQ_Readings FK to Organizations (column already exists
--        on both, unlike WQ_Alert_Config/WQ_Alert_Log which got the FK in v2) ─
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_WQSt_Org')
BEGIN
    ALTER TABLE dbo.WQ_Stations ADD CONSTRAINT FK_WQSt_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    PRINT 'Added FK_WQSt_Org';
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_WQR_Org')
BEGIN
    ALTER TABLE dbo.WQ_Readings ADD CONSTRAINT FK_WQR_Org
        FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
    PRINT 'Added FK_WQR_Org';
END
GO

-- ─── 8. CK_Users_Role — add 'standard_user' ──────────────────────────────────
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_Users_Role'
      AND definition NOT LIKE '%standard_user%'
)
BEGIN
    ALTER TABLE dbo.Users DROP CONSTRAINT CK_Users_Role;
    ALTER TABLE dbo.Users ADD CONSTRAINT CK_Users_Role
        CHECK (role IN ('admin', 'analyst', 'viewer', 'standard_user'));
    PRINT 'Updated CK_Users_Role to include standard_user';
END
ELSE
    PRINT 'CK_Users_Role already includes standard_user (or does not exist) — skipped.';
GO

PRINT '';
PRINT '========================================';
PRINT 'Tenant ownership migration complete.';
PRINT '  - dbo.SubAreas created';
PRINT '  - Catchments and WQ_Indicators are now tenant-owned (org_id + per-org unique)';
PRINT '  - org 3 backfilled with a copy of org 1''s WQ_Indicators';
PRINT '  - DataSources.sub_area_id added (subcatchment_name untouched)';
PRINT '  - org 1 backfilled with one default Sub Area per existing catchment';
PRINT '  - FK_Users_Org, FK_WQSt_Org, FK_WQR_Org closed';
PRINT '  - CK_Users_Role now allows standard_user';
PRINT '========================================';
GO
