# Imagen del servicio de sincronización PostgreSQL → SQL Server
FROM python:3.12-slim

# Dependencias del sistema necesarias para pymssql (FreeTDS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    freetds-dev \
    freetds-bin \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync_service.py .

CMD ["python", "-u", "sync_service.py"]
