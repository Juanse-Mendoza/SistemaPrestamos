#!/bin/bash
# =============================================================================
# Inicialización de SQL Server en Docker
# Espera a que el motor esté listo y luego ejecuta el esquema T-SQL.
# Este script es invocado como CMD del contenedor de SQL Server.
# =============================================================================

SQLCMD="/opt/mssql-tools18/bin/sqlcmd"
SA_PASS="SqlServer_2026!"

echo "Esperando que SQL Server esté listo..."

# Esperar hasta 90 segundos a que SQL Server acepte conexiones
for i in $(seq 1 18); do
    sleep 5
    if $SQLCMD -S localhost -U sa -P "$SA_PASS" -C -Q "SELECT 1" > /dev/null 2>&1; then
        echo "SQL Server listo tras $((i * 5)) segundos."
        break
    fi
    echo "  Intento $i/18..."
done

# Ejecutar el esquema de inicialización
echo "Ejecutando esquema T-SQL..."
$SQLCMD -S localhost -U sa -P "$SA_PASS" -C \
        -i /sqlserver-init/init_schema.sql \
        -o /var/log/sqlserver_init.log

if [ $? -eq 0 ]; then
    echo "Esquema SQL Server inicializado correctamente."
else
    echo "Error al inicializar esquema SQL Server. Revise /var/log/sqlserver_init.log"
    cat /var/log/sqlserver_init.log
fi
