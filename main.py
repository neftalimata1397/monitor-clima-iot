import time
import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
from w1thermsensor import W1ThermSensor
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import smtplib
from email.mime.text import MIMEText

# --- 1. CONFIGURACIÓN DE VARIABLES DE ENTORNO ---
url = os.getenv('INFLUX_URL')
token = os.getenv('INFLUX_TOKEN')
org = os.getenv('INFLUX_ORG')
bucket = os.getenv('INFLUX_BUCKET')
sucursal_id = os.getenv('SUCURSAL_ID', 'Sucursal_Test')

# Variables de Correo
EMAIL_USER = os.getenv('EMAIL_REMITENTE')
EMAIL_PASS = os.getenv('EMAIL_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_DESTINO')

# Configuración de Alertas
UMBRAL_TEMPERATURA = 26.0
TIEMPO_COOLDOWN_ALERTA = 1800  # 1800 segundos = 30 minutos (para no spammear)
ultimo_envio_alerta = 0

# --- 2. CONFIGURACIÓN DE PANTALLA OLED (I2C) ---
WIDTH = 128
HEIGHT = 64
oled = None
image = None
draw = None
font = None


def iniciar_pantalla():
    global oled, image, draw, font
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        oled = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=0x3C)
        oled.fill(0)
        oled.show()
        image = Image.new("1", (oled.width, oled.height))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        print("✅ Pantalla OLED iniciada")
        return True
    except Exception as e:
        print(f"⚠️ Sin Pantalla: {e}")
        return False


# --- 3. CONFIGURACIÓN DEL SENSOR DS18B20 ---
def leer_sensor():
    try:
        sensor = W1ThermSensor()
        return sensor.get_temperature()
    except Exception as e:
        print(f"❌ Error Sensor: {e}")
        return None


# --- 4. FUNCIÓN DE ALERTA DE CORREO ---
def enviar_alerta(temp_actual):
    global ultimo_envio_alerta
    ahora = time.time()

    # Si ya mandé correo hace menos de 30 mins, no hago nada
    if (ahora - ultimo_envio_alerta) < TIEMPO_COOLDOWN_ALERTA:
        return

    print("⚠️ ALERTA: Temperatura alta. Enviando correo...")
    try:
        asunto = f"ALERTA: Temperatura Alta en {sucursal_id}"
        cuerpo = f"ATENCION: La temperatura ha subido a {temp_actual:.1f}°C (Umbral: {UMBRAL_TEMPERATURA}°C).\nFavor de revisar el aire acondicionado."

        msg = MIMEText(cuerpo)
        msg['Subject'] = asunto
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_TO

        # Conectar a Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

        print("📧 Correo enviado exitosamente.")
        ultimo_envio_alerta = ahora  # Reiniciar cronómetro
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")


# --- 5. INICIALIZACIÓN ---
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)
tiene_pantalla = iniciar_pantalla()

print(f"🚀 Iniciando monitoreo en: {sucursal_id}")

# --- 6. BUCLE PRINCIPAL ---
while True:
    try:
        temperatura = leer_sensor()

        if temperatura is not None:
            # A) Checar Alertas
            if temperatura > UMBRAL_TEMPERATURA:
                enviar_alerta(temperatura)

            # B) Pantalla
            if tiene_pantalla:
                draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
                draw.text((0, 0), f"SUCURSAL: {sucursal_id[:9]}", font=font, fill=255)
                draw.text((0, 15), "TEMP ACTUAL:", font=font, fill=255)

                # Si está caliente, mostrar ALERTA en pantalla
                if temperatura > UMBRAL_TEMPERATURA:
                    draw.text((10, 30), f"{temperatura:.1f} C (ALERTA)", font=font, fill=255)
                else:
                    draw.text((10, 30), f"{temperatura:.1f} C", font=font, fill=255)

                oled.image(image)
                oled.show()

            # C) Enviar a Nube
            p = Point("clima_oficina").tag("ubicacion", sucursal_id).field("temperatura", temperatura)
            write_api.write(bucket=bucket, org=org, record=p)
            print(f"🌡️ {temperatura}°C -> Nube")

        else:
            if tiene_pantalla:
                draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
                draw.text((10, 30), "ERROR SENSOR", font=font, fill=255)
                oled.image(image)
                oled.show()

    except Exception as e:
        print(f"🔥 Error en loop: {e}")

    time.sleep(10)