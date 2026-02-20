import time
import smbus2
from RPLCD.i2c import CharLCD
from w1thermsensor import W1ThermSensor
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import smtplib
from email.mime.text import MIMEText

# --- 1. CONFIGURACIÓN ---
# Variables de InfluxDB
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
TIEMPO_COOLDOWN_ALERTA = 1800  # 30 minutos
ultimo_envio_alerta = 0

# --- 2. CONFIGURACIÓN PANTALLA LCD 20x4 ---
lcd = None


def iniciar_lcd():
    global lcd
    try:
        # Dirección común: 0x27. Si no prende, intentar con 0x3F.
        lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1,
                      cols=20, rows=4, dotsize=8)
        lcd.clear()
        print("✅ Pantalla LCD 20x4 iniciada correctamente")
        return True
    except Exception as e:
        print(f"⚠️ No se detectó pantalla LCD: {e}")
        return False


# --- 3. SENSOR ---
def leer_sensor():
    try:
        sensor = W1ThermSensor()
        return sensor.get_temperature()
    except Exception as e:
        print(f"❌ Error leyendo sensor: {e}")
        return None


# --- 4. ALERTAS ---
def enviar_alerta(temp_actual):
    global ultimo_envio_alerta
    ahora = time.time()

    if (ahora - ultimo_envio_alerta) < TIEMPO_COOLDOWN_ALERTA:
        return

    print("⚠️ ALERTA: Temperatura alta. Enviando correo...")
    try:
        msg = MIMEText(f"ATENCION: Temperatura crítica de {temp_actual:.1f}°C en {sucursal_id}.\nFavor de revisar A/C.")
        msg['Subject'] = f"ALERTA TEMP: {sucursal_id}"
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_TO

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

        ultimo_envio_alerta = ahora
        print("📧 Correo enviado.")
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")


# --- 5. INICIALIZACIÓN ---
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

tiene_pantalla = iniciar_lcd()
print(f"🚀 Iniciando monitoreo en: {sucursal_id}")

# --- 6. BUCLE PRINCIPAL ---
while True:
    try:
        temperatura = leer_sensor()

        if temperatura is not None:
            # A) Checar Alertas
            if temperatura > UMBRAL_TEMPERATURA:
                enviar_alerta(temperatura)

            # B) Actualizar Pantalla LCD
            if tiene_pantalla and lcd:
                try:
                    # Limpiamos pantalla para evitar textos encimados
                    lcd.clear()

                    # Renglón 0: Nombre Sucursal
                    lcd.cursor_pos = (0, 0)
                    lcd.write_string(f"SUC: {sucursal_id[:15]}")

                    # Renglón 1: Temperatura
                    lcd.cursor_pos = (1, 0)
                    lcd.write_string(f"TEMP: {temperatura:.2f} C")

                    # Renglón 2: Estado Visual
                    lcd.cursor_pos = (2, 0)
                    if temperatura > UMBRAL_TEMPERATURA:
                        lcd.write_string("ESTADO: ALERTA! 🔥")
                    else:
                        lcd.write_string("ESTADO: NORMAL OK")

                    # Renglón 3: Indicador de envío
                    lcd.cursor_pos = (3, 0)
                    lcd.write_string("Monitoreo Activo...")
                except Exception as e:
                    print(f"Error escribiendo en LCD: {e}")
                    # Intentar reconectar si falla
                    try:
                        iniciar_lcd()
                    except:
                        pass

            # C) Enviar a Nube
            p = Point("clima_oficina").tag("ubicacion", sucursal_id).field("temperatura", temperatura)
            write_api.write(bucket=bucket, org=org, record=p)
            print(f"🌡️ {temperatura}°C enviado.")

        else:
            if tiene_pantalla and lcd:
                lcd.clear()
                lcd.write_string("ERROR DE SENSOR")

    except Exception as e:
        print(f"🔥 Error en loop principal: {e}")

    # Esperar 10 segundos
    time.sleep(10)