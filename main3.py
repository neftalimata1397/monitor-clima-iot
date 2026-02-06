import os
import time
import board
import adafruit_dht
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- CONFIGURACIÓN ---
INFLUX_URL = os.getenv('INFLUX_URL')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN')
INFLUX_ORG = os.getenv('INFLUX_ORG')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')
SUCURSAL_ID = os.getenv('SUCURSAL_ID', 'Raspberry_Sin_Nombre')

# --- CONFIGURACIÓN SENSOR (GPIO 4) ---
# Intentamos inicializar el sensor. Si falla, es porque no está conectado.
try:
    sensor = adafruit_dht.DHT22(board.D4)
    print(f"[INIT] Sensor DHT22 detectado en GPIO 4. Iniciando: {SUCURSAL_ID}")
except Exception as e:
    print(f"Error fatal inicializando sensor: {e}")
    sensor = None

# --- CLIENTE INFLUXDB ---
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

print("--- Iniciando Monitoreo Real ---")

while True:
    try:
        # Intentar leer sensor
        temp = sensor.temperature
        hum = sensor.humidity

        # Validar lectura (a veces el sensor da 'None' si falla la lectura)
        if temp is None or hum is None:
            print("Lectura fallida... reintentando")
            time.sleep(2)
            continue

        # Crear el punto de datos
        p = Point("clima_site") \
            .tag("sucursal", SUCURSAL_ID) \
            .field("temperatura", temp) \
            .field("humedad", hum)

        # Enviar a la nube
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)
        print(f"[{SUCURSAL_ID}] T: {temp:.1f}°C | H: {hum:.1f}% -> Enviado a InfluxDB")

    except RuntimeError as error:
        # Errores comunes de lectura del sensor (es normal que pase a veces)
        print(f"Error de lectura (reintentando): {error.args[0]}")
        time.sleep(2.0)
        continue
    except Exception as error:
        print(f"Error general: {error}")
        sensor.exit()
        raise error

    # Esperar 10 segundos antes de la siguiente lectura
    time.sleep(10)