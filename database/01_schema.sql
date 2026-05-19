-- =============================================================================
-- SISTEMA TRANSACCIONAL DE PRÉSTAMOS UNIVERSITARIOS
-- Universidad Manuela Beltrán - Ingeniería de Software
-- Autores: Juan S. Mendoza, Hemer S. Pérez, Brayan Turmequé
-- Base de datos: PostgreSQL
-- Archivo: 01_schema.sql — Esquema principal
-- =============================================================================

-- Eliminar y recrear la base de datos limpia
\connect postgres
DROP DATABASE IF EXISTS prestamos_umb;
CREATE DATABASE prestamos_umb
    WITH ENCODING = 'UTF8'
    LC_COLLATE = 'es_CO.UTF-8'
    LC_CTYPE = 'es_CO.UTF-8'
    TEMPLATE = template0;

\connect prestamos_umb

-- Habilitar extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- SECCIÓN 1: TIPOS ENUMERADOS
-- Aquí se definen los estados posibles para artículos y préstamos.
-- El sistema valida automáticamente que solo se usen estos valores.
-- =============================================================================

CREATE TYPE estado_articulo AS ENUM (
    'disponible',
    'prestado',
    'mantenimiento',
    'baja'
);

CREATE TYPE estado_prestamo AS ENUM (
    'pendiente',
    'activo',
    'devuelto',
    'vencido',
    'cancelado',
    'rechazado'
);

CREATE TYPE tipo_rol AS ENUM (
    'administrador',
    'cliente'
);

-- =============================================================================
-- SECCIÓN 2: TABLA DE ROLES
-- Define los perfiles de acceso al sistema.
-- El administrador tiene control total; el cliente tiene acceso limitado.
-- =============================================================================

CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    nombre      tipo_rol    NOT NULL UNIQUE,
    descripcion TEXT,
    fecha_creacion TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE roles IS 'Perfiles de acceso: administrador y cliente';

-- =============================================================================
-- SECCIÓN 3: TABLA DE USUARIOS
-- Almacena tanto administradores como clientes/estudiantes.
-- La columna codigo_barras se reserva para integración futura con lector.
-- =============================================================================

CREATE TABLE usuarios (
    id                  SERIAL PRIMARY KEY,
    nombre              VARCHAR(100) NOT NULL,
    apellido            VARCHAR(100) NOT NULL,
    correo              VARCHAR(150) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    rol_id              INTEGER      NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    codigo_barras       VARCHAR(100) UNIQUE,          -- ESPACIO: lector de código de barras
    numero_documento    VARCHAR(50)  UNIQUE,          -- Cédula o carnet universitario
    activo              BOOLEAN      DEFAULT TRUE,
    fecha_creacion      TIMESTAMP    DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP    DEFAULT NOW()
);

COMMENT ON TABLE usuarios IS 'Usuarios del sistema: administradores y clientes/estudiantes';
COMMENT ON COLUMN usuarios.codigo_barras IS 'Reservado para futura integración con lector de código de barras';
COMMENT ON COLUMN usuarios.numero_documento IS 'Cédula o carnet universitario del estudiante';

CREATE INDEX idx_usuarios_correo ON usuarios(correo);
CREATE INDEX idx_usuarios_rol ON usuarios(rol_id);
CREATE INDEX idx_usuarios_codigo_barras ON usuarios(codigo_barras) WHERE codigo_barras IS NOT NULL;

-- =============================================================================
-- SECCIÓN 4: TABLA DE CATEGORÍAS DE ARTÍCULOS
-- Permite agrupar artículos por tipo (equipos de cómputo, laboratorio, etc.)
-- =============================================================================

CREATE TABLE categorias (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    activo      BOOLEAN      DEFAULT TRUE,
    fecha_creacion TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE categorias IS 'Categorías para clasificar los artículos del inventario';

-- =============================================================================
-- SECCIÓN 5: TABLA DE ARTÍCULOS
-- Inventario de todos los insumos y artículos prestables.
-- stock_total: cantidad física registrada
-- stock_disponible: cantidad actualmente disponible para préstamo
-- codigo_barras se reserva para integración futura con lector.
-- =============================================================================

CREATE TABLE articulos (
    id                  SERIAL PRIMARY KEY,
    nombre              VARCHAR(200)    NOT NULL,
    descripcion         TEXT,
    categoria_id        INTEGER         REFERENCES categorias(id) ON DELETE SET NULL,
    estado              estado_articulo NOT NULL DEFAULT 'disponible',
    stock_total         INTEGER         NOT NULL DEFAULT 1 CHECK (stock_total >= 0),
    stock_disponible    INTEGER         NOT NULL DEFAULT 1 CHECK (stock_disponible >= 0),
    codigo_barras       VARCHAR(100)    UNIQUE,       -- ESPACIO: lector de código de barras
    codigo_interno      VARCHAR(50)     UNIQUE,       -- Código institucional del artículo
    ubicacion           VARCHAR(150),                 -- Ej: "Sala B, Estante 3"
    tiempo_maximo_minutos INTEGER       CHECK (tiempo_maximo_minutos IS NULL OR tiempo_maximo_minutos > 0),
    activo              BOOLEAN         DEFAULT TRUE,
    fecha_registro      TIMESTAMP       DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP       DEFAULT NOW(),

    CONSTRAINT chk_stock_coherente CHECK (stock_disponible <= stock_total)
);

COMMENT ON TABLE articulos IS 'Inventario de artículos e insumos universitarios prestables';
COMMENT ON COLUMN articulos.codigo_barras IS 'Reservado para futura integración con lector de código de barras';
COMMENT ON COLUMN articulos.stock_disponible IS 'Calculado automáticamente por triggers al registrar préstamos y devoluciones';

CREATE INDEX idx_articulos_estado ON articulos(estado);
CREATE INDEX idx_articulos_categoria ON articulos(categoria_id);
CREATE INDEX idx_articulos_codigo_barras ON articulos(codigo_barras) WHERE codigo_barras IS NOT NULL;

-- =============================================================================
-- SECCIÓN 6: TABLA DE PRÉSTAMOS
-- Registro central de cada préstamo generado en el sistema.
-- Cada fila representa un préstamo de un artículo a un usuario.
-- codigo_prestamo: generado automáticamente, espacio para código de barras del comprobante.
-- =============================================================================

CREATE TABLE prestamos (
    id                          SERIAL          PRIMARY KEY,
    usuario_id                  INTEGER         NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    articulo_id                 INTEGER         NOT NULL REFERENCES articulos(id) ON DELETE RESTRICT,
    administrador_autoriza_id   INTEGER         REFERENCES usuarios(id) ON DELETE SET NULL,
    estado                      estado_prestamo NOT NULL DEFAULT 'activo',
    fecha_prestamo              TIMESTAMP       NOT NULL DEFAULT NOW(),
    fecha_devolucion_esperada   TIMESTAMP       NOT NULL,
    fecha_devolucion_real       TIMESTAMP,
    observaciones               TEXT,
    codigo_prestamo             VARCHAR(50)     UNIQUE DEFAULT ('PRE-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || LPAD(NEXTVAL('prestamos_id_seq')::TEXT, 6, '0')),
    codigo_solicitud            VARCHAR(50),

    CONSTRAINT chk_fecha_devolucion CHECK (fecha_devolucion_esperada > fecha_prestamo)
);

COMMENT ON TABLE prestamos IS 'Registro de cada préstamo: quién tomó qué artículo y cuándo debe devolverlo';
COMMENT ON COLUMN prestamos.codigo_prestamo IS 'Código único del préstamo, compatible con futura impresión de código de barras';
COMMENT ON COLUMN prestamos.administrador_autoriza_id IS 'Administrador que autorizó el préstamo (NULL si el sistema lo generó automáticamente)';

CREATE INDEX idx_prestamos_usuario ON prestamos(usuario_id);
CREATE INDEX idx_prestamos_articulo ON prestamos(articulo_id);
CREATE INDEX idx_prestamos_estado ON prestamos(estado);
CREATE INDEX idx_prestamos_fecha ON prestamos(fecha_prestamo);

-- =============================================================================
-- SECCIÓN 7: TABLA DE DEVOLUCIONES
-- Registra el acto físico de devolución y el estado en que regresa el artículo.
-- Al insertar aquí, los triggers actualizan automáticamente el préstamo y el stock.
-- =============================================================================

CREATE TABLE devoluciones (
    id                          SERIAL          PRIMARY KEY,
    prestamo_id                 INTEGER         NOT NULL UNIQUE REFERENCES prestamos(id) ON DELETE RESTRICT,
    administrador_recibe_id     INTEGER         REFERENCES usuarios(id) ON DELETE SET NULL,
    estado_articulo_recibido    estado_articulo NOT NULL,
    fecha_devolucion            TIMESTAMP       NOT NULL DEFAULT NOW(),
    observaciones               TEXT,
    confirmada_estudiante       BOOLEAN         DEFAULT NULL,
    fecha_confirmacion          TIMESTAMP,
    motivo_rechazo              TEXT
);

COMMENT ON TABLE devoluciones IS 'Registro de cada devolución con el estado físico en que fue recibido el artículo';

CREATE INDEX idx_devoluciones_prestamo ON devoluciones(prestamo_id);

-- =============================================================================
-- SECCIÓN 8: TABLA DE HISTORIAL DE OPERACIONES (AUDITORÍA)
-- Registro inmutable de todas las acciones críticas del sistema.
-- Permite trazabilidad completa para auditoría académica e institucional.
-- =============================================================================

CREATE TABLE historial_operaciones (
    id              BIGSERIAL   PRIMARY KEY,
    tabla_afectada  VARCHAR(50) NOT NULL,
    operacion       VARCHAR(20) NOT NULL CHECK (operacion IN ('INSERT', 'UPDATE', 'DELETE')),
    registro_id     INTEGER,
    usuario_db      VARCHAR(100) DEFAULT CURRENT_USER,
    datos_anteriores JSONB,
    datos_nuevos     JSONB,
    ip_cliente       INET,
    fecha           TIMESTAMP   DEFAULT NOW()
);

COMMENT ON TABLE historial_operaciones IS 'Auditoría inmutable: registra cada INSERT, UPDATE o DELETE en tablas críticas';

CREATE INDEX idx_historial_tabla ON historial_operaciones(tabla_afectada);
CREATE INDEX idx_historial_fecha ON historial_operaciones(fecha);
CREATE INDEX idx_historial_registro ON historial_operaciones(registro_id);

-- =============================================================================
-- SECCIÓN 9: ROLES DE BASE DE DATOS
-- Controla el acceso a nivel de motor de base de datos.
-- Capa adicional de seguridad independiente del JWT de la aplicación.
-- =============================================================================

-- Rol administrador: acceso completo a todas las tablas
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_administrador') THEN
        CREATE ROLE rol_administrador;
    END IF;
END$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rol_administrador;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rol_administrador;

-- Rol cliente: solo puede leer artículos y sus propios préstamos
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_cliente') THEN
        CREATE ROLE rol_cliente;
    END IF;
END$$;

GRANT SELECT ON articulos TO rol_cliente;
GRANT SELECT ON categorias TO rol_cliente;
GRANT SELECT ON prestamos TO rol_cliente;
GRANT SELECT ON devoluciones TO rol_cliente;

-- Usuario de la aplicación (la app Python se conecta con este usuario)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_prestamos') THEN
        CREATE USER app_prestamos WITH PASSWORD 'App_Prestamos_2026!';
    END IF;
END$$;

GRANT rol_administrador TO app_prestamos;
