import time
import threading
import os
import smtplib
import pytz
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smbus2
from RPLCD.i2c import CharLCD
from w1thermsensor import W1ThermSensor
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import ASYNCHRONOUS

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
# Variables para estadísticas diarias
temp_min = None
temp_max = None
suma_temps = 0.0
conteo_temps = 0
dia_registrado = None

# Configuración de Alertas y Tiempos
UMBRAL_TEMPERATURA = 26.0
TIEMPO_COOLDOWN_ALERTA = 1800
ultimo_envio_alerta = 0

INTERVALO_PANTALLA = 5
INTERVALO_NUBE = 60

ultimo_tiempo_lcd = 0
ultimo_tiempo_nube = 0
temp_actual = None

# Configuración de Zona Horaria y Traducción
ZONA_HORARIA = pytz.timezone('America/Monterrey')
DIAS_SEMANA = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miercoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sabado",
    "Sunday": "Domingo"
}

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


# --- 4. ALERTAS (FORMATO REPORTE VISUAL) ---
# --- 4. ALERTAS (CON THREADING) ---
def _enviar_correo_worker(temp, ahora_local):
    """Esta función corre en segundo plano para no bloquear el sistema"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🚨 ALERTA CRÍTICA: {sucursal_id}"
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_TO

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #eee; border-radius: 10px; overflow: hidden;">
                <div style="background-color: #d9534f; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">Alerta de Temperatura</h2>
                </div>
                <div style="padding: 20px; line-height: 1.6;">
                    <p>Se ha detectado una temperatura fuera de rango en:</p>
                    <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; text-align: center;">
                        <span style="font-size: 14px; color: #777;">TEMPERATURA ACTUAL</span><br>
                        <span style="font-size: 48px; font-weight: bold; color: #d9534f;">{temp:.1f}°C</span>
                    </div>
                    <table style="width: 100%; margin-top: 20px; border-collapse: collapse;">
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Sucursal:</strong></td><td>{sucursal_id}</td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Umbral:</strong></td><td>{UMBRAL_TEMPERATURA}°C</td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Hora:</strong></td><td>{ahora_local.strftime('%H:%M:%S')}</td></tr>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

        print("📧 Correo enviado con éxito (en segundo plano).")
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")

def enviar_alerta(temp):
    global ultimo_envio_alerta
    ahora = time.time()
    
    if (ahora - ultimo_envio_alerta) < TIEMPO_COOLDOWN_ALERTA:
        return

    # Actualizamos el tiempo de inmediato para evitar que el siguiente ciclo 
    # dispare otro hilo antes de que este termine.
    ultimo_envio_alerta = ahora 
    ahora_local = datetime.now(ZONA_HORARIA)
    
    print("⚠️ ALERTA: Iniciando hilo para enviar reporte ...")
    
    # Creamos e iniciamos el hilo en segundo plano
    hilo_alerta = threading.Thread(target=_enviar_correo_worker, args=(temp, ahora_local))
    hilo_alerta.start()


# --- 5. INICIALIZACIÓN ---
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=ASYNCHRONOUS)

tiene_pantalla = iniciar_lcd()
# Texto para el scroll de la pantalla
texto_sucursal = f"CR: {sucursal_id}"
necesita_scroll = len(texto_sucursal) > 20
if necesita_scroll:
    texto_sucursal += "   *** " 
posicion_scroll = 0
print(f"🚀 Sistema activo para: {sucursal_id}")

# --- 6. BUCLE PRINCIPAL ---
while True:
    ahora_unix = time.time()
    ahora_local = datetime.now(ZONA_HORARIA)

    try:
        # A) CADA 5 SEGUNDOS: SENSOR Y LCD
        if ahora_unix - ultimo_tiempo_lcd >= INTERVALO_PANTALLA:
            temp_actual = leer_sensor()

            if temp_actual is not None:
                # --- NUEVA LÓGICA DE ESTADÍSTICAS ---
                dia_actual = ahora_local.date()
                
                # Si es un día nuevo (o la primera vez que corre), reiniciamos contadores
                if dia_registrado != dia_actual:
                    temp_min = temp_actual
                    temp_max = temp_actual
                    suma_temps = 0.0
                    conteo_temps = 0
                    dia_registrado = dia_actual
                
                # Actualizamos mínimos, máximos y sumamos para el promedio
                if temp_actual < temp_min: temp_min = temp_actual
                if temp_actual > temp_max: temp_max = temp_actual
                
                suma_temps += temp_actual
                conteo_temps += 1
                temp_promedio = suma_temps / conteo_temps
                # ------------------------------------
                if temp_actual > UMBRAL_TEMPERATURA:
                    enviar_alerta(temp_actual)

                if tiene_pantalla and lcd:
                    try:
                        """lcd.clear()
                        lcd.cursor_pos = (0, 0)
                        lcd.write_string(f"SUC: {sucursal_id[:15]}")

                        lcd.cursor_pos = (1, 0)
                        lcd.write_string(f"TEMP: {temp_actual:.2f} C")

                        lcd.cursor_pos = (2, 0)
                        # Formato exacto de 20 caracteres: "M:xx.x X:xx.x P:xx.x"
                        stats = f"M:{temp_min:.1f} X:{temp_max:.1f} P:{temp_promedio:.1f}"
                        lcd.write_string(stats.ljust(20))

                        # Renglón 3: Viernes 15:12:59
                        dia_sem = DIAS_SEMANA.get(ahora_local.strftime('%A'), ahora_local.strftime('%A'))
                        hora_str = ahora_local.strftime('%H:%M:%S')
                        lcd.cursor_pos = (3, 0)
                        lcd.write_string(f"{dia_sem} {hora_str}")"""
                        lcd.cursor_pos = (0, 0)
                        #lcd.write_string(f"CR: {sucursal_id[:15]}".ljust(20))
                        if necesita_scroll:
                            texto_doble = texto_sucursal * 2
                            mostrar = texto_doble[posicion_scroll : posicion_scroll + 20]
                            posicion_scroll = (posicion_scroll + 1) % len(texto_sucursal)
                        else:
                            mostrar = texto_sucursal
                        lcd.write_string(mostrar.ljust(20))
                        #lcd.write_string(f"CR: {sucursal_id[:15]}".ljust(20))

                        lcd.cursor_pos = (1, 0)
                        lcd.write_string(f"TEMP: {temp_actual:.2f} C".ljust(20))

                        lcd.cursor_pos = (2, 0)
                        # Formato exacto de 20 caracteres: "M:xx.x X:xx.x P:xx.x"
                        stats = f"M:{temp_min:.1f} X:{temp_max:.1f} P:{temp_promedio:.1f}"
                        lcd.write_string(stats.ljust(20))

                        dia_sem = DIAS_SEMANA.get(ahora_local.strftime('%A'), ahora_local.strftime('%A'))
                        hora_str = ahora_local.strftime('%H:%M:%S')
                        lcd.cursor_pos = (3, 0)
                        lcd.write_string(f"{dia_sem} {hora_str}".ljust(20))
                    except:
                        iniciar_lcd()
            else:
                if tiene_pantalla:
                    lcd.clear()
                    lcd.write_string("ERROR DE SENSOR")

            ultimo_tiempo_lcd = ahora_unix

        # B) CADA 60 SEGUNDOS: INFLUXDB
        if ahora_unix - ultimo_tiempo_nube >= INTERVALO_NUBE:
            if temp_actual is not None:
                try:
                    p = Point("clima_oficina").tag("ubicacion", sucursal_id).field("temperatura", temp_actual)
                    write_api.write(bucket=bucket, org=org, record=p)
                    print(f"☁️ [{ahora_local.strftime('%H:%M:%S')}] Enviado a InfluxDB: {temp_actual}°C")
                    ultimo_tiempo_nube = ahora_unix
                except Exception as e:
                    print(f"❌ Error InfluxDB: {e}")
            else:
                ultimo_tiempo_nube = ahora_unix - 50  # Reintento pronto si no hubo lectura

    except Exception as e:
        print(f"🔥 Error: {e}")

    time.sleep(1)
