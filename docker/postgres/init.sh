#!/bin/bash
# =============================================================================
# Script de inicialización de PostgreSQL para Docker
# Se ejecuta automáticamente la PRIMERA VEZ que se crea el contenedor.
# Los archivos SQL se leen desde /sql-init (montado desde ./database/)
# y se limpian de los comandos de conexión antes de ejecutarlos.
# =============================================================================
set -e

echo "============================================="
echo " Inicializando base de datos prestamos_umb"
echo "============================================="

PSQL="psql -v ON_ERROR_STOP=1 --username=$POSTGRES_USER --dbname=$POSTGRES_DB"

run_sql() {
    local file=$1
    echo "→ Ejecutando: $(basename $file)"
    # Eliminar líneas que crean/conectan a la BD (ya existe por POSTGRES_DB env)
    sed -E \
        '/^\\\\connect /d;
         /^DROP DATABASE /d;
         /^CREATE DATABASE /d;
         /^    WITH ENCODING/d;
         /^    LC_COLLATE/d;
         /^    LC_CTYPE/d;
         /^    TEMPLATE/d;' \
        "$file" | $PSQL
    echo "   ✓ OK"
}

# Ejecutar archivos en orden
for f in /sql-init/01_schema.sql \
          /sql-init/02_triggers.sql \
          /sql-init/03_stored_procedures.sql \
          /sql-init/04_views.sql \
          /sql-init/05_seed_data.sql; do
    if [ -f "$f" ]; then
        run_sql "$f"
    else
        echo "   ! Archivo no encontrado: $f"
    fi
done

# Crear usuario de la aplicación con contraseña correcta
$PSQL <<-EOSQL
    -- Usuario que usa la aplicación Python
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_prestamos') THEN
            CREATE USER app_prestamos WITH PASSWORD 'App_Prestamos_2026!';
        END IF;
    END\$\$;
    GRANT CONNECT ON DATABASE prestamos_umb TO app_prestamos;
    GRANT USAGE ON SCHEMA public TO app_prestamos;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_prestamos;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_prestamos;
    GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_prestamos;
    GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA public TO app_prestamos;
EOSQL

echo ""
echo "============================================="
echo " Base de datos inicializada correctamente"
echo "============================================="
