-- =============================================================================
-- Migración: préstamos en estado PENDIENTE + flujo aceptar/rechazar
-- =============================================================================

\connect prestamos_umb

-- sp_registrar_prestamo ahora crea el préstamo como 'pendiente'
DROP PROCEDURE IF EXISTS sp_registrar_prestamo(INTEGER, INTEGER, TIMESTAMP, INTEGER, TEXT);

CREATE PROCEDURE sp_registrar_prestamo(
    p_usuario_id                INTEGER,
    p_articulo_id               INTEGER,
    p_fecha_devolucion_esperada TIMESTAMP,
    p_administrador_id          INTEGER,
    p_observaciones             TEXT,
    OUT p_prestamo_id           INTEGER,
    OUT p_codigo_prestamo       VARCHAR(50),
    OUT p_mensaje               VARCHAR(200)
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO prestamos (
        usuario_id,
        articulo_id,
        administrador_autoriza_id,
        fecha_devolucion_esperada,
        observaciones,
        estado
    )
    VALUES (
        p_usuario_id,
        p_articulo_id,
        p_administrador_id,
        p_fecha_devolucion_esperada,
        p_observaciones,
        'pendiente'::estado_prestamo
    )
    RETURNING id, codigo_prestamo INTO p_prestamo_id, p_codigo_prestamo;

    p_mensaje := 'Préstamo creado en estado PENDIENTE. Código: ' || p_codigo_prestamo
                 || '. Esperando aceptación del estudiante.';

EXCEPTION
    WHEN OTHERS THEN
        p_prestamo_id := -1;
        p_codigo_prestamo := NULL;
        p_mensaje := SQLERRM;
END;
$$;

-- sp_aceptar_prestamo: estudiante acepta su préstamo pendiente
CREATE OR REPLACE PROCEDURE sp_aceptar_prestamo(
    p_prestamo_id   INTEGER,
    p_usuario_id    INTEGER,
    OUT p_mensaje   VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_estado estado_prestamo;
    v_owner  INTEGER;
BEGIN
    SELECT estado, usuario_id INTO v_estado, v_owner
    FROM prestamos WHERE id = p_prestamo_id;

    IF NOT FOUND THEN
        p_mensaje := 'Préstamo no encontrado.';
        RETURN;
    END IF;

    IF v_owner != p_usuario_id THEN
        p_mensaje := 'No autorizado: este préstamo no le pertenece.';
        RETURN;
    END IF;

    IF v_estado != 'pendiente' THEN
        p_mensaje := 'El préstamo ya no está pendiente (estado actual: ' || v_estado || ').';
        RETURN;
    END IF;

    UPDATE prestamos SET estado = 'activo' WHERE id = p_prestamo_id;
    p_mensaje := 'Préstamo aceptado exitosamente.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al aceptar: ' || SQLERRM;
END;
$$;

-- sp_rechazar_prestamo: estudiante rechaza, se restaura stock
CREATE OR REPLACE PROCEDURE sp_rechazar_prestamo(
    p_prestamo_id   INTEGER,
    p_usuario_id    INTEGER,
    p_motivo        TEXT,
    OUT p_mensaje   VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_estado     estado_prestamo;
    v_owner      INTEGER;
    v_articulo   INTEGER;
BEGIN
    SELECT estado, usuario_id, articulo_id INTO v_estado, v_owner, v_articulo
    FROM prestamos WHERE id = p_prestamo_id;

    IF NOT FOUND THEN
        p_mensaje := 'Préstamo no encontrado.';
        RETURN;
    END IF;

    IF v_owner != p_usuario_id THEN
        p_mensaje := 'No autorizado.';
        RETURN;
    END IF;

    IF v_estado != 'pendiente' THEN
        p_mensaje := 'El préstamo ya no está pendiente.';
        RETURN;
    END IF;

    -- Registrar motivo del rechazo en observaciones
    UPDATE prestamos
    SET estado = 'rechazado',
        observaciones = COALESCE(observaciones || E'\n\n', '') ||
                        'RECHAZADO POR EL ESTUDIANTE: ' ||
                        COALESCE(p_motivo, 'Sin motivo especificado')
    WHERE id = p_prestamo_id;

    -- Restaurar stock del artículo
    UPDATE articulos
    SET stock_disponible = stock_disponible + 1,
        estado = CASE
                    WHEN stock_disponible + 1 > 0 AND estado = 'prestado' THEN 'disponible'::estado_articulo
                    ELSE estado
                 END
    WHERE id = v_articulo;

    p_mensaje := 'Préstamo rechazado. Stock restaurado.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al rechazar: ' || SQLERRM;
END;
$$;
