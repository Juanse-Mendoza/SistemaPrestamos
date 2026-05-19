DROP PROCEDURE IF EXISTS sp_registrar_devolucion(INTEGER, estado_articulo, INTEGER, TEXT);

CREATE OR REPLACE PROCEDURE sp_registrar_devolucion(
    p_prestamo_id               INTEGER,
    p_estado_articulo_recibido  estado_articulo,
    p_administrador_id          INTEGER,
    p_observaciones             TEXT,
    p_fecha_devolucion          TIMESTAMP,
    OUT p_devolucion_id         INTEGER,
    OUT p_mensaje               VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_fecha_prestamo TIMESTAMP;
    v_fecha_efectiva TIMESTAMP;
BEGIN
    SELECT fecha_prestamo INTO v_fecha_prestamo
    FROM prestamos
    WHERE id = p_prestamo_id AND estado IN ('activo', 'vencido');

    IF NOT FOUND THEN
        p_devolucion_id := -1;
        p_mensaje := 'El préstamo no existe o ya fue devuelto.';
        RETURN;
    END IF;

    v_fecha_efectiva := COALESCE(p_fecha_devolucion, NOW());

    IF v_fecha_efectiva < v_fecha_prestamo THEN
        p_devolucion_id := -1;
        p_mensaje := 'La fecha de devolución no puede ser anterior a la fecha del préstamo.';
        RETURN;
    END IF;

    INSERT INTO devoluciones (
        prestamo_id,
        administrador_recibe_id,
        estado_articulo_recibido,
        fecha_devolucion,
        observaciones
    )
    VALUES (
        p_prestamo_id,
        p_administrador_id,
        p_estado_articulo_recibido,
        v_fecha_efectiva,
        p_observaciones
    )
    RETURNING id INTO p_devolucion_id;

    p_mensaje := 'Devolución registrada exitosamente.';

EXCEPTION
    WHEN unique_violation THEN
        p_devolucion_id := -1;
        p_mensaje := 'Este préstamo ya tiene una devolución registrada.';
    WHEN OTHERS THEN
        p_devolucion_id := -1;
        p_mensaje := 'Error al registrar devolución: ' || SQLERRM;
END;
$$;
