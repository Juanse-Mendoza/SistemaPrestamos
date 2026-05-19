-- =============================================================================
-- SISTEMA TRANSACCIONAL DE PRÉSTAMOS UNIVERSITARIOS
-- Archivo: 04_views.sql — Vistas para reportes y consultas frecuentes
-- =============================================================================
-- Las vistas simplifican las consultas complejas que la aplicación necesita
-- ejecutar con frecuencia, evitando joins repetitivos en el código Python.
-- =============================================================================

\connect prestamos_umb

-- =============================================================================
-- VISTA 1: Stock de artículos disponibles
-- Usada por la interfaz del CLIENTE para ver qué hay disponible.
-- Captura de pantalla sugerida: tabla principal en la ventana del cliente.
-- =============================================================================

CREATE OR REPLACE VIEW v_stock_disponible AS
SELECT
    a.id                    AS articulo_id,
    a.nombre                AS articulo,
    a.descripcion,
    c.nombre                AS categoria,
    a.estado,
    a.stock_total,
    a.stock_disponible,
    a.codigo_interno,
    a.codigo_barras,        -- ESPACIO: futura integración con lector
    a.ubicacion,
    a.fecha_registro
FROM articulos a
LEFT JOIN categorias c ON c.id = a.categoria_id
WHERE a.activo = TRUE
ORDER BY a.nombre;

COMMENT ON VIEW v_stock_disponible IS 'Inventario completo con stock actual. Usada en la pantalla principal del cliente.';

-- =============================================================================
-- VISTA 2: Préstamos activos con información completa
-- Usada por el ADMINISTRADOR para ver qué está prestado en este momento.
-- Captura de pantalla sugerida: panel de préstamos activos en admin.
-- =============================================================================

CREATE OR REPLACE VIEW v_prestamos_activos AS
SELECT
    p.id                        AS prestamo_id,
    p.codigo_prestamo,
    u.nombre || ' ' || u.apellido   AS usuario_nombre,
    u.correo                    AS usuario_correo,
    u.numero_documento,
    a.nombre                    AS articulo,
    a.codigo_interno,
    p.fecha_prestamo,
    p.fecha_devolucion_esperada,
    CASE
        WHEN p.fecha_devolucion_esperada < NOW() THEN 'VENCIDO'
        ELSE 'A TIEMPO'
    END                         AS estado_tiempo,
    EXTRACT(DAY FROM NOW() - p.fecha_prestamo) AS dias_prestado,
    p.observaciones
FROM prestamos p
INNER JOIN usuarios u ON u.id = p.usuario_id
INNER JOIN articulos a ON a.id = p.articulo_id
WHERE p.estado = 'activo'
ORDER BY p.fecha_devolucion_esperada ASC;

COMMENT ON VIEW v_prestamos_activos IS 'Préstamos actualmente en curso. Panel principal del administrador.';

-- =============================================================================
-- VISTA 3: Historial completo de préstamos
-- Para reportes del administrador con todos los préstamos (activos, devueltos,
-- vencidos). Incluye información del artículo y el usuario.
-- Captura de pantalla sugerida: sección de reportes / historial en admin.
-- =============================================================================

CREATE OR REPLACE VIEW v_historial_prestamos AS
SELECT
    p.id                            AS prestamo_id,
    p.codigo_prestamo,
    u.nombre || ' ' || u.apellido   AS usuario_nombre,
    u.correo                        AS usuario_correo,
    u.numero_documento,
    a.nombre                        AS articulo,
    c.nombre                        AS categoria,
    p.estado                        AS estado_prestamo,
    p.fecha_prestamo,
    p.fecha_devolucion_esperada,
    p.fecha_devolucion_real,
    CASE
        WHEN p.fecha_devolucion_real IS NOT NULL
        THEN EXTRACT(DAY FROM p.fecha_devolucion_real - p.fecha_prestamo)::INTEGER
        ELSE EXTRACT(DAY FROM NOW() - p.fecha_prestamo)::INTEGER
    END                             AS dias_total,
    CASE
        WHEN p.fecha_devolucion_real > p.fecha_devolucion_esperada THEN 'DEVUELTO TARDE'
        WHEN p.estado = 'vencido' THEN 'VENCIDO'
        WHEN p.estado = 'devuelto' THEN 'A TIEMPO'
        ELSE 'EN CURSO'
    END                             AS cumplimiento,
    d.estado_articulo_recibido,
    d.observaciones                 AS obs_devolucion,
    admin_auth.nombre || ' ' || admin_auth.apellido AS administrador_autorizo,
    admin_rec.nombre  || ' ' || admin_rec.apellido  AS administrador_recibio,
    p.observaciones                 AS obs_prestamo
FROM prestamos p
INNER JOIN usuarios u     ON u.id = p.usuario_id
INNER JOIN articulos a    ON a.id = p.articulo_id
LEFT  JOIN categorias c   ON c.id = a.categoria_id
LEFT  JOIN devoluciones d ON d.prestamo_id = p.id
LEFT  JOIN usuarios admin_auth ON admin_auth.id = p.administrador_autoriza_id
LEFT  JOIN usuarios admin_rec  ON admin_rec.id  = d.administrador_recibe_id
ORDER BY p.fecha_prestamo DESC;

COMMENT ON VIEW v_historial_prestamos IS 'Historial completo de préstamos con todos los detalles. Pantalla de reportes del admin.';

-- =============================================================================
-- VISTA 4: Préstamos por usuario (para el historial del cliente)
-- El cliente ve sus propios préstamos. La app filtra por usuario_id del JWT.
-- Captura de pantalla sugerida: sección "Mis préstamos" en la vista del cliente.
-- =============================================================================

CREATE OR REPLACE VIEW v_mis_prestamos AS
SELECT
    p.id                        AS prestamo_id,
    p.codigo_prestamo,
    a.nombre                    AS articulo,
    a.descripcion               AS descripcion_articulo,
    c.nombre                    AS categoria,
    a.ubicacion,
    p.estado,
    p.fecha_prestamo,
    p.fecha_devolucion_esperada,
    p.fecha_devolucion_real,
    CASE
        WHEN p.estado = 'activo' AND p.fecha_devolucion_esperada < NOW() THEN 'VENCIDO'
        WHEN p.estado = 'activo' THEN 'ACTIVO'
        WHEN p.estado = 'devuelto' THEN 'DEVUELTO'
        ELSE UPPER(p.estado::TEXT)
    END                         AS estado_display,
    p.observaciones,
    p.usuario_id
FROM prestamos p
INNER JOIN articulos a ON a.id = p.articulo_id
LEFT  JOIN categorias c ON c.id = a.categoria_id
ORDER BY p.fecha_prestamo DESC;

COMMENT ON VIEW v_mis_prestamos IS 'Vista de préstamos filtrable por usuario_id. Panel del cliente.';

-- =============================================================================
-- VISTA 5: Artículos más prestados (métricas para reporte)
-- Top de artículos por número de préstamos. Ayuda al administrador
-- a identificar qué artículos tienen más demanda.
-- Captura de pantalla sugerida: gráfico/tabla de métricas en reportes.
-- =============================================================================

CREATE OR REPLACE VIEW v_articulos_mas_prestados AS
SELECT
    a.id,
    a.nombre                AS articulo,
    c.nombre                AS categoria,
    COUNT(p.id)             AS total_prestamos,
    COUNT(CASE WHEN p.estado = 'activo'   THEN 1 END) AS prestamos_activos,
    COUNT(CASE WHEN p.estado = 'devuelto' THEN 1 END) AS prestamos_devueltos,
    COUNT(CASE WHEN p.estado = 'vencido'  THEN 1 END) AS prestamos_vencidos,
    ROUND(
        AVG(
            CASE WHEN p.fecha_devolucion_real IS NOT NULL
            THEN EXTRACT(EPOCH FROM p.fecha_devolucion_real - p.fecha_prestamo) / 3600
            END
        )::NUMERIC, 2
    )                       AS promedio_horas_prestamo,
    a.stock_total,
    a.stock_disponible,
    a.estado
FROM articulos a
LEFT JOIN prestamos p   ON p.articulo_id = a.id
LEFT JOIN categorias c  ON c.id = a.categoria_id
WHERE a.activo = TRUE
GROUP BY a.id, a.nombre, c.nombre, a.stock_total, a.stock_disponible, a.estado
ORDER BY total_prestamos DESC;

COMMENT ON VIEW v_articulos_mas_prestados IS 'Métricas de uso por artículo. Gráfico de demanda en pantalla de reportes.';

-- =============================================================================
-- VISTA 6: Auditoría reciente (para el administrador)
-- Muestra las últimas operaciones registradas en el historial de auditoría.
-- Captura de pantalla sugerida: panel de auditoría en la sección admin.
-- =============================================================================

CREATE OR REPLACE VIEW v_auditoria_reciente AS
SELECT
    h.id,
    h.tabla_afectada,
    h.operacion,
    h.registro_id,
    h.usuario_db,
    h.fecha,
    h.datos_anteriores,
    h.datos_nuevos
FROM historial_operaciones h
ORDER BY h.fecha DESC
LIMIT 500;

COMMENT ON VIEW v_auditoria_reciente IS 'Últimas 500 operaciones de auditoría. Panel de trazabilidad del administrador.';

-- =============================================================================
-- VISTA 7: Resumen de usuarios del sistema
-- Lista de todos los usuarios con su rol. Para la gestión de usuarios del admin.
-- Captura de pantalla sugerida: tabla de usuarios en el panel de administración.
-- =============================================================================

CREATE OR REPLACE VIEW v_usuarios AS
SELECT
    u.id,
    u.nombre,
    u.apellido,
    u.nombre || ' ' || u.apellido   AS nombre_completo,
    u.correo,
    u.numero_documento,
    u.codigo_barras,
    r.nombre                        AS rol,
    u.activo,
    u.fecha_creacion,
    COUNT(p.id)                     AS total_prestamos,
    COUNT(CASE WHEN p.estado = 'activo' THEN 1 END) AS prestamos_activos
FROM usuarios u
INNER JOIN roles r ON r.id = u.rol_id
LEFT  JOIN prestamos p ON p.usuario_id = u.id
GROUP BY u.id, u.nombre, u.apellido, u.correo, u.numero_documento, u.codigo_barras, r.nombre, u.activo, u.fecha_creacion
ORDER BY u.apellido, u.nombre;

COMMENT ON VIEW v_usuarios IS 'Lista de usuarios con conteo de préstamos. Módulo de gestión de usuarios del admin.';
