-- ============================================================================
-- HydroCore Diagnostics Migration
-- Run ONCE against GroundwaterAnalysis, AFTER twqr_standard_migration.sql.
-- Safe to re-run (all statements are idempotent).
--
-- Adds:
--   1. WQ_Diagnostic_Findings - contamination source-attribution engine output
--      (one row per reading x candidate hypothesis, computed at upload time).
--   2. WQ_Livestock_TDS_Bands - DWAF Vol 5 (1996) TDS-per-species severity
--      table (5 species x 10 bands), real numbers extracted from the guideline.
--   3. WQ_Aquaculture_Criteria - DWAF Vol 6 (1996) fish-health TWQR criteria,
--      real numbers extracted from the guideline, converted to match this
--      app's existing per-indicator storage units (verified against
--      wq_schema_v2.sql before writing this file).
--   4. OPTIONAL WQ_Stations.aquifer_type / depth_m - nullable, used only to
--      boost diagnostic confidence for mining-related contamination when
--      present; the engine runs fully without them.
--   5. OPTIONAL WQ_Indicators rows for Bromide + stable isotopes - tracer-only
--      parameters, never required, additive confidence boosters only.
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- ─── 1. Diagnostic Findings ──────────────────────────────────────────────────
IF OBJECT_ID('dbo.WQ_Diagnostic_Findings', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Diagnostic_Findings (
        finding_id            INT           IDENTITY(1,1) NOT NULL,
        reading_id            INT           NOT NULL,
        station_id            INT           NOT NULL,
        org_id                INT           NOT NULL,
        source_code           NVARCHAR(30)  NOT NULL,
        source_label          NVARCHAR(100) NOT NULL,
        confidence_pct        FLOAT         NOT NULL CONSTRAINT CK_DiagFind_Conf CHECK (confidence_pct BETWEEN 0 AND 100),
        matched_signals       NVARCHAR(MAX) NULL,
        contradicting_signals NVARCHAR(MAX) NULL,
        contextual_modifiers_applied NVARCHAR(MAX) NULL,
        explanation_text      NVARCHAR(1000) NULL,
        engine_version        NVARCHAR(20)  NOT NULL CONSTRAINT DF_DiagFind_Ver DEFAULT 'v1',
        created_at            DATETIME2     NOT NULL CONSTRAINT DF_DiagFind_Created DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Diagnostic_Findings PRIMARY KEY (finding_id),
        CONSTRAINT FK_DiagFind_Reading FOREIGN KEY (reading_id) REFERENCES dbo.WQ_Readings(reading_id) ON DELETE CASCADE,
        CONSTRAINT FK_DiagFind_Station FOREIGN KEY (station_id) REFERENCES dbo.WQ_Stations(station_id),
        CONSTRAINT FK_DiagFind_Org     FOREIGN KEY (org_id)     REFERENCES dbo.Organizations(org_id),
        CONSTRAINT UQ_DiagFind_ReadingSource UNIQUE (reading_id, source_code)
    );
    CREATE INDEX IX_DiagFind_Station ON dbo.WQ_Diagnostic_Findings(station_id);
    CREATE INDEX IX_DiagFind_Org     ON dbo.WQ_Diagnostic_Findings(org_id);
    CREATE INDEX IX_DiagFind_Source  ON dbo.WQ_Diagnostic_Findings(source_code);
    PRINT 'Created dbo.WQ_Diagnostic_Findings';
END
ELSE
    PRINT 'Table dbo.WQ_Diagnostic_Findings already exists - skipped.';
GO

-- ─── 2. Livestock TDS-per-species bands (DWAF Vol 5, 1996) ──────────────────
-- Universal reference table, not per-org (same reasoning as the AMD flagging
-- thresholds being a plain Python constant rather than a DB row - these are
-- fixed guideline values, not tenant-editable).
IF OBJECT_ID('dbo.WQ_Livestock_TDS_Bands', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Livestock_TDS_Bands (
        band_id         INT           IDENTITY(1,1) NOT NULL,
        species         NVARCHAR(30)  NOT NULL,
        tds_min_mgL     FLOAT         NULL,
        tds_max_mgL     FLOAT         NULL,
        severity_rating TINYINT       NOT NULL CONSTRAINT CK_LivestockTDS_Sev CHECK (severity_rating BETWEEN 0 AND 4),
        band_label      NVARCHAR(300) NOT NULL,
        reference       NVARCHAR(200) NOT NULL CONSTRAINT DF_LivestockTDS_Ref DEFAULT 'DWAF Vol 5 (1996), Agricultural Water Use: Livestock Watering',
        CONSTRAINT PK_WQ_Livestock_TDS_Bands PRIMARY KEY (band_id)
    );
    CREATE INDEX IX_LivestockTDS_Species ON dbo.WQ_Livestock_TDS_Bands(species);
    PRINT 'Created dbo.WQ_Livestock_TDS_Bands';
END
ELSE
    PRINT 'Table dbo.WQ_Livestock_TDS_Bands already exists - skipped.';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Livestock_TDS_Bands)
BEGIN
    DECLARE @lbl0 NVARCHAR(300) = 'No significant adverse effects. Immediate access allowed without prior exposure to saline waters.';
    DECLARE @lbl1 NVARCHAR(300) = 'Possible initial reluctance to drink, but temporary - no significant adverse effects. Immediate access allowed with prior exposure to saline water.';
    DECLARE @lbl2 NVARCHAR(300) = 'Initial reluctance may reduce intake/production; stock typically adapt within a week. Access only with prior saline exposure.';
    DECLARE @lbl3 NVARCHAR(300) = 'Production likely to decline significantly; recovers only on TWQR water. Limited-time access only, with prior saline exposure.';
    DECLARE @lbl4 NVARCHAR(300) = 'Extreme caution required - no immediate access; stock must be adapted incrementally to this water source.';

    INSERT INTO dbo.WQ_Livestock_TDS_Bands (species, tds_min_mgL, tds_max_mgL, severity_rating, band_label) VALUES
        ('Sheep',           0,     1000,  0, @lbl0),
        ('Sheep',        1000,     2000,  0, @lbl0),
        ('Sheep',        2000,     3000,  0, @lbl0),
        ('Sheep',        3000,     4000,  1, @lbl1),
        ('Sheep',        4000,     5000,  1, @lbl1),
        ('Sheep',        5000,     6000,  1, @lbl1),
        ('Sheep',        6000,     7000,  2, @lbl2),
        ('Sheep',        7000,    10000,  2, @lbl2),
        ('Sheep',       10000,    13000,  2, @lbl2),
        ('Sheep',       13000,     NULL,  3, @lbl3),

        ('Beef',            0,     1000,  0, @lbl0),
        ('Beef',         1000,     2000,  0, @lbl0),
        ('Beef',         2000,     3000,  1, @lbl1),
        ('Beef',         3000,     4000,  1, @lbl1),
        ('Beef',         4000,     5000,  1, @lbl1),
        ('Beef',         5000,     6000,  1, @lbl1),
        ('Beef',         6000,     7000,  2, @lbl2),
        ('Beef',         7000,    10000,  3, @lbl3),
        ('Beef',        10000,    13000,  4, @lbl4),
        ('Beef',        13000,     NULL,  4, @lbl4),

        ('Horses',           0,    1000,  0, @lbl0),
        ('Horses',        1000,    2000,  0, @lbl0),
        ('Horses',        2000,    3000,  1, @lbl1),
        ('Horses',        3000,    4000,  2, @lbl2),
        ('Horses',        4000,    5000,  2, @lbl2),
        ('Horses',        5000,    6000,  2, @lbl2),
        ('Horses',        6000,    7000,  3, @lbl3),
        ('Horses',        7000,   10000,  4, @lbl4),
        ('Horses',       10000,   13000,  4, @lbl4),
        ('Horses',       13000,    NULL,  4, @lbl4),

        ('Dairy',            0,    1000,  0, @lbl0),
        ('Dairy',         1000,    2000,  1, @lbl1),
        ('Dairy',         2000,    3000,  1, @lbl1),
        ('Dairy',         3000,    4000,  2, @lbl2),
        ('Dairy',         4000,    5000,  3, @lbl3),
        ('Dairy',         5000,    6000,  3, @lbl3),
        ('Dairy',         6000,    7000,  4, @lbl4),
        ('Dairy',         7000,   10000,  4, @lbl4),
        ('Dairy',        10000,   13000,  4, @lbl4),
        ('Dairy',        13000,    NULL,  4, @lbl4),

        ('Pigs & Poultry',   0,    1000,  0, @lbl0),
        ('Pigs & Poultry',1000,    2000,  1, @lbl1),
        ('Pigs & Poultry',2000,    3000,  2, @lbl2),
        ('Pigs & Poultry',3000,    4000,  3, @lbl3),
        ('Pigs & Poultry',4000,    5000,  4, @lbl4),
        ('Pigs & Poultry',5000,    6000,  4, @lbl4),
        ('Pigs & Poultry',6000,    7000,  4, @lbl4),
        ('Pigs & Poultry',7000,   10000,  4, @lbl4),
        ('Pigs & Poultry',10000,  13000,  4, @lbl4),
        ('Pigs & Poultry',13000,   NULL,  4, @lbl4);

    PRINT 'Seeded dbo.WQ_Livestock_TDS_Bands (50 rows, 5 species x 10 bands).';
END
GO

-- ─── 3. Aquaculture criteria (DWAF Vol 6, 1996) ──────────────────────────────
-- Universal reference table (same reasoning as #2). indicator_code matches
-- WQ_Indicators.indicator_code; hardness_class is only used for Cadmium.
-- All bounds converted from the guideline's stated units to match this app's
-- existing per-indicator storage unit (verified against wq_schema_v2.sql).
IF OBJECT_ID('dbo.WQ_Aquaculture_Criteria', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Aquaculture_Criteria (
        criterion_id    INT           IDENTITY(1,1) NOT NULL,
        indicator_code  NVARCHAR(20)  NOT NULL,
        hardness_class  NVARCHAR(20)  NULL,
        twqr_lower      FLOAT         NULL,
        twqr_upper      FLOAT         NULL,
        unit            NVARCHAR(20)  NULL,
        note            NVARCHAR(400) NULL,
        reference       NVARCHAR(200) NOT NULL CONSTRAINT DF_AquaCrit_Ref DEFAULT 'DWAF Vol 6 (1996), Agricultural Water Use: Aquaculture',
        CONSTRAINT PK_WQ_Aquaculture_Criteria PRIMARY KEY (criterion_id)
    );
    CREATE INDEX IX_AquaCrit_Indicator ON dbo.WQ_Aquaculture_Criteria(indicator_code);
    PRINT 'Created dbo.WQ_Aquaculture_Criteria';
END
ELSE
    PRINT 'Table dbo.WQ_Aquaculture_Criteria already exists - skipped.';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Aquaculture_Criteria)
BEGIN
    INSERT INTO dbo.WQ_Aquaculture_Criteria (indicator_code, hardness_class, twqr_lower, twqr_upper, unit, note) VALUES
        ('PH',   NULL, 6.5,    9.0,     NULL,   'Most species tolerate/reproduce successfully in this range; <4.0 lethal to most salmonids, >9.0 upper tolerance for most species.'),
        ('DO',   NULL, 5.0,    21.0,    'mg/L', 'General floor across species groups (cold-water fish need 6-9 mg/L for optimal growth); >21 mg/L supersaturation risk causes gas-bubble mortality.'),
        ('NH4',  NULL, NULL,   0.3,     'mg/L', 'Un-ionised ammonia TWQR for warm-water fish (most common in SA aquaculture, e.g. tilapia/catfish) is <=0.3 mg NH3/L; cold-water species (trout) are far more sensitive at <=0.025 mg NH3/L. Compared directly against total ammonia (as NH4) per this app''s existing simplification (same approach used for TWQR aquatic-ecosystem ammonia).'),
        ('NO2',  NULL, NULL,   0.164,   'mg/L', 'DWAF TWQR is 0-0.05 mg NO2-N/L, converted to mg NO2/L (x3.286 molar ratio) to match this app''s stored Nitrite unit. Protective for salmonids and most other species.'),
        ('NO3',  NULL, NULL,   1328.0,  'mg/L', 'DWAF TWQR is <300 mg NO3-N/L, converted to mg NO3/L (x4.427 molar ratio). Nitrate is the least toxic inorganic nitrogen compound to fish - this is a very permissive band relative to drinking-water/TWQR-ecosystem limits.'),
        ('TP',   NULL, NULL,   100.0,   'ug/L', 'DWAF criterion ~0.1 mg/L orthophosphate (100 ug/L) ensures protection of aquatic organisms with no trophic status change; optimum growth for carp/goldfish at or below 600 ug/L.'),
        ('FE',   NULL, NULL,   0.01,    'mg/L', 'No known adverse effects on fish below this concentration; general lethal threshold range is 0.2-1.75 mg/L.'),
        ('MN',   NULL, NULL,   0.1,     'mg/L', 'Recommended minimal value for pond culture; 0.1-0.5 mg/L sublethal effects, >0.5 mg/L increasing lethal risk.'),
        ('AS',   NULL, 0.0,    0.05,    'mg/L', 'TWQR for arsenic in water bodies containing fish.'),
        ('CD', 'soft',      NULL, 0.0002, 'mg/L', 'Hardness 0-60 mg CaCO3/L.'),
        ('CD', 'medium',    NULL, 0.0008, 'mg/L', 'Hardness 60-120 mg CaCO3/L.'),
        ('CD', 'hard',      NULL, 0.0013, 'mg/L', 'Hardness 120-180 mg CaCO3/L.'),
        ('CD', 'very_hard', NULL, 0.0018, 'mg/L', 'Hardness >180 mg CaCO3/L.'),
        ('CR',   NULL, NULL,   0.02,    'mg/L', 'DWAF TWQR <20 ug/L Cr(VI), converted to mg/L. Since chromium bio-accumulates, this TWQR is protective of all freshwater fish species.'),
        ('CU',   NULL, NULL,   0.005,   'mg/L', 'Fish are far more copper-sensitive than drinking-water standards assume - this is much stricter than the SANS/TWQR-ecosystem copper limits.'),
        ('PB',   NULL, NULL,   0.01,    'mg/L', 'TWQR for soft water - no adverse effects on fish health below this concentration.'),
        ('HG',   NULL, NULL,   0.001,   'mg/L', 'DWAF TWQR <1 ug/L, converted to mg/L. No adverse effects on fish populations below this concentration.'),
        ('CN',   NULL, NULL,   0.02,    'mg/L', 'Guideline is tentative (based on limited information) per DWAF Vol 6 - no known adverse effects below this concentration.'),
        ('PHENOL', NULL, NULL, 2.0,     'mg/L', 'TWQR for non-salmonid species (dominant in SA aquaculture); salmonid species need a stricter <1 mg/L. Halve this threshold if water temperature is below 5degC.'),
        ('TEMP', NULL, 17.0,   32.0,    'degC',   'Broad envelope across species groups (cold-water optimum 17-18degC, warm-water/tilapia/catfish optimum 27-30degC) - a rough sanity band only since this app does not track farmed species per station.'),
        ('TDS',  NULL, NULL,   2000.0,  'mg/L', 'TWQR for stenohaline (salinity-sensitive) species (<2 g/L); euryhaline species tolerate up to 10,000-17,000 mg/L with acclimation.'),
        ('HARD', NULL, 20.0,   100.0,   'mg/L as CaCO3', 'Recommended range for most freshwater fish; >300 mg/L affects survival/growth of freshwater prawns specifically.'),
        ('SS',   NULL, NULL,   20000.0, 'mg/L', 'TWQR for turbid-water tolerant species (e.g. carp, catfish, bass).'),
        ('TURB', NULL, NULL,   25.0,    'NTU',  'TWQR for clear-water species (e.g. trout) - far stricter than turbid-water-tolerant species.');

    PRINT 'Seeded dbo.WQ_Aquaculture_Criteria (24 rows, real DWAF Vol 6 numbers).';
END
GO

-- ─── 4. OPTIONAL - WQ_Stations aquifer context (nullable, never required) ────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Stations') AND name='aquifer_type')
    ALTER TABLE dbo.WQ_Stations ADD aquifer_type NVARCHAR(20) NULL
        CONSTRAINT CK_WQSt_AquiferType CHECK (aquifer_type IN ('unconfined','semi-confined','confined'));
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Stations') AND name='depth_m')
    ALTER TABLE dbo.WQ_Stations ADD depth_m FLOAT NULL;
GO

-- ─── 5. OPTIONAL - Bromide + isotope tracer indicators ───────────────────────
-- Ordinary WQ_Indicators rows, seeded per-org (tenant-owned table, same
-- cursor pattern as twqr_standard_migration.sql). twqr_basis='not_applicable'
-- since these are diagnostic tracers, not compliance parameters - the
-- diagnostic engine uses them only as optional confidence boosters when a lab
-- happens to report them.
DECLARE @org3 INT;
DECLARE org_cursor3 CURSOR FOR SELECT DISTINCT org_id FROM dbo.WQ_Indicators;
OPEN org_cursor3;
FETCH NEXT FROM org_cursor3 INTO @org3;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org3 AND indicator_code='BR')
        INSERT INTO dbo.WQ_Indicators (indicator_code, indicator_name, unit, std_reference, display_order,
            twqr_basis, twqr_reference, equivalent_weight, ion_type, org_id)
        VALUES ('BR', 'Bromide', 'mg/L', 'Tracer - optional Cl/Br ratio booster for diagnostic engine', 44,
            'not_applicable', 'Not a compliance parameter - used only as an optional confidence booster for saline-intrusion source attribution when reported.',
            79.90, 'anion', @org3);

    IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org3 AND indicator_code='D15N')
        INSERT INTO dbo.WQ_Indicators (indicator_code, indicator_name, unit, std_reference, display_order,
            twqr_basis, twqr_reference, org_id)
        VALUES ('D15N', 'Nitrogen-15 isotope ratio (delta-15N)', 'permil', 'Tracer - optional nitrate-source-attribution booster for diagnostic engine', 45,
            'not_applicable', 'Not a compliance parameter - used only as an optional confidence booster to distinguish sewage/manure vs. fertiliser vs. atmospheric nitrogen sources when reported.', @org3);

    IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org3 AND indicator_code='D18O')
        INSERT INTO dbo.WQ_Indicators (indicator_code, indicator_name, unit, std_reference, display_order,
            twqr_basis, twqr_reference, org_id)
        VALUES ('D18O', 'Oxygen-18 isotope ratio (delta-18O)', 'permil', 'Tracer - optional groundwater-source-attribution booster for diagnostic engine', 46,
            'not_applicable', 'Not a compliance parameter - used only as an optional confidence booster for water-source/recharge attribution when reported.', @org3);

    IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org3 AND indicator_code='D11B')
        INSERT INTO dbo.WQ_Indicators (indicator_code, indicator_name, unit, std_reference, display_order,
            twqr_basis, twqr_reference, org_id)
        VALUES ('D11B', 'Boron-11 isotope ratio (delta-11B)', 'permil', 'Tracer - optional sewage-vs-fertiliser booster for diagnostic engine', 47,
            'not_applicable', 'Not a compliance parameter - used only as an optional confidence booster to distinguish sewage/wastewater from agricultural sources when reported.', @org3);

    IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE org_id=@org3 AND indicator_code='D2H')
        INSERT INTO dbo.WQ_Indicators (indicator_code, indicator_name, unit, std_reference, display_order,
            twqr_basis, twqr_reference, org_id)
        VALUES ('D2H', 'Deuterium isotope ratio (delta-2H)', 'permil', 'Tracer - optional groundwater-source-attribution booster for diagnostic engine', 48,
            'not_applicable', 'Not a compliance parameter - used only as an optional confidence booster for water-source/recharge attribution when reported.', @org3);

    FETCH NEXT FROM org_cursor3 INTO @org3;
END
CLOSE org_cursor3;
DEALLOCATE org_cursor3;
GO

PRINT '';
PRINT '========================================';
PRINT 'Diagnostics migration complete.';
PRINT '  - WQ_Diagnostic_Findings created';
PRINT '  - WQ_Livestock_TDS_Bands created + seeded (DWAF Vol 5, 50 rows)';
PRINT '  - WQ_Aquaculture_Criteria created + seeded (DWAF Vol 6, 24 rows)';
PRINT '  - WQ_Stations gained OPTIONAL aquifer_type / depth_m';
PRINT '  - WQ_Indicators gained OPTIONAL BR/D15N/D18O/D11B/D2H tracer rows, per org';
PRINT '========================================';
GO
