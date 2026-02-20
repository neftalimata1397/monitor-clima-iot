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

# --- NUEVOS INTERVALOS PARA VENTA (24/7) ---
INTERVALO_PANTALLA = 5  # Actualizar LCD y leer sensor cada 5 segundos
INTERVALO_NUBE = 60  # Enviar a InfluxDB cada 60 segundos

ultimo_tiempo_lcd = 0
ultimo_tiempo_nube = 0
temp_actual = None  # Almacena la última lectura para el envío a la nube

# --- 2. CONFIGURACIÓN PANTALLA LCD 20x4 ---
lcd = None


def iniciar_lcd():
    global lcd
    try:
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
def enviar_alerta(temp):
    global ultimo_envio_alerta
    ahora = time.time()
    if (ahora - ultimo_envio_alerta) < TIEMPO_COOLDOWN_ALERTA:
        return

    print("⚠️ ALERTA: Temperatura alta. Enviando correo...")
    try:
        msg = MIMEText(f"ATENCION: Temperatura crítica de {temp:.1f}°C en {sucursal_id}.\nFavor de revisar A/C.")
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
print(f"🚀 Sistema de monitoreo activo para: {sucursal_id}")

# --- 6. BUCLE PRINCIPAL (NON-BLOCKING) ---
while True:
    ahora = time.time()

    try:
        # A) TAREA CADA 5 SEGUNDOS: LEER SENSOR Y ACTUALIZAR LCD
        if ahora - ultimo_tiempo_lcd >= INTERVALO_PANTALLA:
            temp_actual = leer_sensor()

            if temp_actual is not None:
                # Checar Alertas
                if temp_actual > UMBRAL_TEMPERATURA:
                    enviar_alerta(temp_actual)

                # Actualizar Pantalla
                if tiene_pantalla and lcd:
                    try:
                        lcd.clear()
                        # Renglón 0
                        lcd.cursor_pos = (0, 0)
                        lcd.write_string(f"SUC: {sucursal_id[:15]}")
                        # Renglón 1
                        lcd.cursor_pos = (1, 0)
                        lcd.write_string(f"TEMP: {temp_actual:.2f} C")
                        # Renglón 2
                        lcd.cursor_pos = (2, 0)
                        estado = "ALERTA! 🔥" if temp_actual > UMBRAL_TEMPERATURA else "ESTADO: OK"
                        lcd.write_string(estado)
                        # Renglón 3 - Reloj para confirmar que el sistema no está congelado
                        lcd.cursor_pos = (3, 0)
                        lcd.write_string(f"ACTUALIZADO: {time.strftime('%H:%M:%S')}")
                    except:
                        iniciar_lcd()  # Intento de recuperación si se desconecta el bus I2C
            else:
                if tiene_pantalla:
                    lcd.clear()
                    lcd.write_string("ERROR DE SENSOR")

            ultimo_tiempo_lcd = ahora

        # B) TAREA CADA 60 SEGUNDOS: ENVIAR A INFLUXDB
        if ahora - ultimo_tiempo_nube >= INTERVALO_NUBE:
            if temp_actual is not None:
                try:
                    p = Point("clima_oficina").tag("ubicacion", sucursal_id).field("temperatura", temp_actual)
                    write_api.write(bucket=bucket, org=org, record=p)
                    print(f"☁️ [{time.strftime('%H:%M:%S')}] Dato enviado a InfluxDB: {temp_actual}°C")
                    ultimo_tiempo_nube = ahora
                except Exception as e:
                    print(f"❌ Error al conectar con InfluxDB: {e}")
            else:
                print("⚠️ No hay lectura válida para enviar a la nube.")
                # Reintentamos en 10 segundos si falló por falta de lectura
                ultimo_tiempo_nube = ahora - 50

    except Exception as e:
        print(f"🔥 Error crítico en loop: {e}")

    # Pausa ligera para no estresar la CPU (1 segundo es perfecto para precisión)
    time.sleep(1)