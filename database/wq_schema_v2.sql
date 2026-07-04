-- ============================================================================
-- HydroCore — Water Quality Schema v2 (incremental additions)
-- Run after wq_schema.sql.  All guards are safe to re-run.
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- ─── Extend WQ_Indicators with SANS 241 risk classification fields ───────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='risk_class')
    ALTER TABLE dbo.WQ_Indicators ADD risk_class NVARCHAR(30) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='sans_class1_limit')
    ALTER TABLE dbo.WQ_Indicators ADD sans_class1_limit FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='sans_class2_limit')
    ALTER TABLE dbo.WQ_Indicators ADD sans_class2_limit FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='method_detection_limit')
    ALTER TABLE dbo.WQ_Indicators ADD method_detection_limit FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='equivalent_weight')
    ALTER TABLE dbo.WQ_Indicators ADD equivalent_weight FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='ion_type')
    ALTER TABLE dbo.WQ_Indicators ADD ion_type NVARCHAR(10) NULL; -- 'cation' | 'anion' | NULL
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Indicators') AND name='blue_drop_category')
    ALTER TABLE dbo.WQ_Indicators ADD blue_drop_category NVARCHAR(30) NULL;
    -- 'microbiological' | 'chemical_health' | 'chemical_aesthetic' | 'physical' | NULL
GO

-- ─── Extend WQ_Measurements with data quality fields ─────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Measurements') AND name='quality_flag')
    ALTER TABLE dbo.WQ_Measurements ADD quality_flag NVARCHAR(20) NOT NULL CONSTRAINT DF_WQM_QFlag DEFAULT 'Preliminary';
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Measurements') AND name='is_censored')
    ALTER TABLE dbo.WQ_Measurements ADD is_censored BIT NOT NULL CONSTRAINT DF_WQM_Cens DEFAULT 0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Measurements') AND name='censored_limit')
    ALTER TABLE dbo.WQ_Measurements ADD censored_limit FLOAT NULL;
GO

-- ─── Extend WQ_Readings with hydrological + computed fields ──────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Readings') AND name='season')
    ALTER TABLE dbo.WQ_Readings ADD season NVARCHAR(10) NULL;  -- 'Wet' | 'Dry'
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Readings') AND name='flow_rate_m3s')
    ALTER TABLE dbo.WQ_Readings ADD flow_rate_m3s FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Readings') AND name='ion_balance_error_pct')
    ALTER TABLE dbo.WQ_Readings ADD ion_balance_error_pct FLOAT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.WQ_Readings') AND name='notes')
    ALTER TABLE dbo.WQ_Readings ADD notes NVARCHAR(1000) NULL;
GO

-- ─── Alert configuration table ───────────────────────────────────────────────
IF OBJECT_ID('dbo.WQ_Alert_Config', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Alert_Config (
        alert_id        INT          IDENTITY(1,1) NOT NULL,
        org_id          INT          NOT NULL,
        indicator_id    INT          NOT NULL,
        station_id      INT          NULL,           -- NULL = all stations
        threshold_type  NVARCHAR(10) NOT NULL,       -- 'ABOVE' | 'BELOW' | 'HEALTH'
        threshold_value FLOAT        NOT NULL,
        alert_email     NVARCHAR(255) NULL,
        alert_whatsapp  NVARCHAR(30) NULL,
        is_active       BIT          NOT NULL CONSTRAINT DF_WQAlCfg_Active DEFAULT 1,
        created_at      DATETIME2    NOT NULL CONSTRAINT DF_WQAlCfg_Created DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Alert_Config    PRIMARY KEY (alert_id),
        CONSTRAINT FK_WQAlCfg_Indicator  FOREIGN KEY (indicator_id) REFERENCES dbo.WQ_Indicators(indicator_id),
        CONSTRAINT FK_WQAlCfg_Station    FOREIGN KEY (station_id)   REFERENCES dbo.WQ_Stations(station_id),
        CONSTRAINT CK_WQAlCfg_Type       CHECK (threshold_type IN ('ABOVE','BELOW','HEALTH'))
    );
    CREATE INDEX IX_WQAlCfg_Org  ON dbo.WQ_Alert_Config(org_id);
    PRINT 'Created table: dbo.WQ_Alert_Config';
END
ELSE
    PRINT 'Table dbo.WQ_Alert_Config already exists — skipped.';
GO

-- ─── Alert dispatch log ───────────────────────────────────────────────────────
IF OBJECT_ID('dbo.WQ_Alert_Log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Alert_Log (
        log_id         INT           IDENTITY(1,1) NOT NULL,
        org_id         INT           NOT NULL,
        alert_id       INT           NULL,
        reading_id     INT           NOT NULL,
        indicator_id   INT           NOT NULL,
        measured_val   FLOAT         NULL,
        channel        NVARCHAR(20)  NOT NULL,  -- 'email' | 'whatsapp'
        recipient      NVARCHAR(255) NOT NULL,
        status         NVARCHAR(20)  NOT NULL,  -- 'sent' | 'failed' | 'skipped'
        message_body   NVARCHAR(MAX) NULL,
        dispatched_at  DATETIME2     NOT NULL CONSTRAINT DF_WQAlLog_Disp DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Alert_Log   PRIMARY KEY (log_id),
        CONSTRAINT FK_WQAlLog_Reading    FOREIGN KEY (reading_id)   REFERENCES dbo.WQ_Readings(reading_id),
        CONSTRAINT FK_WQAlLog_Indicator  FOREIGN KEY (indicator_id) REFERENCES dbo.WQ_Indicators(indicator_id)
    );
    CREATE INDEX IX_WQAlLog_Org  ON dbo.WQ_Alert_Log(org_id);
    CREATE INDEX IX_WQAlLog_Date ON dbo.WQ_Alert_Log(dispatched_at DESC);
    PRINT 'Created table: dbo.WQ_Alert_Log';
END
ELSE
    PRINT 'Table dbo.WQ_Alert_Log already exists — skipped.';
GO

-- ─── Referential integrity: org_id must reference a real tenant ──────────────
-- (Guarded so this is safe to re-run and safe to apply to installs where the
--  tables above already existed without this constraint.)
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_WQAlCfg_Org')
    ALTER TABLE dbo.WQ_Alert_Config ADD CONSTRAINT FK_WQAlCfg_Org FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_WQAlLog_Org')
    ALTER TABLE dbo.WQ_Alert_Log ADD CONSTRAINT FK_WQAlLog_Org FOREIGN KEY (org_id) REFERENCES dbo.Organizations(org_id);
GO

-- ─── Update existing 15 indicators with new metadata ─────────────────────────
UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='physical',
    sans_class1_limit=6.0, sans_class2_limit=9.0
WHERE indicator_code='PH';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='chemical_aesthetic',
    sans_class1_limit=NULL, sans_class2_limit=70.0
WHERE indicator_code='EC';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='physical',
    sans_class1_limit=NULL, sans_class2_limit=10.0
WHERE indicator_code='SS';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='chemical_aesthetic',
    sans_class1_limit=NULL, sans_class2_limit=1000.0
WHERE indicator_code='TDS';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='physical',
    sans_class1_limit=NULL, sans_class2_limit=5.0
WHERE indicator_code='TURB';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='chemical_aesthetic',
    sans_class1_limit=NULL, sans_class2_limit=100.0,
    equivalent_weight=35.45, ion_type='anion'
WHERE indicator_code='CL';

UPDATE dbo.WQ_Indicators SET
    risk_class='health', blue_drop_category='chemical_health',
    sans_class1_limit=NULL, sans_class2_limit=1.0,
    method_detection_limit=0.05
WHERE indicator_code='FL';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='chemical_aesthetic',
    sans_class1_limit=NULL, sans_class2_limit=200.0,
    equivalent_weight=20.04, ion_type='cation'
WHERE indicator_code='CA';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='chemical_aesthetic',
    sans_class1_limit=NULL, sans_class2_limit=100.0,
    equivalent_weight=12.15, ion_type='cation'
WHERE indicator_code='MG';

UPDATE dbo.WQ_Indicators SET
    risk_class='health', blue_drop_category='chemical_health',
    sans_class1_limit=NULL, sans_class2_limit=6.0,
    equivalent_weight=62.00, ion_type='anion',
    method_detection_limit=0.1
WHERE indicator_code='NO3';

UPDATE dbo.WQ_Indicators SET
    risk_class='health', blue_drop_category='microbiological',
    sans_class1_limit=NULL, sans_class2_limit=0.0,
    method_detection_limit=1.0
WHERE indicator_code='TCOL';

UPDATE dbo.WQ_Indicators SET
    risk_class='health', blue_drop_category='microbiological',
    sans_class1_limit=NULL, sans_class2_limit=0.0,
    method_detection_limit=1.0
WHERE indicator_code='ECOLI';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='chemical_aesthetic',
    sans_class1_limit=NULL, sans_class2_limit=100.0,
    equivalent_weight=22.99, ion_type='cation'
WHERE indicator_code='NA';

UPDATE dbo.WQ_Indicators SET
    risk_class='aesthetic', blue_drop_category='physical',
    sans_class1_limit=NULL, sans_class2_limit=30.0
WHERE indicator_code='TEMP';

UPDATE dbo.WQ_Indicators SET
    risk_class='operational', blue_drop_category='physical',
    sans_class1_limit=5.0, sans_class2_limit=NULL,
    method_detection_limit=0.1
WHERE indicator_code='DO';
GO

-- ─── 28 new indicator records ─────────────────────────────────────────────────
-- SANS 241:2015 health + aesthetic + operational parameters
-- Heavy metals, radionuclides, disinfection by-products, ions for IBE
IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='NO2')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('NO2','Nitrite','mg/L',NULL,0.9,'SANS 241:2015',16,
    'health',NULL,0.9,0.005,23.00,'anion','chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='NH4')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('NH4','Ammonia (as NH4)','mg/L',NULL,1.5,'SANS 241:2015',17,
    'aesthetic',NULL,1.5,0.05,18.04,'cation','chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='SO4')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('SO4','Sulphate','mg/L',NULL,400.0,'SANS 241:2015',18,
    'aesthetic',NULL,400.0,0.5,48.03,'anion','chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='K')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('K','Potassium','mg/L',NULL,50.0,'SANS 241:2015',19,
    'aesthetic',NULL,50.0,0.5,39.10,'cation','chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='HCO3')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('HCO3','Bicarbonate','mg/L',NULL,NULL,'General chemistry',20,
    'operational',NULL,NULL,1.0,61.01,'anion',NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='CO3')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('CO3','Carbonate','mg/L',NULL,NULL,'General chemistry',21,
    'operational',NULL,NULL,1.0,30.00,'anion',NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='ALK')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('ALK','Total Alkalinity','mg/L as CaCO3',NULL,NULL,'General chemistry',22,
    'operational',NULL,NULL,1.0,NULL,NULL,NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='HARD')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('HARD','Total Hardness','mg/L as CaCO3',NULL,300.0,'SANS 241:2015',23,
    'aesthetic',NULL,300.0,1.0,NULL,NULL,'chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='FE')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('FE','Iron (total)','mg/L',NULL,0.3,'SANS 241:2015',24,
    'aesthetic',NULL,0.3,0.01,NULL,NULL,'chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='FE2')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('FE2','Ferrous Iron (Fe²⁺)','mg/L',NULL,NULL,'AMD monitoring',25,
    'operational',NULL,NULL,0.05,NULL,NULL,NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='FE3')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('FE3','Ferric Iron (Fe³⁺)','mg/L',NULL,NULL,'AMD monitoring',26,
    'operational',NULL,NULL,0.05,NULL,NULL,NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='MN')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('MN','Manganese','mg/L',NULL,0.1,'SANS 241:2015',27,
    'aesthetic',NULL,0.1,0.002,NULL,NULL,'chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='AS')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('AS','Arsenic','mg/L',NULL,0.01,'SANS 241:2015',28,
    'health',NULL,0.01,0.001,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='CD')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('CD','Cadmium','mg/L',NULL,0.003,'SANS 241:2015',29,
    'health',NULL,0.003,0.0001,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='CR')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('CR','Chromium (total)','mg/L',NULL,0.05,'SANS 241:2015',30,
    'health',NULL,0.05,0.005,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='CU')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('CU','Copper','mg/L',NULL,2.0,'SANS 241:2015',31,
    'health',NULL,2.0,0.01,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='PB')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('PB','Lead','mg/L',NULL,0.01,'SANS 241:2015',32,
    'health',NULL,0.01,0.001,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='HG')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('HG','Mercury','mg/L',NULL,0.006,'SANS 241:2015',33,
    'health',NULL,0.006,0.0001,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='CN')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('CN','Cyanide (free)','mg/L',NULL,0.07,'SANS 241:2015',34,
    'health',NULL,0.07,0.002,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='U238')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('U238','Uranium-238','µg/L',NULL,15.0,'SANS 241:2015',35,
    'health',NULL,15.0,0.1,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='BRO3')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('BRO3','Bromate','mg/L',NULL,0.01,'SANS 241:2015',36,
    'health',NULL,0.01,0.001,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='THM')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('THM','Total Trihalomethanes','mg/L',NULL,0.2,'SANS 241:2015',37,
    'health',NULL,0.2,0.005,NULL,NULL,'chemical_health');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='COLOR')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('COLOR','True Colour','TCU',NULL,15.0,'SANS 241:2015',38,
    'aesthetic',NULL,15.0,1.0,NULL,NULL,'chemical_aesthetic');

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='PHENOL')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,equivalent_weight,ion_type,blue_drop_category)
VALUES ('PHENOL','Phenols','mg/L',NULL,0.002,'SANS 241:2015',39,
    'aesthetic',NULL,0.002,0.0001,NULL,NULL,'chemical_aesthetic');

-- Eutrophication parameters (DWAF/DWS targets)
IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='TP')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,blue_drop_category)
VALUES ('TP','Total Phosphorus','µg/L',NULL,20.0,'DWAF Target 5.5.1',40,
    'operational',NULL,20.0,1.0,NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='CHLA')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,blue_drop_category)
VALUES ('CHLA','Chlorophyll-a','µg/L',NULL,10.0,'DWAF Target 5.5.1',41,
    'operational',NULL,10.0,0.5,NULL);

IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='SECCHI')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,blue_drop_category)
VALUES ('SECCHI','Secchi Depth','m',1.5,NULL,'DWAF Target 5.5.1',42,
    'operational',1.5,NULL,0.05,NULL);

-- AMD indicator
IF NOT EXISTS (SELECT 1 FROM dbo.WQ_Indicators WHERE indicator_code='TOTAL_ACID')
INSERT INTO dbo.WQ_Indicators (indicator_code,indicator_name,unit,lower_std,upper_std,std_reference,display_order,
    risk_class,sans_class1_limit,sans_class2_limit,method_detection_limit,blue_drop_category)
VALUES ('TOTAL_ACID','Total Acidity','mg/L as CaCO3',NULL,NULL,'AMD monitoring',43,
    'operational',NULL,NULL,1.0,NULL);
GO

-- ─── Back-fill existing measurements to Approved status ──────────────────────
UPDATE dbo.WQ_Measurements SET quality_flag = 'Approved'
WHERE quality_flag = 'Preliminary' AND is_censored = 0;
GO

-- ─── Back-fill season on existing readings (Southern Hemisphere) ──────────────
UPDATE dbo.WQ_Readings
SET season = CASE
    WHEN MONTH(reading_date) IN (10,11,12,1,2,3,4) THEN 'Wet'
    ELSE 'Dry'
END
WHERE season IS NULL;
GO

PRINT 'HydroCore Water Quality schema v2 applied successfully.';
GO
