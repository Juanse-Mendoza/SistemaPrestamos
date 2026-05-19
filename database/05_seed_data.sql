-- =============================================================================
-- SISTEMA TRANSACCIONAL DE PRÉSTAMOS UNIVERSITARIOS
-- Archivo: 05_seed_data.sql — Datos iniciales del sistema
-- =============================================================================
-- Este archivo inserta los datos mínimos para que el sistema arranque:
-- roles, usuario administrador por defecto, categorías y artículos de ejemplo.
-- IMPORTANTE: Cambiar la contraseña del administrador en producción.
-- =============================================================================

\connect prestamos_umb

-- =============================================================================
-- SECCIÓN 1: ROLES DEL SISTEMA
-- Dos roles: administrador (control total) y cliente (consulta y préstamos).
-- =============================================================================

INSERT INTO roles (nombre, descripcion) VALUES
    ('administrador', 'Acceso completo: gestión de usuarios, artículos, préstamos y reportes'),
    ('cliente',       'Acceso limitado: visualización de stock e historial de préstamos propios')
ON CONFLICT (nombre) DO NOTHING;

-- =============================================================================
-- SECCIÓN 2: USUARIO ADMINISTRADOR POR DEFECTO
-- Contraseña: Admin2026! (hasheada con bcrypt, cost=12)
-- Este hash fue generado con: bcrypt.hashpw(b'Admin2026!', bcrypt.gensalt(12))
-- CAMBIAR EN PRODUCCIÓN.
-- =============================================================================

INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol_id, numero_documento)
SELECT
    'Administrador',
    'Sistema',
    'admin@umb.edu.co',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMqJqhS2GpHEYxQ6VQrz7v2Gca',
    r.id,
    '000000000'
FROM roles r
WHERE r.nombre = 'administrador'
ON CONFLICT (correo) DO NOTHING;

-- =============================================================================
-- SECCIÓN 3: CATEGORÍAS DE ARTÍCULOS
-- Tipos de insumos universitarios frecuentes.
-- =============================================================================

INSERT INTO categorias (nombre, descripcion) VALUES
    ('Equipos de Cómputo',      'Computadores portátiles, tabletas y periféricos'),
    ('Laboratorio',             'Equipos y herramientas de laboratorio científico'),
    ('Audiovisual',             'Proyectores, cámaras, micrófonos y equipos de video'),
    ('Herramientas',            'Herramientas manuales y eléctricas para talleres'),
    ('Material Didáctico',      'Libros, kits educativos y material de apoyo académico'),
    ('Redes y Comunicaciones',  'Routers, switches, cables y equipos de redes')
ON CONFLICT (nombre) DO NOTHING;

-- =============================================================================
-- SECCIÓN 4: ARTÍCULOS DE EJEMPLO
-- Inventario inicial de demostración para la entrega del sistema.
-- Captura de pantalla sugerida: tabla de artículos en la interfaz del cliente
-- y en el módulo de inventario del administrador.
-- =============================================================================

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Computador Portátil Dell Latitude 5420',
    'Intel Core i5 11va gen, 8GB RAM, 256GB SSD, Windows 11 Pro',
    c.id, 5, 5, 'EQ-COM-001', 'Sala de Préstamos - Estante A1'
FROM categorias c WHERE c.nombre = 'Equipos de Cómputo'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Computador Portátil HP ProBook 440',
    'AMD Ryzen 5, 8GB RAM, 512GB SSD, Windows 11',
    c.id, 3, 3, 'EQ-COM-002', 'Sala de Préstamos - Estante A1'
FROM categorias c WHERE c.nombre = 'Equipos de Cómputo'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Tableta Gráfica Wacom Intuos',
    'Tableta gráfica profesional para diseño digital, 8.5" x 5.3"',
    c.id, 2, 2, 'EQ-COM-003', 'Sala de Préstamos - Estante A2'
FROM categorias c WHERE c.nombre = 'Equipos de Cómputo'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Proyector Epson PowerLite W52+',
    'Proyector WXGA 4000 lúmenes, conexión HDMI y VGA',
    c.id, 4, 4, 'AV-PRY-001', 'Sala de Préstamos - Estante B1'
FROM categorias c WHERE c.nombre = 'Audiovisual'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Cámara de Video Sony HDR-CX405',
    'Cámara de video Full HD, zoom óptico 30x, entrada para micrófono',
    c.id, 2, 2, 'AV-CAM-001', 'Sala de Préstamos - Estante B2'
FROM categorias c WHERE c.nombre = 'Audiovisual'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Osciloscopio Digital Rigol DS1054Z',
    'Osciloscopio digital 4 canales, 50MHz, pantalla LCD 7"',
    c.id, 3, 3, 'LAB-OSC-001', 'Laboratorio Electrónica - Armario 1'
FROM categorias c WHERE c.nombre = 'Laboratorio'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Kit Arduino Mega',
    'Kit completo con Arduino Mega 2560, sensores, LEDs, protoboard y cables',
    c.id, 10, 10, 'LAB-ARD-001', 'Laboratorio Electrónica - Armario 2'
FROM categorias c WHERE c.nombre = 'Laboratorio'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Kit Raspberry Pi 4 (4GB)',
    'Raspberry Pi 4B 4GB, fuente de alimentación, carcasa y tarjeta SD 32GB',
    c.id, 5, 5, 'LAB-RAS-001', 'Laboratorio Electrónica - Armario 2'
FROM categorias c WHERE c.nombre = 'Laboratorio'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Switch Cisco Catalyst 2960',
    'Switch administrable 24 puertos Fast Ethernet, 2 puertos Gigabit SFP',
    c.id, 2, 2, 'RED-SWT-001', 'Laboratorio de Redes - Rack 1'
FROM categorias c WHERE c.nombre = 'Redes y Comunicaciones'
ON CONFLICT (codigo_interno) DO NOTHING;

INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible, codigo_interno, ubicacion)
SELECT
    'Cable de Red UTP Cat6 (10m)',
    'Cable de red categoría 6, 10 metros, conectores RJ45 ya instalados',
    c.id, 20, 20, 'RED-CAB-001', 'Laboratorio de Redes - Cajón 1'
FROM categorias c WHERE c.nombre = 'Redes y Comunicaciones'
ON CONFLICT (codigo_interno) DO NOTHING;

-- =============================================================================
-- VERIFICACIÓN FINAL
-- Muestra un resumen de lo que se insertó para confirmar la carga.
-- =============================================================================

SELECT 'ROLES' AS tabla, COUNT(*) AS registros FROM roles
UNION ALL
SELECT 'USUARIOS', COUNT(*) FROM usuarios
UNION ALL
SELECT 'CATEGORÍAS', COUNT(*) FROM categorias
UNION ALL
SELECT 'ARTÍCULOS', COUNT(*) FROM articulos;
