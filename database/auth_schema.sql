-- ============================================================================
-- HydroCore Authentication Schema
-- Run this ONCE against the GroundwaterAnalysis database.
-- Compatible with SQL Server 2012 and later.
-- ============================================================================

USE GroundwaterAnalysis;
GO

-- ─── Users ───────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.Users', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Users (
        user_id                 INT             IDENTITY(1,1)   NOT NULL,
        username                NVARCHAR(50)    NOT NULL,
        email                   NVARCHAR(255)   NOT NULL,
        password_hash           NVARCHAR(255)   NOT NULL,
        role                    NVARCHAR(20)    NOT NULL        CONSTRAINT DF_Users_Role    DEFAULT 'viewer',
        is_active               BIT             NOT NULL        CONSTRAINT DF_Users_Active  DEFAULT 1,
        failed_login_attempts   INT             NOT NULL        CONSTRAINT DF_Users_Failed  DEFAULT 0,
        locked_until            DATETIME2       NULL,
        must_change_password    BIT             NOT NULL        CONSTRAINT DF_Users_MustCP  DEFAULT 0,
        created_at              DATETIME2       NOT NULL        CONSTRAINT DF_Users_Created DEFAULT GETDATE(),
        last_login              DATETIME2       NULL,
        created_by              INT             NULL,

        CONSTRAINT PK_Users             PRIMARY KEY (user_id),
        CONSTRAINT UQ_Users_Username    UNIQUE (username),
        CONSTRAINT UQ_Users_Email       UNIQUE (email),
        CONSTRAINT CK_Users_Role        CHECK (role IN ('admin', 'analyst', 'viewer'))
    );
    PRINT 'Created table: dbo.Users';
END
ELSE
    PRINT 'Table dbo.Users already exists — skipped.';
GO

-- Self-referencing FK added separately so the table exists first
IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_Users_CreatedBy' AND parent_object_id = OBJECT_ID('dbo.Users')
)
BEGIN
    ALTER TABLE dbo.Users
        ADD CONSTRAINT FK_Users_CreatedBy
            FOREIGN KEY (created_by) REFERENCES dbo.Users(user_id);
    PRINT 'Added FK: FK_Users_CreatedBy';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Users_Email'  AND object_id = OBJECT_ID('dbo.Users'))
    CREATE INDEX IX_Users_Email  ON dbo.Users (email);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Users_Active' AND object_id = OBJECT_ID('dbo.Users'))
    CREATE INDEX IX_Users_Active ON dbo.Users (is_active);
GO

-- ─── RefreshTokens ───────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.RefreshTokens', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.RefreshTokens (
        token_id    INT             IDENTITY(1,1)   NOT NULL,
        user_id     INT             NOT NULL,
        token_hash  NVARCHAR(64)    NOT NULL,
        expires_at  DATETIME2       NOT NULL,
        created_at  DATETIME2       NOT NULL    CONSTRAINT DF_RT_Created DEFAULT GETDATE(),
        revoked_at  DATETIME2       NULL,
        ip_address  NVARCHAR(45)    NULL,
        user_agent  NVARCHAR(500)   NULL,

        CONSTRAINT PK_RefreshTokens         PRIMARY KEY (token_id),
        CONSTRAINT UQ_RefreshTokens_Hash    UNIQUE (token_hash),
        CONSTRAINT FK_RefreshTokens_User    FOREIGN KEY (user_id)
                                                REFERENCES dbo.Users(user_id)
    );
    PRINT 'Created table: dbo.RefreshTokens';
END
ELSE
    PRINT 'Table dbo.RefreshTokens already exists — skipped.';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RefreshTokens_Hash'   AND object_id = OBJECT_ID('dbo.RefreshTokens'))
    CREATE INDEX IX_RefreshTokens_Hash   ON dbo.RefreshTokens (token_hash);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RefreshTokens_UserId' AND object_id = OBJECT_ID('dbo.RefreshTokens'))
    CREATE INDEX IX_RefreshTokens_UserId ON dbo.RefreshTokens (user_id);
GO

-- ─── AuditLog ────────────────────────────────────────────────────────────────
-- Note: column is named logged_at (not timestamp — reserved keyword in SQL Server)
IF OBJECT_ID('dbo.AuditLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AuditLog (
        log_id      BIGINT          IDENTITY(1,1)   NOT NULL,
        user_id     INT             NULL,
        action      NVARCHAR(100)   NOT NULL,
        resource    NVARCHAR(255)   NULL,
        details     NVARCHAR(1000)  NULL,
        ip_address  NVARCHAR(45)    NULL,
        user_agent  NVARCHAR(500)   NULL,
        logged_at   DATETIME2       NOT NULL    CONSTRAINT DF_AL_LoggedAt DEFAULT GETDATE(),
        success     BIT             NOT NULL    CONSTRAINT DF_AL_Success  DEFAULT 1,

        CONSTRAINT PK_AuditLog      PRIMARY KEY (log_id),
        CONSTRAINT FK_AuditLog_User FOREIGN KEY (user_id)
                                        REFERENCES dbo.Users(user_id)
    );
    PRINT 'Created table: dbo.AuditLog';
END
ELSE
    PRINT 'Table dbo.AuditLog already exists — skipped.';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AuditLog_UserId'   AND object_id = OBJECT_ID('dbo.AuditLog'))
    CREATE INDEX IX_AuditLog_UserId   ON dbo.AuditLog (user_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AuditLog_LoggedAt' AND object_id = OBJECT_ID('dbo.AuditLog'))
    CREATE INDEX IX_AuditLog_LoggedAt ON dbo.AuditLog (logged_at DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AuditLog_Action'   AND object_id = OBJECT_ID('dbo.AuditLog'))
    CREATE INDEX IX_AuditLog_Action   ON dbo.AuditLog (action);
GO

-- ─── Maintenance stored procedure ────────────────────────────────────────────
IF OBJECT_ID('dbo.sp_PurgeExpiredTokens', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_PurgeExpiredTokens;
GO

CREATE PROCEDURE dbo.sp_PurgeExpiredTokens
AS
BEGIN
    SET NOCOUNT ON;
    -- Remove refresh tokens expired more than 1 day ago
    DELETE FROM dbo.RefreshTokens
    WHERE expires_at < DATEADD(DAY, -1, GETDATE());

    -- Retain only 2 years of audit history
    DELETE FROM dbo.AuditLog
    WHERE logged_at < DATEADD(YEAR, -2, GETDATE());
END;
GO

-- ─── Organizations table (run once) ─────────────────────────────────────────
IF OBJECT_ID('dbo.Organizations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Organizations (
        org_id  INT             IDENTITY(1,1)   NOT NULL,
        name    NVARCHAR(100)   NOT NULL,
        [plan]  NVARCHAR(20)    NOT NULL        CONSTRAINT DF_Org_Plan DEFAULT 'pro',
        CONSTRAINT PK_Organizations PRIMARY KEY (org_id)
    );
    INSERT INTO dbo.Organizations (name, [plan]) VALUES ('Default', 'pro');
    PRINT 'Created table: dbo.Organizations';
END
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.Organizations)
        INSERT INTO dbo.Organizations (name, [plan]) VALUES ('Default', 'pro');
    PRINT 'Table dbo.Organizations already exists — skipped.';
END
GO

-- ─── org_id column migration on Users ────────────────────────────────────────
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'org_id'
)
BEGIN
    ALTER TABLE dbo.Users
        ADD org_id INT NOT NULL CONSTRAINT DF_Users_OrgId DEFAULT 1;
    PRINT 'Added column: dbo.Users.org_id';
END
ELSE
    PRINT 'Column dbo.Users.org_id already exists — skipped.';
GO

-- ─── Plan column migration (run once on existing databases) ─────────────────
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'plan'
)
BEGIN
    ALTER TABLE dbo.Users
        ADD [plan] NVARCHAR(20) NOT NULL
            CONSTRAINT DF_Users_Plan DEFAULT 'basic';
    PRINT 'Added column: dbo.Users.[plan]';
END
ELSE
    PRINT 'Column dbo.Users.[plan] already exists — skipped.';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_Users_Plan' AND parent_object_id = OBJECT_ID('dbo.Users')
)
BEGIN
    ALTER TABLE dbo.Users
        ADD CONSTRAINT CK_Users_Plan CHECK ([plan] IN ('basic', 'pro'));
    PRINT 'Added constraint: CK_Users_Plan';
END
GO

-- ─── Organizations table additions ───────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Organizations') AND name = 'is_active')
    ALTER TABLE dbo.Organizations ADD is_active BIT NOT NULL CONSTRAINT DF_Org_Active DEFAULT 1;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Organizations') AND name = 'contact_email')
    ALTER TABLE dbo.Organizations ADD contact_email NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Organizations') AND name = 'created_at')
    ALTER TABLE dbo.Organizations ADD created_at DATETIME2 NOT NULL CONSTRAINT DF_Org_Created DEFAULT GETDATE();
GO

-- ─── Users table — 2FA, setup, system-admin columns ─────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'totp_secret')
    ALTER TABLE dbo.Users ADD totp_secret NVARCHAR(64) NULL;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'totp_enabled')
    ALTER TABLE dbo.Users ADD totp_enabled BIT NOT NULL CONSTRAINT DF_Users_Totp DEFAULT 0;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'is_system_admin')
    ALTER TABLE dbo.Users ADD is_system_admin BIT NOT NULL CONSTRAINT DF_Users_SysAdmin DEFAULT 0;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'account_setup_token')
    ALTER TABLE dbo.Users ADD account_setup_token NVARCHAR(256) NULL;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'setup_token_expires')
    ALTER TABLE dbo.Users ADD setup_token_expires DATETIME2 NULL;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'setup_completed')
BEGIN
    -- Default 1 so pre-existing accounts are not locked out by the migration.
    -- New accounts created via the setup flow are explicitly set to 0 by the API.
    ALTER TABLE dbo.Users ADD setup_completed BIT NOT NULL CONSTRAINT DF_Users_Setup DEFAULT 1;
    PRINT 'Added column: dbo.Users.setup_completed';
END
ELSE
    PRINT 'Column dbo.Users.setup_completed already exists — skipped.';
GO

-- ─── Remediation: unlock pre-existing accounts ───────────────────────────────
-- If the column was previously added with DEFAULT 0, existing users were locked
-- out. This sets them back to active.  New accounts (setup_completed = 0 AND
-- account_setup_token IS NOT NULL) are left untouched so they still go through
-- the welcome-email setup flow.
UPDATE dbo.Users
SET    setup_completed = 1
WHERE  setup_completed = 0
  AND  account_setup_token IS NULL
  AND  is_system_admin    = 0;
PRINT 'Remediated pre-existing user accounts (setup_completed set to 1 where applicable).';
GO

-- ─── Done ─────────────────────────────────────────────────────────────────────
-- Next step: create the first system admin via the API:
--
--   POST http://localhost:5000/api/admin/setup
--   Body: { "username": "sysadmin", "email": "you@domain.com" }
--   (A setup link is emailed; configure SMTP env vars or use the returned token)
--
-- Or create the first tenant admin account via the API:
--   POST http://localhost:5000/api/auth/setup
--   Body: { "username": "admin", "email": "you@domain.com", "password": "YourStr0ng!Pass1" }
-- ─────────────────────────────────────────────────────────────────────────────

PRINT 'HydroCore auth schema applied successfully.';
GO
