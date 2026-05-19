-- =============================================================================
-- Acciones interactivas del admin sobre solicitudes y disputas
-- =============================================================================

\connect prestamos_umb

-- sp_cancelar_prestamo_pendiente: el admin retira un préstamo aún no aceptado
CREATE OR REPLACE PROCEDURE sp_cancelar_prestamo_pendiente(
    p_prestamo_id   INTEGER,
    p_admin_id      INTEGER,
    p_motivo        TEXT,
    OUT p_mensaje   VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_estado     estado_prestamo;
    v_articulo   INTEGER;
BEGIN
    SELECT estado, articulo_id INTO v_estado, v_articulo
    FROM prestamos WHERE id = p_prestamo_id;

    IF NOT FOUND THEN
        p_mensaje := 'Préstamo no encontrado.';
        RETURN;
    END IF;
    IF v_estado != 'pendiente' THEN
        p_mensaje := 'Solo se pueden cancelar préstamos pendientes (estado actual: ' || v_estado || ').';
        RETURN;
    END IF;

    UPDATE prestamos
    SET estado = 'cancelado',
        observaciones = COALESCE(observaciones || E'\n\n', '') ||
                        'CANCELADO POR EL ADMINISTRADOR (ID ' || p_admin_id || '): ' ||
                        COALESCE(p_motivo, 'Sin motivo especificado')
    WHERE id = p_prestamo_id;

    -- Restaurar stock
    UPDATE articulos
    SET stock_disponible = stock_disponible + 1,
        estado = CASE
                    WHEN stock_disponible + 1 > 0 AND estado = 'prestado' THEN 'disponible'::estado_articulo
                    ELSE estado
                 END
    WHERE id = v_articulo;

    p_mensaje := 'Préstamo cancelado. Stock restaurado.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al cancelar: ' || SQLERRM;
END;
$$;

-- sp_corregir_devolucion: admin reabre la disputa con nuevos datos
CREATE OR REPLACE PROCEDURE sp_corregir_devolucion(
    p_devolucion_id     INTEGER,
    p_admin_id          INTEGER,
    p_nuevo_estado      estado_articulo,
    p_nuevas_obs        TEXT,
    p_nota_admin        TEXT,
    OUT p_mensaje       VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_confirmada    BOOLEAN;
    v_articulo_id   INTEGER;
    v_estado_old    estado_articulo;
BEGIN
    SELECT d.confirmada_estudiante, p.articulo_id, d.estado_articulo_recibido
    INTO v_confirmada, v_articulo_id, v_estado_old
    FROM devoluciones d
    INNER JOIN prestamos p ON p.id = d.prestamo_id
    WHERE d.id = p_devolucion_id;

    IF NOT FOUND THEN
        p_mensaje := 'Devolución no encontrada.';
        RETURN;
    END IF;
    IF v_confirmada IS NOT FALSE THEN
        p_mensaje := 'Solo se pueden corregir devoluciones en disputa.';
        RETURN;
    END IF;

    -- Sobrescribir la devolución con los nuevos datos y volver a pendiente
    UPDATE devoluciones
    SET estado_articulo_recibido = p_nuevo_estado,
        observaciones            = COALESCE(p_nuevas_obs, observaciones) ||
                                    E'\n\n[CORRECCIÓN DEL ADMIN tras disputa, ' || NOW()::TEXT || ']: ' ||
                                    COALESCE(p_nota_admin, 'Datos corregidos.'),
        confirmada_estudiante    = NULL,
        fecha_confirmacion       = NULL
    WHERE id = p_devolucion_id;

    -- Ajustar estado del artículo si cambió
    IF p_nuevo_estado IS DISTINCT FROM v_estado_old THEN
        UPDATE articulos
        SET estado = CASE
                        WHEN p_nuevo_estado = 'mantenimiento' THEN 'mantenimiento'::estado_articulo
                        WHEN p_nuevo_estado = 'baja' THEN 'baja'::estado_articulo
                        WHEN stock_disponible > 0 THEN 'disponible'::estado_articulo
                        ELSE estado
                     END
        WHERE id = v_articulo_id;
    END IF;

    p_mensaje := 'Devolución corregida. Pendiente de nueva confirmación del estudiante.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al corregir: ' || SQLERRM;
END;
$$;

-- sp_cerrar_disputa: admin mantiene su decisión, cierra el caso
CREATE OR REPLACE PROCEDURE sp_cerrar_disputa(
    p_devolucion_id   INTEGER,
    p_admin_id        INTEGER,
    p_nota            TEXT,
    OUT p_mensaje     VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_confirmada BOOLEAN;
BEGIN
    SELECT confirmada_estudiante INTO v_confirmada
    FROM devoluciones WHERE id = p_devolucion_id;

    IF NOT FOUND THEN
        p_mensaje := 'Devolución no encontrada.';
        RETURN;
    END IF;
    IF v_confirmada IS NOT FALSE THEN
        p_mensaje := 'Solo se pueden cerrar disputas activas.';
        RETURN;
    END IF;
    IF p_nota IS NULL OR LENGTH(TRIM(p_nota)) = 0 THEN
        p_mensaje := 'Debe indicar la nota de cierre.';
        RETURN;
    END IF;

    UPDATE devoluciones
    SET confirmada_estudiante = TRUE,
        fecha_confirmacion    = NOW(),
        observaciones         = COALESCE(observaciones, '') ||
                                E'\n\n[DISPUTA CERRADA POR EL ADMIN, ' || NOW()::TEXT || ']: ' || p_nota
    WHERE id = p_devolucion_id;

    p_mensaje := 'Disputa cerrada. La devolución queda confirmada con nota del administrador.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al cerrar disputa: ' || SQLERRM;
END;
$$;
