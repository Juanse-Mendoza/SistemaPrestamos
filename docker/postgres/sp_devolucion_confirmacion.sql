-- =============================================================================
-- Migración: confirmación de la devolución por parte del estudiante
-- =============================================================================

\connect prestamos_umb

-- Columnas nuevas en devoluciones
ALTER TABLE devoluciones
    ADD COLUMN IF NOT EXISTS confirmada_estudiante BOOLEAN DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS fecha_confirmacion    TIMESTAMP,
    ADD COLUMN IF NOT EXISTS motivo_rechazo        TEXT;

COMMENT ON COLUMN devoluciones.confirmada_estudiante IS
  'NULL = pendiente de confirmación, TRUE = aceptada, FALSE = rechazada (disputa)';

-- sp_confirmar_devolucion: estudiante acepta los datos registrados
CREATE OR REPLACE PROCEDURE sp_confirmar_devolucion(
    p_devolucion_id   INTEGER,
    p_usuario_id      INTEGER,
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
        fecha_confirmacion    = NOW()
    WHERE id = p_devolucion_id;

    p_mensaje := 'Devolución confirmada exitosamente.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al confirmar: ' || SQLERRM;
END;
$$;

-- sp_rechazar_devolucion: estudiante no está de acuerdo (queda en disputa)
CREATE OR REPLACE PROCEDURE sp_rechazar_devolucion(
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
        p_mensaje := 'No autorizado.';
        RETURN;
    END IF;
    IF v_confirmada IS NOT NULL THEN
        p_mensaje := 'Esta devolución ya fue procesada.';
        RETURN;
    END IF;
    IF p_motivo IS NULL OR LENGTH(TRIM(p_motivo)) = 0 THEN
        p_mensaje := 'Debe indicar el motivo del rechazo.';
        RETURN;
    END IF;

    UPDATE devoluciones
    SET confirmada_estudiante = FALSE,
        fecha_confirmacion    = NOW(),
        motivo_rechazo        = p_motivo
    WHERE id = p_devolucion_id;

    p_mensaje := 'Rechazo registrado. La devolución queda en disputa para revisión del administrador.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al rechazar: ' || SQLERRM;
END;
$$;
