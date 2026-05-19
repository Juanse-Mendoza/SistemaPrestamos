-- =============================================================================
-- SISTEMA TRANSACCIONAL DE PRÉSTAMOS UNIVERSITARIOS
-- Archivo: 02_triggers.sql — Triggers y automatizaciones
-- =============================================================================
-- Los triggers implementan la lógica de negocio directamente en la base de datos,
-- garantizando consistencia de datos sin importar qué aplicación los modifique.
-- =============================================================================

\connect prestamos_umb

-- =============================================================================
-- TRIGGER 1: Actualizar fecha_actualizacion en usuarios
-- Se dispara automáticamente antes de cada UPDATE para mantener el registro
-- de cuándo fue modificado por última vez cada usuario.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_actualizar_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_usuarios_timestamp
    BEFORE UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION fn_actualizar_timestamp();

CREATE TRIGGER trg_articulos_timestamp
    BEFORE UPDATE ON articulos
    FOR EACH ROW
    EXECUTE FUNCTION fn_actualizar_timestamp();

-- =============================================================================
-- TRIGGER 2: Validar disponibilidad antes de registrar un préstamo
-- Verifica que el artículo esté disponible y tenga stock > 0.
-- Se ejecuta ANTES del INSERT para bloquear el registro si no hay stock.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_validar_prestamo()
RETURNS TRIGGER AS $$
DECLARE
    v_estado    estado_articulo;
    v_stock     INTEGER;
    v_rol_usuario tipo_rol;
BEGIN
    -- Verificar que el artículo existe y está disponible
    SELECT estado, stock_disponible
    INTO v_estado, v_stock
    FROM articulos
    WHERE id = NEW.articulo_id AND activo = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El artículo con ID % no existe o está dado de baja.', NEW.articulo_id;
    END IF;

    IF v_estado != 'disponible' THEN
        RAISE EXCEPTION 'El artículo no está disponible para préstamo. Estado actual: %', v_estado;
    END IF;

    IF v_stock <= 0 THEN
        RAISE EXCEPTION 'No hay stock disponible para el artículo solicitado.';
    END IF;

    -- Verificar que el usuario solicitante existe y está activo
    IF NOT EXISTS (SELECT 1 FROM usuarios WHERE id = NEW.usuario_id AND activo = TRUE) THEN
        RAISE EXCEPTION 'El usuario con ID % no existe o está inactivo.', NEW.usuario_id;
    END IF;

    -- Verificar que la fecha de devolución esperada es futura
    IF NEW.fecha_devolucion_esperada <= NOW() THEN
        RAISE EXCEPTION 'La fecha de devolución esperada debe ser posterior a la fecha actual.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_prestamo
    BEFORE INSERT ON prestamos
    FOR EACH ROW
    EXECUTE FUNCTION fn_validar_prestamo();

-- =============================================================================
-- TRIGGER 3: Actualizar stock del artículo al registrar un préstamo
-- Después de confirmar el préstamo, descuenta del stock disponible
-- y actualiza el estado del artículo si el stock llega a 0.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_descontar_stock_prestamo()
RETURNS TRIGGER AS $$
DECLARE
    v_nuevo_stock INTEGER;
BEGIN
    UPDATE articulos
    SET
        stock_disponible = stock_disponible - 1,
        estado = CASE
                    WHEN stock_disponible - 1 = 0 THEN 'prestado'::estado_articulo
                    ELSE 'disponible'::estado_articulo
                 END
    WHERE id = NEW.articulo_id
    RETURNING stock_disponible INTO v_nuevo_stock;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_descontar_stock_prestamo
    AFTER INSERT ON prestamos
    FOR EACH ROW
    EXECUTE FUNCTION fn_descontar_stock_prestamo();

-- =============================================================================
-- TRIGGER 4: Actualizar stock y estado al registrar una devolución
-- Después de insertar la devolución, actualiza el préstamo como 'devuelto'
-- y restaura el stock. Si el artículo vuelve en mal estado, lo pone en
-- 'mantenimiento' en lugar de 'disponible'.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_procesar_devolucion()
RETURNS TRIGGER AS $$
DECLARE
    v_articulo_id INTEGER;
BEGIN
    -- Obtener el artículo relacionado con el préstamo
    SELECT articulo_id INTO v_articulo_id
    FROM prestamos
    WHERE id = NEW.prestamo_id;

    -- Cerrar el préstamo
    UPDATE prestamos
    SET
        estado = 'devuelto',
        fecha_devolucion_real = NEW.fecha_devolucion
    WHERE id = NEW.prestamo_id;

    -- Restaurar stock y actualizar estado según condición del artículo devuelto
    UPDATE articulos
    SET
        stock_disponible = stock_disponible + 1,
        estado = CASE
                    WHEN NEW.estado_articulo_recibido = 'mantenimiento' THEN 'mantenimiento'::estado_articulo
                    WHEN NEW.estado_articulo_recibido = 'baja' THEN 'baja'::estado_articulo
                    ELSE CASE
                            WHEN stock_disponible + 1 > 0 THEN 'disponible'::estado_articulo
                            ELSE estado
                         END
                 END
    WHERE id = v_articulo_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_procesar_devolucion
    AFTER INSERT ON devoluciones
    FOR EACH ROW
    EXECUTE FUNCTION fn_procesar_devolucion();

-- =============================================================================
-- TRIGGER 5: Detectar préstamos vencidos automáticamente
-- Al consultar préstamos activos, se puede ejecutar esta función para
-- marcar como 'vencido' cualquier préstamo cuya fecha esperada ya pasó.
-- Se llama desde la aplicación o mediante pg_cron si se instala la extensión.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_marcar_prestamos_vencidos()
RETURNS INTEGER AS $$
DECLARE
    v_actualizados INTEGER;
BEGIN
    UPDATE prestamos
    SET estado = 'vencido'
    WHERE estado = 'activo'
      AND fecha_devolucion_esperada < NOW();

    GET DIAGNOSTICS v_actualizados = ROW_COUNT;
    RETURN v_actualizados;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGER 6: Auditoría de usuarios (INSERT / UPDATE / DELETE)
-- Registra automáticamente en historial_operaciones cualquier cambio
-- sobre la tabla usuarios, incluyendo quién lo hizo y cuándo.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_auditoria_usuarios()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_nuevos)
        VALUES ('usuarios', 'INSERT', NEW.id, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_anteriores, datos_nuevos)
        VALUES ('usuarios', 'UPDATE', NEW.id, row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_anteriores)
        VALUES ('usuarios', 'DELETE', OLD.id, row_to_json(OLD)::jsonb);
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auditoria_usuarios
    AFTER INSERT OR UPDATE OR DELETE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION fn_auditoria_usuarios();

-- =============================================================================
-- TRIGGER 7: Auditoría de artículos
-- Igual al anterior pero sobre la tabla articulos.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_auditoria_articulos()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_nuevos)
        VALUES ('articulos', 'INSERT', NEW.id, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_anteriores, datos_nuevos)
        VALUES ('articulos', 'UPDATE', NEW.id, row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_anteriores)
        VALUES ('articulos', 'DELETE', OLD.id, row_to_json(OLD)::jsonb);
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auditoria_articulos
    AFTER INSERT OR UPDATE OR DELETE ON articulos
    FOR EACH ROW
    EXECUTE FUNCTION fn_auditoria_articulos();

-- =============================================================================
-- TRIGGER 8: Auditoría de préstamos
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_auditoria_prestamos()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_nuevos)
        VALUES ('prestamos', 'INSERT', NEW.id, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO historial_operaciones (tabla_afectada, operacion, registro_id, datos_anteriores, datos_nuevos)
        VALUES ('prestamos', 'UPDATE', NEW.id, row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auditoria_prestamos
    AFTER INSERT OR UPDATE ON prestamos
    FOR EACH ROW
    EXECUTE FUNCTION fn_auditoria_prestamos();

-- =============================================================================
-- TRIGGER 9: Prevenir eliminación de usuarios con préstamos activos
-- Protege la integridad referencial: no se puede eliminar un usuario
-- que tenga préstamos en curso.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_proteger_usuario_activo()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM prestamos
        WHERE usuario_id = OLD.id AND estado = 'activo'
    ) THEN
        RAISE EXCEPTION 'No se puede eliminar el usuario ID % porque tiene préstamos activos.', OLD.id;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_proteger_usuario_activo
    BEFORE DELETE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION fn_proteger_usuario_activo();
