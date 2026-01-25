import os
import time
import random
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- CONFIGURACIÓN ---
INFLUX_URL = os.getenv('INFLUX_URL')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN')
INFLUX_ORG = os.getenv('INFLUX_ORG')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')
SUCURSAL_ID = os.getenv('SUCURSAL_ID', 'Desconocido')
SENSOR_PIN_NUM = int(os.getenv('SENSOR_PIN', '4'))

# --- SENSOR: MODO REAL VS SIMULADO ---
sensor = None
is_simulated = False

try:
    # Intenta cargar librerías de hardware (Solo existen en Raspberry)
    import board
    import adafruit_dht

    # Mapeo de pines (GPIO 4 -> D4)
    if SENSOR_PIN_NUM == 4:
        sensor = adafruit_dht.DHT22(board.D4)
        print(f"[INIT] Hardware DHT22 detectado en GPIO {SENSOR_PIN_NUM}")
    else:
        # Puedes agregar mas pines aquí si usas otro
        sensor = adafruit_dht.DHT22(board.D4)

except Exception as e:
    print(f"[WARN] No se detectó hardware ({e}). Usando MODO SIMULACIÓN.")
    is_simulated = True

# --- CONEXIÓN INFLUXDB ---
client = None
write_api = None

try:
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    print("[INIT] Conexión a Nube configurada.")
except Exception as e:
    print(f"[ERROR] InfluxDB: {e}")

# --- BUCLE PRINCIPAL ---
print(f"--- Iniciando Monitor: {SUCURSAL_ID} ---")

while True:
    try:
        temp = 0.0
        hum = 0.0

        if is_simulated:
            # Generar datos falsos
            temp = round(random.uniform(20.0, 30.0), 1)
            hum = round(random.uniform(40.0, 60.0), 1)
        else:
            # Leer sensor real
            try:
                temp = sensor.temperature
                hum = sensor.humidity
                if temp is None or hum is None:
                    raise RuntimeError("Lectura Nula")
            except RuntimeError as error:
                print(f"[SENSOR] Reintentando... ({error.args[0]})")
                time.sleep(2.0)
                continue

        # Log Local
        print(f"[{SUCURSAL_ID}] T: {temp}°C | H: {hum}%")

        # Enviar a Nube
        if write_api:
            p = Point("clima_site") \
                .tag("sucursal", SUCURSAL_ID) \
                .field("temperatura", temp) \
                .field("humedad", hum)
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)
            print(" -> Enviado OK")

    except Exception as e:
        print(f"[ERROR] {e}")
        if not is_simulated:
            time.sleep(1)

    time.sleep(10)  # Envia cada 10 segundos