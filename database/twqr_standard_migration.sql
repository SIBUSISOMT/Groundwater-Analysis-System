-- ============================================================================
-- HydroCore TWQR Resource-Water Standard + Water Safety Plan Migration
-- Run ONCE against GroundwaterAnalysis, AFTER tenant_ownership_migration.sql.
-- Safe to re-run (all statements are idempotent).
--
-- Adds DWAF South African Water Quality Guidelines Vol 7 (Aquatic Ecosystems,
-- 1996) Target Water Quality Range (TWQR) as a SECOND compliance standard
-- alongside SANS 241:2015, since HydroCore's WQ stations are rivers, not
-- drinking-water taps. Does NOT touch lower_std/upper_std/is_compliant/
-- blue_drop_category — those stay exactly as they are, still SANS-241-driven,
-- since Blue Drop scoring and CCME-WQI both depend on them unchanged.
--
-- Also adds the Water Safety Plan risk register + corrective action tables
-- (WHO/Blue-Drop-style risk management — previously nonexistent).
--
-- All numeric values below were extracted directly from the DWAF (1996)
-- South African Water Quality Guidelines, Volume 7: Aquatic Ecosystems PDF,
-- converted from the guideline's µg/L to mg/L to match this app's existing
-- unit convention for each indicator (verified against wq_schema.sql /
-- wq_schema_v2.sql seed data before writing this file).
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- Required for the persisted computed column (risk_score) in WQ_Risk_Register below.
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- ─── 1. TWQR columns on WQ_Indicators ────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='twqr_lower')
    ALTER TABLE dbo.WQ_Indicators ADD twqr_lower FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='twqr_upper')
    ALTER TABLE dbo.WQ_Indicators ADD twqr_upper FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='twqr_cev')
    ALTER TABLE dbo.WQ_Indicators ADD twqr_cev FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='twqr_aev')
    ALTER TABLE dbo.WQ_Indicators ADD twqr_aev FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='twqr_basis')
    ALTER TABLE dbo.WQ_Indicators ADD twqr_basis NVARCHAR(30) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='twqr_reference')
    ALTER TABLE dbo.WQ_Indicators ADD twqr_reference NVARCHAR(200) NULL;
GO

-- ─── 2. Hardness-dependent TWQR bands (Cadmium, Copper, Lead) ────────────────
IF OBJECT_ID('dbo.WQ_TWQR_HardnessBands', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_TWQR_HardnessBands (
        band_id       INT           IDENTITY(1,1) NOT NULL,
        indicator_id  INT           NOT NULL,
        hardness_class NVARCHAR(20) NOT NULL,  -- 'soft' | 'medium' | 'hard' | 'very_hard'
        twqr_upper    FLOAT         NOT NULL,
        cev           FLOAT         NOT NULL,
        aev           FLOAT         NOT NULL,
        CONSTRAINT PK_WQ_TWQR_HardnessBands PRIMARY KEY (band_id),
        CONSTRAINT FK_TWQRBands_Indicator FOREIGN KEY (indicator_id) REFERENCES dbo.WQ_Indicators(indicator_id),
        CONSTRAINT UQ_TWQRBands_IndClass UNIQUE (indicator_id, hardness_class)
    );
    CREATE INDEX IX_TWQRBands_Indicator ON dbo.WQ_TWQR_HardnessBands(indicator_id);
    PRINT 'Created dbo.WQ_TWQR_HardnessBands';
END
ELSE
    PRINT 'Table dbo.WQ_TWQR_HardnessBands already exists — skipped.';
GO

-- ─── 3. TWQR compliance columns on WQ_Measurements (separate from SANS ones) ─
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Measurements') AND name='is_compliant_twqr')
    ALTER TABLE dbo.WQ_Measurements ADD is_compliant_twqr BIT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Measurements') AND name='flag_twqr')
    ALTER TABLE dbo.WQ_Measurements ADD flag_twqr NVARCHAR(10) NULL;
GO

-- ─── 4. Seed TWQR values for every org that currently has WQ_Indicators ──────
-- (today that's org 1 "Default" and org 3 "Offingteck", each with their own
--  independent copy of the 43 indicators post tenant-ownership migration).
-- Fixed (non-hardness) toxicant limits — all "<=" ceiling values:
DECLARE @org INT;
DECLARE org_cursor CURSOR FOR SELECT DISTINCT org_id FROM dbo.WQ_Indicators;
OPEN org_cursor;
FETCH NEXT FROM org_cursor INTO @org;
WHILE @@FETCH_STATUS = 0
BEGIN
    -- Arsenic: TWQR 10 ug/L = 0.01 mg/L, CEV 20 ug/L = 0.02, AEV 130 ug/L = 0.13
    UPDATE dbo.WQ_Indicators SET twqr_upper=0.01, twqr_cev=0.02, twqr_aev=0.13,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996), Aquatic Ecosystems'
        WHERE org_id=@org AND indicator_code='AS';

    -- Chromium: using Cr(VI) as the conservative/protective default for our
    -- generic "Chromium (total)" indicator. TWQR 7 ug/L=0.007, CEV 14=0.014, AEV 200=0.2
    UPDATE dbo.WQ_Indicators SET twqr_upper=0.007, twqr_cev=0.014, twqr_aev=0.2,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996) — Cr(VI) criteria used as conservative default'
        WHERE org_id=@org AND indicator_code='CR';

    -- Cyanide (free): TWQR 1 ug/L=0.001, CEV 4=0.004, AEV 110=0.11
    UPDATE dbo.WQ_Indicators SET twqr_upper=0.001, twqr_cev=0.004, twqr_aev=0.11,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996), Aquatic Ecosystems'
        WHERE org_id=@org AND indicator_code='CN';

    -- Fluoride: TWQR 750 ug/L=0.75, CEV 1500=1.5, AEV 2540=2.54
    UPDATE dbo.WQ_Indicators SET twqr_upper=0.75, twqr_cev=1.5, twqr_aev=2.54,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996), Aquatic Ecosystems'
        WHERE org_id=@org AND indicator_code='FL';

    -- Manganese: TWQR 180 ug/L=0.18, CEV 370=0.37, AEV 1300=1.3
    UPDATE dbo.WQ_Indicators SET twqr_upper=0.18, twqr_cev=0.37, twqr_aev=1.3,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996), Aquatic Ecosystems'
        WHERE org_id=@org AND indicator_code='MN';

    -- Mercury (total): TWQR 0.04 ug/L=0.00004, CEV 0.08=0.00008, AEV 1.7=0.0017
    UPDATE dbo.WQ_Indicators SET twqr_upper=0.00004, twqr_cev=0.00008, twqr_aev=0.0017,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996), Aquatic Ecosystems'
        WHERE org_id=@org AND indicator_code='HG';

    -- pH: guideline TWQR is background +/- 0.5 units (site-specific, requires a
    -- baseline this app doesn't yet track) — using a conservative fallback
    -- range so the matrix isn't blank, clearly documented as an approximation.
    UPDATE dbo.WQ_Indicators SET twqr_lower=6.5, twqr_upper=9.0,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996) — fallback range; true TWQR is site-specific (background +/-0.5 pH units)'
        WHERE org_id=@org AND indicator_code='PH';

    -- Dissolved Oxygen: guideline criterion is >=80% saturation (temperature-
    -- dependent, not a fixed mg/L number) — using a conservative mg/L fallback.
    UPDATE dbo.WQ_Indicators SET twqr_lower=6.0,
        twqr_basis='fixed', twqr_reference='DWAF Vol 7 (1996) — fallback mg/L floor; true criterion is >=80% saturation (temperature-dependent)'
        WHERE org_id=@org AND indicator_code='DO';

    -- Total Phosphorus: trophic-band nutrient enrichment, not a toxicant.
    -- Practical pass/fail cutover at the eutrophic boundary (25 ug/L); full
    -- band scheme (oligotrophic<5 / mesotrophic 5-25 / eutrophic 25-250 /
    -- hypertrophic>250 ug/L) is documented in twqr_reference.
    UPDATE dbo.WQ_Indicators SET twqr_upper=25,
        twqr_basis='trophic_band',
        twqr_reference='DWAF Vol 7 (1996) trophic bands (ug/L): oligotrophic<5, mesotrophic 5-25, eutrophic 25-250, hypertrophic>250'
        WHERE org_id=@org AND indicator_code='TP';

    -- Not individually assessable under TWQR in v1: NH4/NO2/NO3 only feed the
    -- derived "Inorganic Nitrogen" trophic analytics endpoint (sum of the
    -- three, as N), not a per-indicator compliance flag. TDS/Iron/Temperature
    -- are background-baseline-relative per the guideline and not faked here.
    UPDATE dbo.WQ_Indicators SET twqr_basis='not_applicable',
        twqr_reference='DWAF Vol 7 (1996) — background/site-baseline-relative or contributes only to a derived multi-indicator metric; not assessed as a standalone TWQR in this version'
        WHERE org_id=@org AND indicator_code IN ('NH4','NO2','NO3','TDS','FE','TEMP');

    FETCH NEXT FROM org_cursor INTO @org;
END
CLOSE org_cursor;
DEALLOCATE org_cursor;
GO

-- Hardness-dependent bands (Cadmium, Copper, Lead) — 3 indicators x 4 bands,
-- seeded once per org's copy of each indicator.
DECLARE @org2 INT;
DECLARE org_cursor2 CURSOR FOR SELECT DISTINCT org_id FROM dbo.WQ_Indicators;
OPEN org_cursor2;
FETCH NEXT FROM org_cursor2 INTO @org2;
WHILE @@FETCH_STATUS = 0
BEGIN
    UPDATE dbo.WQ_Indicators SET twqr_basis='hardness_dependent',
        twqr_reference='DWAF Vol 7 (1996) — hardness-dependent bands, see WQ_TWQR_HardnessBands'
        WHERE org_id=@org2 AND indicator_code IN ('CD','CU','PB');

    -- Cadmium: TWQR/CEV/AEV (ug/L) Soft<60 / Medium 60-119 / Hard 120-180 / VeryHard>180 mg CaCO3/L
    -- converted to mg/L: TWQR 0.15/0.25/0.35/0.40 ug/L -> 0.00015/0.00025/0.00035/0.00040
    --                     CEV  0.3/0.5/0.7/0.8   ug/L -> 0.0003/0.0005/0.0007/0.0008
    --                     AEV  3/6/10/13         ug/L -> 0.003/0.006/0.010/0.013
    IF EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org2 AND indicator_code='CD')
    BEGIN
        DECLARE @cd_id INT = (SELECT indicator_id FROM dbo.WQ_Indicators WHERE org_id=@org2 AND indicator_code='CD');
        IF NOT EXISTS (SELECT 1 FROM dbo.WQ_TWQR_HardnessBands WHERE indicator_id=@cd_id)
        BEGIN
            INSERT INTO dbo.WQ_TWQR_HardnessBands (indicator_id, hardness_class, twqr_upper, cev, aev) VALUES
                (@cd_id, 'soft',      0.00015, 0.0003, 0.003),
                (@cd_id, 'medium',    0.00025, 0.0005, 0.006),
                (@cd_id, 'hard',      0.00035, 0.0007, 0.010),
                (@cd_id, 'very_hard', 0.00040, 0.0008, 0.013);
        END
    END

    -- Copper: TWQR 0.3/0.8/1.2/1.4 ug/L -> 0.0003/0.0008/0.0012/0.0014
    --         CEV  0.53/1.5/2.4/2.8 ug/L -> 0.00053/0.0015/0.0024/0.0028
    --         AEV  1.6/4.6/7.5/12   ug/L -> 0.0016/0.0046/0.0075/0.012
    IF EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org2 AND indicator_code='CU')
    BEGIN
        DECLARE @cu_id INT = (SELECT indicator_id FROM dbo.WQ_Indicators WHERE org_id=@org2 AND indicator_code='CU');
        IF NOT EXISTS (SELECT 1 FROM dbo.WQ_TWQR_HardnessBands WHERE indicator_id=@cu_id)
        BEGIN
            INSERT INTO dbo.WQ_TWQR_HardnessBands (indicator_id, hardness_class, twqr_upper, cev, aev) VALUES
                (@cu_id, 'soft',      0.0003,  0.00053, 0.0016),
                (@cu_id, 'medium',    0.0008,  0.0015,  0.0046),
                (@cu_id, 'hard',      0.0012,  0.0024,  0.0075),
                (@cu_id, 'very_hard', 0.0014,  0.0028,  0.012);
        END
    END

    -- Lead: TWQR 0.2/0.5/1.0/1.2 ug/L -> 0.0002/0.0005/0.0010/0.0012
    --       CEV  0.5/1.0/2.0/2.4 ug/L -> 0.0005/0.0010/0.0020/0.0024
    --       AEV  4/7/13/16       ug/L -> 0.004/0.007/0.013/0.016
    IF EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org2 AND indicator_code='PB')
    BEGIN
        DECLARE @pb_id INT = (SELECT indicator_id FROM dbo.WQ_Indicators WHERE org_id=@org2 AND indicator_code='PB');
        IF NOT EXISTS (SELECT 1 FROM dbo.WQ_TWQR_HardnessBands WHERE indicator_id=@pb_id)
        BEGIN
            INSERT INTO dbo.WQ_TWQR_HardnessBands (indicator_id, hardness_class, twqr_upper, cev, aev) VALUES
                (@pb_id, 'soft',      0.0002, 0.0005, 0.004),
                (@pb_id, 'medium',    0.0005, 0.0010, 0.007),
                (@pb_id, 'hard',      0.0010, 0.0020, 0.013),
                (@pb_id, 'very_hard', 0.0012, 0.0024, 0.016);
        END
    END

    FETCH NEXT FROM org_cursor2 INTO @org2;
END
CLOSE org_cursor2;
DEALLOCATE org_cursor2;
GO

PRINT 'TWQR seed complete for all existing orgs.';
GO

-- ============================================================================
-- Part 2 — Water Safety Plan: Risk Register + Corrective Actions
-- ============================================================================

IF OBJECT_ID('dbo.WQ_Risk_Register', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Risk_Register (
        risk_id             INT           IDENTITY(1,1) NOT NULL,
        org_id              INT           NOT NULL,
        station_id          INT           NULL,   -- NULL = org-wide hazard
        linked_indicator_id INT           NULL,
        hazard_description  NVARCHAR(500) NOT NULL,
        hazard_source       NVARCHAR(300) NULL,
        likelihood          INT           NOT NULL CONSTRAINT CK_Risk_Likelihood CHECK (likelihood BETWEEN 1 AND 5),
        severity            INT           NOT NULL CONSTRAINT CK_Risk_Severity CHECK (severity BETWEEN 1 AND 5),
        risk_score          AS (likelihood * severity) PERSISTED,
        control_measure     NVARCHAR(500) NULL,
        monitoring_frequency NVARCHAR(100) NULL,
        responsible_person  NVARCHAR(200) NULL,
        status              NVARCHAR(20)  NOT NULL CONSTRAINT DF_Risk_Status DEFAULT 'open'
                                CONSTRAINT CK_Risk_Status CHECK (status IN ('open','mitigated','closed')),
        review_date         DATE          NULL,
        created_at          DATETIME2     NOT NULL CONSTRAINT DF_Risk_Created DEFAULT GETDATE(),
        updated_at          DATETIME2     NOT NULL CONSTRAINT DF_Risk_Updated DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Risk_Register PRIMARY KEY (risk_id),
        CONSTRAINT FK_Risk_Org        FOREIGN KEY (org_id)              REFERENCES dbo.Organizations(org_id),
        CONSTRAINT FK_Risk_Station    FOREIGN KEY (station_id)          REFERENCES dbo.WQ_Stations(station_id),
        CONSTRAINT FK_Risk_Indicator  FOREIGN KEY (linked_indicator_id) REFERENCES dbo.WQ_Indicators(indicator_id)
    );
    CREATE INDEX IX_Risk_Org ON dbo.WQ_Risk_Register(org_id);
    PRINT 'Created dbo.WQ_Risk_Register';
END
ELSE
    PRINT 'Table dbo.WQ_Risk_Register already exists — skipped.';
GO

IF OBJECT_ID('dbo.WQ_Corrective_Actions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Corrective_Actions (
        action_id      INT           IDENTITY(1,1) NOT NULL,
        org_id         INT           NOT NULL,
        station_id     INT           NULL,
        indicator_id   INT           NULL,
        reading_id     INT           NULL,   -- the specific violation event that triggered this, if any
        description    NVARCHAR(500) NOT NULL,
        root_cause     NVARCHAR(500) NULL,
        action_taken   NVARCHAR(500) NULL,
        assigned_to    NVARCHAR(200) NULL,
        due_date       DATE          NULL,
        status         NVARCHAR(20)  NOT NULL CONSTRAINT DF_CorrAct_Status DEFAULT 'open'
                            CONSTRAINT CK_CorrAct_Status CHECK (status IN ('open','in_progress','closed','overdue')),
        auto_generated BIT           NOT NULL CONSTRAINT DF_CorrAct_Auto DEFAULT 0,
        closed_at      DATETIME2     NULL,
        created_at      DATETIME2    NOT NULL CONSTRAINT DF_CorrAct_Created DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Corrective_Actions PRIMARY KEY (action_id),
        CONSTRAINT FK_CorrAct_Org       FOREIGN KEY (org_id)       REFERENCES dbo.Organizations(org_id),
        CONSTRAINT FK_CorrAct_Station   FOREIGN KEY (station_id)   REFERENCES dbo.WQ_Stations(station_id),
        CONSTRAINT FK_CorrAct_Indicator FOREIGN KEY (indicator_id) REFERENCES dbo.WQ_Indicators(indicator_id),
        CONSTRAINT FK_CorrAct_Reading   FOREIGN KEY (reading_id)   REFERENCES dbo.WQ_Readings(reading_id)
    );
    CREATE INDEX IX_CorrAct_Org ON dbo.WQ_Corrective_Actions(org_id);
    PRINT 'Created dbo.WQ_Corrective_Actions';
END
ELSE
    PRINT 'Table dbo.WQ_Corrective_Actions already exists — skipped.';
GO

PRINT '';
PRINT '========================================';
PRINT 'TWQR + WSP migration complete.';
PRINT '  - WQ_Indicators gained twqr_lower/upper/cev/aev/basis/reference';
PRINT '  - WQ_TWQR_HardnessBands created + seeded (Cd, Cu, Pb x 4 bands, per org)';
PRINT '  - WQ_Measurements gained is_compliant_twqr / flag_twqr (SANS columns untouched)';
PRINT '  - WQ_Risk_Register and WQ_Corrective_Actions created';
PRINT '========================================';
GO
