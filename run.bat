@echo off
REM =============================================================================
REM  PrestaUni — Arranque del sistema (Windows)
REM  Acceso: http://localhost:8000
REM =============================================================================
REM  run.bat up      → Construye e inicia todos los servicios Docker
REM  run.bat down    → Detiene los servicios (conserva los datos)
REM  run.bat reset   → Detiene y BORRA TODOS LOS DATOS
REM  run.bat logs    → Muestra logs de la aplicación web
REM  run.bat status  → Estado de los contenedores
REM =============================================================================

SET CMD=%1
IF "%CMD%"=="" GOTO HELP

IF "%CMD%"=="up"     GOTO UP
IF "%CMD%"=="down"   GOTO DOWN
IF "%CMD%"=="reset"  GOTO RESET
IF "%CMD%"=="logs"   GOTO LOGS
IF "%CMD%"=="status" GOTO STATUS
GOTO HELP

:UP
echo.
echo [PrestaUni] Iniciando sistema...
docker compose up -d --build
IF ERRORLEVEL 1 (
    echo ERROR: Verifique que Docker Desktop este en ejecucion.
    EXIT /B 1
)
echo.
echo Esperando que los servicios esten listos...
timeout /t 20 /nobreak >nul
docker compose ps
echo.
echo Sistema listo. Abra su navegador en: http://localhost:8000
echo Usuario admin: admin@umb.edu.co / Admin2026
GOTO END

:DOWN
echo [PrestaUni] Deteniendo servicios...
docker compose down
echo Los datos persisten en los volumenes Docker.
GOTO END

:RESET
echo ADVERTENCIA: Se eliminaran TODOS los datos del sistema.
SET /P CONFIRM=Escriba SI para confirmar:
IF NOT "%CONFIRM%"=="SI" ( echo Cancelado. & GOTO END )
docker compose down -v
echo Datos eliminados. El proximo inicio recreara la base de datos.
GOTO END

:LOGS
echo [PrestaUni] Logs en tiempo real (Ctrl+C para salir):
docker compose logs -f web
GOTO END

:STATUS
docker compose ps
GOTO END

:HELP
echo.
echo  PrestaUni — Sistema de Prestamos UMB
echo  Acceso: http://localhost:8000
echo.
echo  run.bat up      Iniciar sistema completo
echo  run.bat down    Detener (conserva datos)
echo  run.bat reset   Detener y borrar datos
echo  run.bat logs    Ver logs de la app web
echo  run.bat status  Estado de los servicios
echo.

:END
