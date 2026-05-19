-- =============================================================================
-- Multas v2: tarifa configurable por artículo + pagos parciales
-- =============================================================================

\connect prestamos_umb

-- 1) Tarifa de multa por hora, por artículo (NULL = usa default global)
ALTER TABLE articulos
    ADD COLUMN IF NOT EXISTS multa_por_hora_cop NUMERIC(10,2);

COMMENT ON COLUMN articulos.multa_por_hora_cop IS
  'Tarifa de multa en COP por cada hora de retraso. NULL = usa default global del sistema.';

-- 2) Tabla para registrar pagos (puede haber varios pagos por préstamo)
CREATE TABLE IF NOT EXISTS pagos_multa (
    id                SERIAL PRIMARY KEY,
    prestamo_id       INTEGER NOT NULL REFERENCES prestamos(id) ON DELETE RESTRICT,
    monto             NUMERIC(12,2) NOT NULL CHECK (monto > 0),
    fecha_pago        TIMESTAMP DEFAULT NOW(),
    admin_recibe_id   INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    observaciones     TEXT
);

CREATE INDEX IF NOT EXISTS idx_pagos_multa_prestamo ON pagos_multa(prestamo_id);

COMMENT ON TABLE pagos_multa IS
  'Registro de cada pago (parcial o total) de multa por retraso. Permite saldos pendientes.';

-- 3) Migrar pagos existentes (de las columnas viejas) a la nueva tabla
INSERT INTO pagos_multa (prestamo_id, monto, fecha_pago, admin_recibe_id, observaciones)
SELECT id, multa_monto_pagado, multa_fecha_pago, multa_admin_recibe_id,
       COALESCE(multa_observaciones, '(migrado de registro anterior)')
FROM prestamos
WHERE multa_pagada = TRUE
  AND multa_monto_pagado IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM pagos_multa WHERE prestamo_id = prestamos.id);
