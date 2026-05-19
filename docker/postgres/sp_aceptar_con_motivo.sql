-- =============================================================================
-- Permitir que el estudiante deje un motivo/comentario al aceptar
-- =============================================================================

\connect prestamos_umb

-- Reemplazar sp_aceptar_prestamo agregando motivo opcional
DROP PROCEDURE IF EXISTS sp_aceptar_prestamo(INTEGER, INTEGER);

CREATE PROCEDURE sp_aceptar_prestamo(
    p_prestamo_id   INTEGER,
    p_usuario_id    INTEGER,
    p_motivo        TEXT,
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

    UPDATE prestamos
    SET estado = 'activo',
        observaciones = CASE
            WHEN p_motivo IS NOT NULL AND LENGTH(TRIM(p_motivo)) > 0 THEN
                COALESCE(observaciones || E'\n\n', '') ||
                'ACEPTADO POR EL ESTUDIANTE (' || NOW()::TEXT || '): ' || p_motivo
            ELSE observaciones
        END
    WHERE id = p_prestamo_id;

    p_mensaje := 'Préstamo aceptado exitosamente.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al aceptar: ' || SQLERRM;
END;
$$;

-- Reemplazar sp_confirmar_devolucion agregando motivo opcional
DROP PROCEDURE IF EXISTS sp_confirmar_devolucion(INTEGER, INTEGER);

CREATE PROCEDURE sp_confirmar_devolucion(
    p_devolucion_id   INTEGER,
    p_usuario_id      INTEGER,
    p_motivo          TEXT,
    OUT p_mensaje     VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_owner            INTEGER;
    v_confirmada       BOOLEAN;
BEGIN
    SELECT p.usuario_id, d.confirmada_estudiante
    INTO v_owner, v_confirmada
    FROM devoluciones d
    INNER JOIN prestamos p ON p.id = d.prestamo_id
    WHERE d.id = p_devolucion_id;

    IF NOT FOUND THEN
        p_mensaje := 'Devolución no encontrada.';
        RETURN;
    END IF;
    IF v_owner != p_usuario_id THEN
        p_mensaje := 'No autorizado: esta devolución no le pertenece.';
        RETURN;
    END IF;
    IF v_confirmada IS NOT NULL THEN
        p_mensaje := 'Esta devolución ya fue ' ||
                     CASE WHEN v_confirmada THEN 'confirmada' ELSE 'rechazada' END || '.';
        RETURN;
    END IF;

    UPDATE devoluciones
    SET confirmada_estudiante = TRUE,
        fecha_confirmacion    = NOW(),
        observaciones         = CASE
            WHEN p_motivo IS NOT NULL AND LENGTH(TRIM(p_motivo)) > 0 THEN
                COALESCE(observaciones, '') ||
                E'\n\n[CONFIRMADA POR EL ESTUDIANTE, ' || NOW()::TEXT || ']: ' || p_motivo
            ELSE observaciones
        END
    WHERE id = p_devolucion_id;

    p_mensaje := 'Devolución confirmada exitosamente.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al confirmar: ' || SQLERRM;
END;
$$;
