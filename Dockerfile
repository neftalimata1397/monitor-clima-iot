FROM python:3.9-slim

WORKDIR /app

# --- CORRECCIÓN PLAN B ---
# Ejecutamos update e install JUNTOS para que no se pierda la conexión entre pasos.
# Agregamos --fix-missing por si la red es inestable.
RUN apt-get update --fix-missing && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["python", "-u", "main.py"]