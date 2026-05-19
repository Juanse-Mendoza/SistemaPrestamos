-- =============================================================================
-- SISTEMA TRANSACCIONAL DE PRÉSTAMOS UNIVERSITARIOS
-- Archivo: 03_stored_procedures.sql — Procedimientos almacenados
-- =============================================================================
-- Los stored procedures encapsulan la lógica de negocio más importante,
-- garantizando que las operaciones críticas (préstamo, devolución, registro)
-- se ejecuten de forma atómica y con todas las validaciones necesarias.
-- =============================================================================

\connect prestamos_umb

-- =============================================================================
-- PROCEDIMIENTO 1: Registrar nuevo usuario
-- Crea un usuario en el sistema validando que el correo no esté duplicado.
-- El password llega ya hasheado desde la aplicación Python (bcrypt).
-- Parámetros:
--   p_nombre, p_apellido   : Nombre completo
--   p_correo               : Correo electrónico único
--   p_password_hash        : Hash bcrypt de la contraseña
--   p_rol_nombre           : 'administrador' o 'cliente'
--   p_numero_documento     : Cédula o carnet (opcional)
-- =============================================================================

CREATE OR REPLACE PROCEDURE sp_registrar_usuario(
    p_nombre            VARCHAR(100),
    p_apellido          VARCHAR(100),
    p_correo            VARCHAR(150),
    p_password_hash     VARCHAR(255),
    p_rol_nombre        tipo_rol,
    p_numero_documento  VARCHAR(50),
    OUT p_usuario_id    INTEGER,
    OUT p_mensaje       VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_rol_id INTEGER;
BEGIN
    -- Verificar correo único
    IF EXISTS (SELECT 1 FROM usuarios WHERE correo = LOWER(p_correo)) THEN
        p_usuario_id := -1;
        p_mensaje := 'El correo electrónico ya está registrado en el sistema.';
        RETURN;
    END IF;

    -- Obtener ID del rol
    SELECT id INTO v_rol_id FROM roles WHERE nombre = p_rol_nombre;
    IF NOT FOUND THEN
        p_usuario_id := -1;
        p_mensaje := 'El rol especificado no existe.';
        RETURN;
    END IF;

    -- Insertar usuario
    INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol_id, numero_documento)
    VALUES (p_nombre, p_apellido, LOWER(p_correo), p_password_hash, v_rol_id, p_numero_documento)
    RETURNING id INTO p_usuario_id;

    p_mensaje := 'Usuario registrado exitosamente con ID: ' || p_usuario_id;

EXCEPTION
    WHEN OTHERS THEN
        p_usuario_id := -1;
        p_mensaje := 'Error al registrar usuario: ' || SQLERRM;
END;
$$;

-- =============================================================================
-- PROCEDIMIENTO 2: Autenticar usuario
-- Verifica las credenciales y retorna los datos del usuario para que
-- la aplicación Python pueda generar el token JWT.
-- El hash de la contraseña se verifica en Python con bcrypt.checkpw().
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_obtener_usuario_login(
    p_correo VARCHAR(150)
)
RETURNS TABLE (
    usuario_id      INTEGER,
    nombre          VARCHAR(100),
    apellido        VARCHAR(100),
    correo          VARCHAR(150),
    password_hash   VARCHAR(255),
    rol_nombre      tipo_rol,
    activo          BOOLEAN
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id,
        u.nombre,
        u.apellido,
        u.correo,
        u.password_hash,
        r.nombre,
        u.activo
    FROM usuarios u
    INNER JOIN roles r ON r.id = u.rol_id
    WHERE u.correo = LOWER(p_correo);
END;
$$;

-- =============================================================================
-- PROCEDIMIENTO 3: Registrar artículo
-- Solo el administrador puede registrar artículos (validado en la app).
-- =============================================================================

CREATE OR REPLACE PROCEDURE sp_registrar_articulo(
    p_nombre            VARCHAR(200),
    p_descripcion       TEXT,
    p_categoria_id      INTEGER,
    p_stock_total       INTEGER,
    p_codigo_interno    VARCHAR(50),
    p_ubicacion         VARCHAR(150),
    p_codigo_barras     VARCHAR(100),
    OUT p_articulo_id   INTEGER,
    OUT p_mensaje       VARCHAR(200)
)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_stock_total <= 0 THEN
        p_articulo_id := -1;
        p_mensaje := 'El stock total debe ser mayor a 0.';
        RETURN;
    END IF;

    IF p_categoria_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM categorias WHERE id = p_categoria_id AND activo = TRUE) THEN
        p_articulo_id := -1;
        p_mensaje := 'La categoría especificada no existe.';
        RETURN;
    END IF;

    -- Verificar que el código de barras no esté duplicado
    IF p_codigo_barras IS NOT NULL AND EXISTS (SELECT 1 FROM articulos WHERE codigo_barras = p_codigo_barras) THEN
        p_articulo_id := -1;
        p_mensaje := 'Ya existe un artículo con ese código de barras: ' || p_codigo_barras;
        RETURN;
    END IF;

    INSERT INTO articulos (nombre, descripcion, categoria_id, stock_total, stock_disponible,
                           codigo_interno, ubicacion, codigo_barras)
    VALUES (p_nombre, p_descripcion, p_categoria_id, p_stock_total, p_stock_total,
            p_codigo_interno, p_ubicacion, p_codigo_barras)
    RETURNING id INTO p_articulo_id;

    p_mensaje := 'Artículo registrado con ID: ' || p_articulo_id;

EXCEPTION
    WHEN unique_violation THEN
        p_articulo_id := -1;
        p_mensaje := 'Ya existe un artículo con ese código interno o código de barras.';
    WHEN OTHERS THEN
        p_articulo_id := -1;
        p_mensaje := 'Error al registrar artículo: ' || SQLERRM;
END;
$$;

-- =============================================================================
-- PROCEDIMIENTO 4: Actualizar stock de artículo
-- Permite al administrador cambiar el stock total. El stock_disponible
-- se recalcula respetando los préstamos activos actuales.
-- =============================================================================

CREATE OR REPLACE PROCEDURE sp_actualizar_stock(
    p_articulo_id       INTEGER,
    p_nuevo_stock_total INTEGER,
    OUT p_mensaje       VARCHAR(200)
)
LANGUAGE plpgsql AS $$
DECLARE
    v_prestados INTEGER;
BEGIN
    -- Cuántas unidades están actualmente prestadas
    SELECT COUNT(*) INTO v_prestados
    FROM prestamos
    WHERE articulo_id = p_articulo_id AND estado = 'activo';

    IF p_nuevo_stock_total < v_prestados THEN
        p_mensaje := 'No se puede reducir el stock a ' || p_nuevo_stock_total ||
                     ' porque hay ' || v_prestados || ' unidades actualmente prestadas.';
        RETURN;
    END IF;

    UPDATE articulos
    SET
        stock_total = p_nuevo_stock_total,
        stock_disponible = p_nuevo_stock_total - v_prestados,
        estado = CASE
                    WHEN p_nuevo_stock_total - v_prestados = 0 THEN 'prestado'::estado_articulo
                    ELSE 'disponible'::estado_articulo
                 END
    WHERE id = p_articulo_id;

    p_mensaje := 'Stock actualizado. Disponible: ' || (p_nuevo_stock_total - v_prestados);

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al actualizar stock: ' || SQLERRM;
END;
$$;

-- =============================================================================
-- PROCEDIMIENTO 5: Registrar préstamo
-- Punto de entrada principal para el proceso de préstamo.
-- Los triggers en la tabla prestamos se encargan del resto.
-- =============================================================================

CREATE OR REPLACE PROCEDURE sp_registrar_prestamo(
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
        observaciones
    )
    VALUES (
        p_usuario_id,
        p_articulo_id,
        p_administrador_id,
        p_fecha_devolucion_esperada,
        p_observaciones
    )
    RETURNING id, codigo_prestamo INTO p_prestamo_id, p_codigo_prestamo;

    p_mensaje := 'Préstamo registrado exitosamente. Código: ' || p_codigo_prestamo;

EXCEPTION
    WHEN OTHERS THEN
        p_prestamo_id := -1;
        p_codigo_prestamo := NULL;
        p_mensaje := SQLERRM;
END;
$$;

-- =============================================================================
-- PROCEDIMIENTO 6: Registrar devolución
-- Registra la devolución física del artículo. El trigger fn_procesar_devolucion
-- actualiza automáticamente el préstamo y el stock del artículo.
-- =============================================================================

CREATE OR REPLACE PROCEDURE sp_registrar_devolucion(
    p_prestamo_id               INTEGER,
    p_estado_articulo_recibido  estado_articulo,
    p_administrador_id          INTEGER,
    p_observaciones             TEXT,
    OUT p_devolucion_id         INTEGER,
    OUT p_mensaje               VARCHAR(200)
)
LANGUAGE plpgsql AS $$
BEGIN
    -- Verificar que el préstamo existe y está activo
    IF NOT EXISTS (
        SELECT 1 FROM prestamos
        WHERE id = p_prestamo_id AND estado IN ('activo', 'vencido')
    ) THEN
        p_devolucion_id := -1;
        p_mensaje := 'El préstamo no existe o ya fue devuelto.';
        RETURN;
    END IF;

    INSERT INTO devoluciones (
        prestamo_id,
        administrador_recibe_id,
        estado_articulo_recibido,
        observaciones
    )
    VALUES (
        p_prestamo_id,
        p_administrador_id,
        p_estado_articulo_recibido,
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

-- =============================================================================
-- PROCEDIMIENTO 7: Dar de baja un artículo
-- Marca el artículo como inactivo. No se puede dar de baja si tiene
-- préstamos activos.
-- =============================================================================

CREATE OR REPLACE PROCEDURE sp_baja_articulo(
    p_articulo_id   INTEGER,
    p_motivo        TEXT,
    OUT p_mensaje   VARCHAR(200)
)
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM prestamos
        WHERE articulo_id = p_articulo_id AND estado = 'activo'
    ) THEN
        p_mensaje := 'No se puede dar de baja: el artículo tiene préstamos activos.';
        RETURN;
    END IF;

    UPDATE articulos
    SET activo = FALSE, estado = 'baja', stock_disponible = 0
    WHERE id = p_articulo_id;

    p_mensaje := 'Artículo dado de baja correctamente.';

EXCEPTION
    WHEN OTHERS THEN
        p_mensaje := 'Error al dar de baja el artículo: ' || SQLERRM;
END;
$$;

-- =============================================================================
-- FUNCIÓN 8: Obtener historial de préstamos de un usuario
-- Retorna el historial completo con información del artículo.
-- Usada por la interfaz del cliente para mostrar su historial.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_historial_usuario(p_usuario_id INTEGER)
RETURNS TABLE (
    prestamo_id             INTEGER,
    codigo_prestamo         VARCHAR(50),
    articulo_nombre         VARCHAR(200),
    articulo_descripcion    TEXT,
    fecha_prestamo          TIMESTAMP,
    fecha_devolucion_esperada TIMESTAMP,
    fecha_devolucion_real   TIMESTAMP,
    estado_prestamo         estado_prestamo,
    observaciones           TEXT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.codigo_prestamo,
        a.nombre,
        a.descripcion,
        p.fecha_prestamo,
        p.fecha_devolucion_esperada,
        p.fecha_devolucion_real,
        p.estado,
        p.observaciones
    FROM prestamos p
    INNER JOIN articulos a ON a.id = p.articulo_id
    WHERE p.usuario_id = p_usuario_id
    ORDER BY p.fecha_prestamo DESC;
END;
$$;

-- =============================================================================
-- FUNCIÓN 9: Reporte general para el administrador
-- Retorna métricas de uso para la pantalla de reportes.
-- =============================================================================

CREATE OR REPLACE FUNCTION fn_reporte_general(
    p_fecha_inicio  TIMESTAMP DEFAULT NOW() - INTERVAL '30 days',
    p_fecha_fin     TIMESTAMP DEFAULT NOW()
)
RETURNS TABLE (
    total_prestamos         BIGINT,
    prestamos_activos       BIGINT,
    prestamos_devueltos     BIGINT,
    prestamos_vencidos      BIGINT,
    articulos_disponibles   BIGINT,
    articulos_prestados     BIGINT,
    articulos_mantenimiento BIGINT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM prestamos WHERE fecha_prestamo BETWEEN p_fecha_inicio AND p_fecha_fin),
        (SELECT COUNT(*) FROM prestamos WHERE estado = 'activo' AND fecha_prestamo BETWEEN p_fecha_inicio AND p_fecha_fin),
        (SELECT COUNT(*) FROM prestamos WHERE estado = 'devuelto' AND fecha_prestamo BETWEEN p_fecha_inicio AND p_fecha_fin),
        (SELECT COUNT(*) FROM prestamos WHERE estado = 'vencido' AND fecha_prestamo BETWEEN p_fecha_inicio AND p_fecha_fin),
        (SELECT COUNT(*) FROM articulos WHERE estado = 'disponible' AND activo = TRUE),
        (SELECT COUNT(*) FROM articulos WHERE estado = 'prestado' AND activo = TRUE),
        (SELECT COUNT(*) FROM articulos WHERE estado = 'mantenimiento' AND activo = TRUE);
END;
$$;
