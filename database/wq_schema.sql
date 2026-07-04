-- ============================================================================
-- HydroCore — Water Quality Module Schema
-- Run once against the GroundwaterAnalysis database.
-- All guards are safe to re-run (IF NOT EXISTS throughout).
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- ─── Sampling Stations ───────────────────────────────────────────────────────
IF OBJECT_ID('dbo.WQ_Stations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Stations (
        station_id    INT           IDENTITY(1,1) NOT NULL,
        station_code  NVARCHAR(20)  NOT NULL,
        station_name  NVARCHAR(150) NOT NULL,
        description   NVARCHAR(500) NULL,
        latitude      DECIMAL(10,7) NULL  CONSTRAINT CK_WQSt_Lat CHECK (latitude  BETWEEN -90  AND 90),
        longitude     DECIMAL(10,7) NULL  CONSTRAINT CK_WQSt_Lon CHECK (longitude BETWEEN -180 AND 180),
        org_id        INT           NOT NULL CONSTRAINT DF_WQSt_Org     DEFAULT 1,
        is_active     BIT           NOT NULL CONSTRAINT DF_WQSt_Active  DEFAULT 1,
        created_at    DATETIME2     NOT NULL CONSTRAINT DF_WQSt_Created DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Stations     PRIMARY KEY (station_id),
        CONSTRAINT UQ_WQSt_CodeOrg    UNIQUE (station_code, org_id)
    );
    CREATE INDEX IX_WQSt_Org    ON dbo.WQ_Stations(org_id);
    CREATE INDEX IX_WQSt_Active ON dbo.WQ_Stations(is_active);
    PRINT 'Created table: dbo.WQ_Stations';
END
ELSE
    PRINT 'Table dbo.WQ_Stations already exists — skipped.';
GO

-- ─── Quality Indicators (parameters + built-in guideline standards) ──────────
IF OBJECT_ID('dbo.WQ_Indicators', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Indicators (
        indicator_id   INT           IDENTITY(1,1) NOT NULL,
        indicator_code NVARCHAR(30)  NOT NULL,
        indicator_name NVARCHAR(100) NOT NULL,
        unit           NVARCHAR(30)  NULL,
        lower_std      FLOAT         NULL,   -- value < lower_std → non-compliant
        upper_std      FLOAT         NULL,   -- value > upper_std → non-compliant
        std_reference  NVARCHAR(200) NULL,
        display_order  INT           NOT NULL CONSTRAINT DF_WQInd_Order DEFAULT 99,
        CONSTRAINT PK_WQ_Indicators  PRIMARY KEY (indicator_id),
        CONSTRAINT UQ_WQInd_Code     UNIQUE (indicator_code)
    );

    -- 15 indicators — super-set of what the standard covers
    INSERT INTO dbo.WQ_Indicators
        (indicator_code, indicator_name, unit, lower_std, upper_std, std_reference, display_order)
    VALUES
        ('PH',    'pH',                        NULL,          6.0,   9.0,    'SANS 241:2015',  1),
        ('EC',    'Electrical Conductivity',    'mS/m',        NULL,  70.0,   'SANS 241:2015',  2),
        ('SS',    'Suspended Solids',           'mg/L',        NULL,  10.0,   'SANS 241:2015',  3),
        ('TDS',   'Total Dissolved Solids',     'mg/L',        NULL,  1000.0, 'SANS 241:2015',  4),
        ('TURB',  'Turbidity',                  'NTU',         NULL,  5.0,    'SANS 241:2015',  5),
        ('CL',    'Chloride',                   'mg/L',        NULL,  100.0,  'SANS 241:2015',  6),
        ('FL',    'Fluoride',                   'mg/L',        NULL,  1.0,    'SANS 241:2015',  7),
        ('CA',    'Calcium',                    'mg/L',        NULL,  200.0,  'SANS 241:2015',  8),
        ('MG',    'Magnesium',                  'mg/L',        NULL,  100.0,  'SANS 241:2015',  9),
        ('NO3',   'Nitrate',                    'mg/L',        NULL,  6.0,    'SANS 241:2015', 10),
        ('TCOL',  'Total Coliform',             'CFU/100mL',   NULL,  0.0,    'SANS 241:2015', 11),
        ('ECOLI', 'E. coli',                    'CFU/100mL',   NULL,  0.0,    'SANS 241:2015', 12),
        ('NA',    'Sodium',                     'mg/L',        NULL,  100.0,  'SANS 241:2015', 13),
        ('TEMP',  'Water Temperature',          '°C',          NULL,  30.0,   'SANS 241:2015', 14),
        ('DO',    'Dissolved Oxygen',           'mg/L',        5.0,   NULL,   'SANS 241:2015', 15);

    PRINT 'Created and seeded table: dbo.WQ_Indicators';
END
ELSE
    PRINT 'Table dbo.WQ_Indicators already exists — skipped.';
GO

-- ─── Reading Events (one row per station × date sampling event) ──────────────
IF OBJECT_ID('dbo.WQ_Readings', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Readings (
        reading_id   INT          IDENTITY(1,1) NOT NULL,
        station_id   INT          NOT NULL,
        reading_date DATE         NOT NULL,
        source_file  NVARCHAR(255) NULL,
        uploaded_by  INT          NULL,
        org_id       INT          NOT NULL CONSTRAINT DF_WQR_Org DEFAULT 1,
        created_at   DATETIME2    NOT NULL CONSTRAINT DF_WQR_Created DEFAULT GETDATE(),
        CONSTRAINT PK_WQ_Readings        PRIMARY KEY (reading_id),
        CONSTRAINT FK_WQR_Station        FOREIGN KEY (station_id)  REFERENCES dbo.WQ_Stations(station_id),
        CONSTRAINT FK_WQR_User           FOREIGN KEY (uploaded_by) REFERENCES dbo.Users(user_id),
        CONSTRAINT UQ_WQR_StationDate    UNIQUE (station_id, reading_date)
    );
    CREATE INDEX IX_WQR_Station ON dbo.WQ_Readings(station_id);
    CREATE INDEX IX_WQR_Date    ON dbo.WQ_Readings(reading_date DESC);
    CREATE INDEX IX_WQR_Org     ON dbo.WQ_Readings(org_id);
    PRINT 'Created table: dbo.WQ_Readings';
END
ELSE
    PRINT 'Table dbo.WQ_Readings already exists — skipped.';
GO

-- ─── Measurements (one row per reading × indicator) ──────────────────────────
IF OBJECT_ID('dbo.WQ_Measurements', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WQ_Measurements (
        meas_id      INT          IDENTITY(1,1) NOT NULL,
        reading_id   INT          NOT NULL,
        indicator_id INT          NOT NULL,
        measured_val FLOAT        NULL,
        is_compliant BIT          NULL,     -- NULL when no standard applies
        flag         NVARCHAR(10) NULL,     -- 'ABOVE' | 'BELOW' | NULL
        CONSTRAINT PK_WQ_Measurements        PRIMARY KEY (meas_id),
        CONSTRAINT FK_WQM_Reading            FOREIGN KEY (reading_id)   REFERENCES dbo.WQ_Readings(reading_id)   ON DELETE CASCADE,
        CONSTRAINT FK_WQM_Indicator          FOREIGN KEY (indicator_id) REFERENCES dbo.WQ_Indicators(indicator_id),
        CONSTRAINT UQ_WQM_ReadingIndicator   UNIQUE (reading_id, indicator_id)
    );
    CREATE INDEX IX_WQM_Reading   ON dbo.WQ_Measurements(reading_id);
    CREATE INDEX IX_WQM_Indicator ON dbo.WQ_Measurements(indicator_id);
    PRINT 'Created table: dbo.WQ_Measurements';
END
ELSE
    PRINT 'Table dbo.WQ_Measurements already exists — skipped.';
GO

PRINT 'HydroCore Water Quality schema applied successfully.';
GO
