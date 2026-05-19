-- =============================================================================
-- Refactor: tiempo máximo de préstamo en minutos (granularidad fina)
-- =============================================================================

\connect prestamos_umb

-- Recrear vista v_stock_disponible con la nueva columna
DROP VIEW IF EXISTS v_stock_disponible CASCADE;
CREATE VIEW v_stock_disponible AS
SELECT
    a.id                    AS articulo_id,
    a.nombre                AS articulo,
    a.descripcion,
    c.nombre                AS categoria,
    a.estado,
    a.stock_total,
    a.stock_disponible,
    a.codigo_interno,
    a.codigo_barras,
    a.ubicacion,
    a.tiempo_maximo_minutos,
    a.fecha_registro
FROM articulos a
LEFT JOIN categorias c ON c.id = a.categoria_id
WHERE a.activo = TRUE
ORDER BY a.nombre;

-- Reemplazar sp_registrar_articulo para usar minutos
DROP PROCEDURE IF EXISTS sp_registrar_articulo(VARCHAR, TEXT, INTEGER, INTEGER, VARCHAR, VARCHAR, VARCHAR, INTEGER);

CREATE PROCEDURE sp_registrar_articulo(
    p_nombre                 VARCHAR(200),
    p_descripcion            TEXT,
    p_categoria_id           INTEGER,
    p_stock_total            INTEGER,
    p_codigo_interno         VARCHAR(50),
    p_ubicacion              VARCHAR(150),
    p_codigo_barras          VARCHAR(100),
    p_tiempo_maximo_minutos  INTEGER,
    OUT p_articulo_id        INTEGER,
    OUT p_mensaje            VARCHAR(200)
)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_stock_total <= 0 THEN
        p_articulo_id := -1;
        p_mensaje := 'El stock total debe ser mayor a 0.';
        RETURN;
    END IF;
    IF p_categoria_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM categorias WHERE id = p_categoria_id AND activo = TRUE
    ) THEN
        p_articulo_id := -1;
        p_mensaje := 'La categoría especificada no existe.';
        RETURN;
    END IF;
    IF p_codigo_barras IS NOT NULL AND EXISTS (
        SELECT 1 FROM articulos WHERE codigo_barras = p_codigo_barras
    ) THEN
        p_articulo_id := -1;
        p_mensaje := 'Ya existe un artículo con ese código de barras: ' || p_codigo_barras;
        RETURN;
    END IF;
    IF p_tiempo_maximo_minutos IS NOT NULL AND p_tiempo_maximo_minutos <= 0 THEN
        p_articulo_id := -1;
        p_mensaje := 'El tiempo máximo de préstamo debe ser mayor a 0.';
        RETURN;
    END IF;

    INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible,
                           codigo_interno, ubicacion, codigo_barras, tiempo_maximo_minutos)
    VALUES (p_nombre, p_descripcion, p_categoria_id, p_stock_total, p_stock_total,
            p_codigo_interno, p_ubicacion, p_codigo_barras, p_tiempo_maximo_minutos)
    RETURNING id INTO p_articulo_id;

    p_mensaje := 'Artículo registrado con ID: ' || p_articulo_id;

EXCEPTION
    WHEN unique_violation THEN
        p_articulo_id := -1;
        p_mensaje := 'Ya existe un artículo con ese código interno o de barras.';
    WHEN OTHERS THEN
        p_articulo_id := -1;
        p_mensaje := 'Error al registrar artículo: ' || SQLERRM;
END;
$$;

-- Trigger fn_validar_prestamo: validar tiempo máximo en minutos
CREATE OR REPLACE FUNCTION fn_validar_prestamo()
RETURNS TRIGGER AS $$
DECLARE
    v_estado          estado_articulo;
    v_stock           INTEGER;
    v_max_minutos     INTEGER;
    v_minutos_pedidos NUMERIC;
    v_legible         VARCHAR(60);
BEGIN
    SELECT estado, stock_disponible, tiempo_maximo_minutos
    INTO v_estado, v_stock, v_max_minutos
    FROM articulos WHERE id = NEW.articulo_id AND activo = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El artículo con ID % no existe o está dado de baja.', NEW.articulo_id;
    END IF;
    IF v_estado != 'disponible' THEN
        RAISE EXCEPTION 'El artículo no está disponible para préstamo. Estado actual: %', v_estado;
    END IF;
    IF v_stock <= 0 THEN
        RAISE EXCEPTION 'No hay stock disponible para el artículo solicitado.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM usuarios WHERE id = NEW.usuario_id AND activo = TRUE) THEN
        RAISE EXCEPTION 'El usuario con ID % no existe o está inactivo.', NEW.usuario_id;
    END IF;
    IF NEW.fecha_devolucion_esperada <= NOW() THEN
        RAISE EXCEPTION 'La fecha de devolución esperada debe ser posterior a la fecha actual.';
    END IF;

    -- Validar tiempo máximo en minutos
    IF v_max_minutos IS NOT NULL THEN
        v_minutos_pedidos := EXTRACT(EPOCH FROM (NEW.fecha_devolucion_esperada - NEW.fecha_prestamo)) / 60.0;
        IF v_minutos_pedidos > v_max_minutos THEN
            -- Formato legible del límite
            IF v_max_minutos % 1440 = 0 THEN
                v_legible := (v_max_minutos / 1440) || ' día(s)';
            ELSIF v_max_minutos % 60 = 0 THEN
                v_legible := (v_max_minutos / 60) || ' hora(s)';
            ELSE
                v_legible := v_max_minutos || ' minuto(s)';
            END IF;
            RAISE EXCEPTION 'El préstamo no puede exceder %. Solicitado: % minuto(s).',
                v_legible, ROUND(v_minutos_pedidos::numeric, 0);
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
