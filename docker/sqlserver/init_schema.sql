-- =============================================================================
-- SISTEMA TRANSACCIONAL DE PRÉSTAMOS UNIVERSITARIOS
-- Archivo: init_schema.sql — Esquema réplica en SQL Server (T-SQL)
-- =============================================================================
-- Este esquema replica la estructura de PostgreSQL en SQL Server.
-- Es la copia de respaldo / réplica del sistema principal.
-- El servicio de sincronización (prestamos_sync) mantiene los datos actualizados.
-- =============================================================================

-- Crear la base de datos si no existe
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'prestamos_umb_copia')
BEGIN
    CREATE DATABASE prestamos_umb_copia
        COLLATE Latin1_General_100_CI_AS_SC_UTF8;
END
GO

USE prestamos_umb_copia;
GO

-- =============================================================================
-- SECCIÓN 1: TABLA DE ROLES
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'roles')
BEGIN
    CREATE TABLE roles (
        id              INT             IDENTITY(1,1) PRIMARY KEY,
        nombre          NVARCHAR(50)    NOT NULL UNIQUE
            CHECK (nombre IN ('administrador', 'cliente')),
        descripcion     NVARCHAR(MAX),
        fecha_creacion  DATETIME2       DEFAULT GETDATE()
    );
END
GO

-- =============================================================================
-- SECCIÓN 2: TABLA DE USUARIOS
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'usuarios')
BEGIN
    CREATE TABLE usuarios (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        nombre              NVARCHAR(100)   NOT NULL,
        apellido            NVARCHAR(100)   NOT NULL,
        correo              NVARCHAR(150)   NOT NULL UNIQUE,
        password_hash       NVARCHAR(255)   NOT NULL,
        rol_id              INT             NOT NULL REFERENCES roles(id),
        codigo_barras       NVARCHAR(100)   UNIQUE,   -- ESPACIO: lector código de barras
        numero_documento    NVARCHAR(50)    UNIQUE,
        activo              BIT             DEFAULT 1,
        fecha_creacion      DATETIME2       DEFAULT GETDATE(),
        fecha_actualizacion DATETIME2       DEFAULT GETDATE()
    );

    CREATE INDEX idx_usuarios_correo ON usuarios(correo);
    CREATE INDEX idx_usuarios_rol    ON usuarios(rol_id);
END
GO

-- =============================================================================
-- SECCIÓN 3: TABLA DE CATEGORÍAS
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'categorias')
BEGIN
    CREATE TABLE categorias (
        id          INT             IDENTITY(1,1) PRIMARY KEY,
        nombre      NVARCHAR(100)   NOT NULL UNIQUE,
        descripcion NVARCHAR(MAX),
        activo      BIT             DEFAULT 1,
        fecha_creacion DATETIME2    DEFAULT GETDATE()
    );
END
GO

-- =============================================================================
-- SECCIÓN 4: TABLA DE ARTÍCULOS
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'articulos')
BEGIN
    CREATE TABLE articulos (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        nombre              NVARCHAR(200)   NOT NULL,
        descripcion         NVARCHAR(MAX),
        categoria_id        INT             REFERENCES categorias(id),
        estado              NVARCHAR(20)    NOT NULL DEFAULT 'disponible'
            CHECK (estado IN ('disponible', 'prestado', 'mantenimiento', 'baja')),
        stock_total         INT             NOT NULL DEFAULT 1
            CHECK (stock_total >= 0),
        stock_disponible    INT             NOT NULL DEFAULT 1
            CHECK (stock_disponible >= 0),
        codigo_barras       NVARCHAR(100)   UNIQUE,  -- ESPACIO: lector código de barras
        codigo_interno      NVARCHAR(50)    UNIQUE,
        ubicacion           NVARCHAR(150),
        activo              BIT             DEFAULT 1,
        fecha_registro      DATETIME2       DEFAULT GETDATE(),
        fecha_actualizacion DATETIME2       DEFAULT GETDATE(),

        CONSTRAINT chk_stock_coherente CHECK (stock_disponible <= stock_total)
    );

    CREATE INDEX idx_articulos_estado    ON articulos(estado);
    CREATE INDEX idx_articulos_categoria ON articulos(categoria_id);
END
GO

-- =============================================================================
-- SECCIÓN 5: TABLA DE PRÉSTAMOS
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'prestamos')
BEGIN
    CREATE TABLE prestamos (
        id                          INT             IDENTITY(1,1) PRIMARY KEY,
        usuario_id                  INT             NOT NULL REFERENCES usuarios(id),
        articulo_id                 INT             NOT NULL REFERENCES articulos(id),
        administrador_autoriza_id   INT             REFERENCES usuarios(id),
        estado                      NVARCHAR(20)    NOT NULL DEFAULT 'activo'
            CHECK (estado IN ('activo', 'devuelto', 'vencido', 'cancelado')),
        fecha_prestamo              DATETIME2       NOT NULL DEFAULT GETDATE(),
        fecha_devolucion_esperada   DATETIME2       NOT NULL,
        fecha_devolucion_real       DATETIME2,
        observaciones               NVARCHAR(MAX),
        codigo_prestamo             NVARCHAR(50)    UNIQUE,

        CONSTRAINT chk_fecha_dev CHECK (fecha_devolucion_esperada > fecha_prestamo)
    );

    CREATE INDEX idx_prestamos_usuario  ON prestamos(usuario_id);
    CREATE INDEX idx_prestamos_articulo ON prestamos(articulo_id);
    CREATE INDEX idx_prestamos_estado   ON prestamos(estado);
    CREATE INDEX idx_prestamos_fecha    ON prestamos(fecha_prestamo);
END
GO

-- =============================================================================
-- SECCIÓN 6: TABLA DE DEVOLUCIONES
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'devoluciones')
BEGIN
    CREATE TABLE devoluciones (
        id                          INT             IDENTITY(1,1) PRIMARY KEY,
        prestamo_id                 INT             NOT NULL UNIQUE REFERENCES prestamos(id),
        administrador_recibe_id     INT             REFERENCES usuarios(id),
        estado_articulo_recibido    NVARCHAR(20)    NOT NULL
            CHECK (estado_articulo_recibido IN ('disponible', 'prestado', 'mantenimiento', 'baja')),
        fecha_devolucion            DATETIME2       NOT NULL DEFAULT GETDATE(),
        observaciones               NVARCHAR(MAX)
    );

    CREATE INDEX idx_devoluciones_prestamo ON devoluciones(prestamo_id);
END
GO

-- =============================================================================
-- SECCIÓN 7: TABLA DE HISTORIAL DE OPERACIONES (AUDITORÍA)
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'historial_operaciones')
BEGIN
    CREATE TABLE historial_operaciones (
        id              BIGINT          IDENTITY(1,1) PRIMARY KEY,
        tabla_afectada  NVARCHAR(50)    NOT NULL,
        operacion       NVARCHAR(20)    NOT NULL
            CHECK (operacion IN ('INSERT', 'UPDATE', 'DELETE')),
        registro_id     INT,
        usuario_db      NVARCHAR(100)   DEFAULT SYSTEM_USER,
        datos_anteriores NVARCHAR(MAX),  -- JSON como string
        datos_nuevos     NVARCHAR(MAX),  -- JSON como string
        ip_cliente       NVARCHAR(45),
        fecha           DATETIME2       DEFAULT GETDATE()
    );

    CREATE INDEX idx_historial_tabla  ON historial_operaciones(tabla_afectada);
    CREATE INDEX idx_historial_fecha  ON historial_operaciones(fecha);
END
GO

-- =============================================================================
-- SECCIÓN 8: TABLA DE CONTROL DE SINCRONIZACIÓN
-- Registra cada ejecución del servicio de sync para trazabilidad.
-- Esta tabla es exclusiva de SQL Server (no existe en PostgreSQL).
-- =============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sync_log')
BEGIN
    CREATE TABLE sync_log (
        id              BIGINT          IDENTITY(1,1) PRIMARY KEY,
        fecha_inicio    DATETIME2       NOT NULL DEFAULT GETDATE(),
        fecha_fin       DATETIME2,
        registros_sync  INT             DEFAULT 0,
        estado          NVARCHAR(20)    DEFAULT 'en_proceso'
            CHECK (estado IN ('en_proceso', 'completado', 'error')),
        mensaje         NVARCHAR(MAX)
    );
END
GO

-- =============================================================================
-- VISTAS DE REPLICA
-- Equivalentes simplificadas de las vistas de PostgreSQL.
-- =============================================================================

-- Vista: Stock disponible
CREATE OR ALTER VIEW v_stock_disponible AS
SELECT
    a.id            AS articulo_id,
    a.nombre        AS articulo,
    a.descripcion,
    c.nombre        AS categoria,
    a.estado,
    a.stock_total,
    a.stock_disponible,
    a.codigo_interno,
    a.codigo_barras,
    a.ubicacion,
    a.fecha_registro
FROM articulos a
LEFT JOIN categorias c ON c.id = a.categoria_id
WHERE a.activo = 1;
GO

-- Vista: Historial de préstamos
CREATE OR ALTER VIEW v_historial_prestamos AS
SELECT
    p.id                                        AS prestamo_id,
    p.codigo_prestamo,
    u.nombre + ' ' + u.apellido                AS usuario_nombre,
    u.correo,
    a.nombre                                    AS articulo,
    p.estado                                    AS estado_prestamo,
    p.fecha_prestamo,
    p.fecha_devolucion_esperada,
    p.fecha_devolucion_real,
    d.estado_articulo_recibido,
    adm.nombre + ' ' + adm.apellido            AS administrador_autorizo
FROM prestamos p
INNER JOIN usuarios u       ON u.id = p.usuario_id
INNER JOIN articulos a      ON a.id = p.articulo_id
LEFT  JOIN devoluciones d   ON d.prestamo_id = p.id
LEFT  JOIN usuarios adm     ON adm.id = p.administrador_autoriza_id;
GO

PRINT 'Esquema SQL Server creado exitosamente.';
GO
