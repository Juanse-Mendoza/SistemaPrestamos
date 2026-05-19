# PrestaUni — Sistema de Préstamos UMB

Sistema transaccional de préstamos universitarios con flujo de aceptación bilateral
(admin y estudiante), gestión de multas por retraso en COP, soporte para escáneres
de código de barras (USB y cámara) y reportes en PDF.

## Stack

- **Backend:** FastAPI + Uvicorn (Python 3.12)
- **Base de datos:** PostgreSQL 16 (con triggers, procedimientos y vistas)
- **Réplica:** SQL Server 2022 + servicio de sync (cada 5 min)
- **Frontend:** Jinja2 + CSS/JS vanilla
- **Auth:** JWT en cookie HTTP-only + bcrypt
- **Reportes:** ReportLab
- **Contenedores:** Docker Compose

## Arquitectura por capas

```
Presentación (templates + static)
        ↓
Controladores (app/routes/)
        ↓
Lógica de negocio (app/services/)
        ↓
Acceso a datos (app/database/)
        ↓
PostgreSQL (triggers + SPs + views)
```

## Instalación rápida

### Requisitos
- [Docker Desktop](https://www.docker.com/products/docker-desktop) instalado y en ejecución

### Pasos

```bash
# 1. Clonar
git clone https://github.com/TU_USUARIO/SistemaPrestamos.git
cd SistemaPrestamos

# 2. Levantar
docker compose up -d --build
# o en Windows:  run.bat up

# 3. Acceder
# Navegador → http://localhost:8000
```

### Credenciales por defecto

| Rol           | Correo                       | Contraseña        |
|---------------|------------------------------|-------------------|
| Administrador | `admin@umb.edu.co`           | `Admin2026!`      |

> El usuario admin viene preconfigurado en el seed. El primer login está listo
> nada más arrancar los contenedores.

## Comandos útiles

```bash
docker compose up -d --build    # construir e iniciar
docker compose logs -f web      # ver logs en vivo de la app
docker compose ps               # estado de los servicios
docker compose down             # detener (conserva datos)
docker compose down -v          # detener y BORRAR base de datos

# Atajos Windows
run.bat up | down | reset | logs | status
```

## Funcionalidades principales

### Para el administrador
- Dashboard con préstamos en curso (filtrable por código de barras)
- Gestión de inventario: artículos con tarifa de multa configurable y tiempo máximo
- Flujo de préstamo (hasta 2 artículos por solicitud)
- Aceptación de devoluciones con checklist
- Panel de solicitudes pendientes y disputas
- Sistema de multas en COP con pagos parciales
- Reportes en PDF: productos, usuarios, historial (con filtro de fechas)
- CRUD de usuarios con generación de códigos de barras

### Para el estudiante
- Catálogo de artículos disponibles
- Solicitud de préstamos (autoaceptados)
- Aceptación/rechazo de préstamos creados por el admin
- Confirmación/disputa de devoluciones registradas
- Visualización de multas con saldo pendiente (pagables solo de forma presencial)

## Estructura del proyecto

```
.
├── app/
│   ├── auth/              # JWT + bcrypt
│   ├── database/          # conexión psycopg
│   ├── routes/            # endpoints FastAPI
│   ├── services/          # lógica de negocio
│   ├── static/            # CSS + JS
│   ├── templates/         # vistas Jinja2
│   └── main.py
├── database/              # SQL inicial (schema, triggers, SPs, vistas, seed)
├── docker/                # configuración de contenedores y migraciones
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── run.bat                # atajos Windows
```

## Configuración

Variables principales (definidas en `docker-compose.yml`):

| Variable             | Default                              |
|----------------------|--------------------------------------|
| `DB_HOST`            | `postgres`                           |
| `DB_NAME`            | `prestamos_umb`                      |
| `JWT_SECRET_KEY`     | `PrestaUni_UMB_JWT_Secret_2026`      |
| `JWT_EXPIRATION_HOURS` | `8`                                |
| `TZ`                 | `America/Bogota`                     |

Para producción se recomienda mover `JWT_SECRET_KEY` y credenciales a un archivo
`.env` (excluido del repositorio).

## Capturas
*Por agregar*

## Licencia
Proyecto académico — Universidad Manuela Beltrán.
