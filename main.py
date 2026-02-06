import time
import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
from w1thermsensor import W1ThermSensor
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os

# --- 1. CONFIGURACIÓN DE VARIABLES DE ENTORNO ---
url = os.getenv('INFLUX_URL')
token = os.getenv('INFLUX_TOKEN')
org = os.getenv('INFLUX_ORG')
bucket = os.getenv('INFLUX_BUCKET')
sucursal_id = os.getenv('SUCURSAL_ID', 'Sucursal_Test')

# --- 2. CONFIGURACIÓN DE PANTALLA OLED (I2C) ---
# Definir tamaño de pantalla (128x64 es el estándar de tu modelo)
WIDTH = 128
HEIGHT = 64
oled = None
image = None
draw = None
font = None


def iniciar_pantalla():
    global oled, image, draw, font
    try:
        # Crear interfaz I2C
        i2c = busio.I2C(board.SCL, board.SDA)
        # Crear clase de pantalla
        oled = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=0x3C)

        # Limpiar pantalla
        oled.fill(0)
        oled.show()

        # Crear imagen en blanco para dibujar (Modo '1' es 1-bit color)
        image = Image.new("1", (oled.width, oled.height))
        draw = ImageDraw.Draw(image)

        # Cargar fuente por defecto
        font = ImageFont.load_default()
        print("✅ Pantalla OLED iniciada correctamente")
        return True
    except Exception as e:
        print(f"⚠️ Advertencia: No se detectó pantalla OLED ({e})")
        return False


# --- 3. CONFIGURACIÓN DEL SENSOR DS18B20 ---
def leer_sensor():
    try:
        sensor = W1ThermSensor()
        temp_c = sensor.get_temperature()
        return temp_c
    except Exception as e:
        print(f"❌ Error leyendo sensor: {e}")
        return None


# --- 4. INICIALIZACIÓN ---
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

# Intentar iniciar pantalla al arrancar
tiene_pantalla = iniciar_pantalla()

print(f"🚀 Iniciando monitoreo en: {sucursal_id}")

# --- 5. BUCLE PRINCIPAL ---
while True:
    try:
        # A) Leer Temperatura
        temperatura = leer_sensor()

        if temperatura is not None:
            # B) Mostrar en Pantalla (Si existe)
            if tiene_pantalla:
                # Borrar lienzo (rectángulo negro)
                draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)

                # Dibujar textos
                draw.text((0, 0), f"SUCURSAL:", font=font, fill=255)
                draw.text((60, 0), sucursal_id[:10], font=font, fill=255)

                # Temperatura en grande (simulado)
                draw.text((0, 20), "TEMP ACTUAL:", font=font, fill=255)
                draw.text((10, 35), f"{temperatura:.2f} C", font=font, fill=255)

                # Estado
                draw.text((0, 55), "Estado: ENVIANDO...", font=font, fill=255)

                # Actualizar hardware
                oled.image(image)
                oled.show()

            # C) Enviar a InfluxDB
            p = Point("clima_oficina") \
                .tag("ubicacion", sucursal_id) \
                .field("temperatura", temperatura)

            write_api.write(bucket=bucket, org=org, record=p)
            print(f"🌡️ {temperatura}°C enviado a la nube.")

        else:
            print("⚠️ Sensor desconectado o fallando.")
            if tiene_pantalla:
                draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
                draw.text((10, 25), "ERROR SENSOR", font=font, fill=255)
                oled.image(image)
                oled.show()

    except Exception as e:
        print(f"🔥 Error crítico en el loop: {e}")

    # Esperar 10 segundos antes de la siguiente lectura
    time.sleep(10)