# -*- coding: utf-8 -*-
import sys
from machine import Pin, WDT, ADC
import machine
import time
import xbee

# --- Configuración ---
TARGET_NODE_ID = "XBEE_COOR"
COORDINATOR_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8B\x99'

# CAMARA
CAMERA_DEVICE_NODE_ID = "XBEE_CAM" # Reemplaza con el NI del dispositivo cámara
CAMERA_DEVICE_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8A\xAC' # Reemplaza con la dirección del dispositivo cámara

DEVICE_ID = "XBEE_X"
DEVICE_ID_NI = "NONE"


# Periodos de tiempo (en milisegundos)
SLEEP_DURATION_MS = 100                     # Tiempo de espera en modo sleep       
RETRY_DELAY_MS = 1000                        # Tiempo de espera entre reintentos de envio
HEARING_INTERVAL_MS = 2000                  # Tiempo escuchando ACK tras envio  
WATCHDOG_TIMEOUT_MS = 120000                # Tiempo de timeout del watchdog
STATE_ERROR_SLEEP_MS = 5000                 # Segundos en estado de error
DEBOUNCE_TIME_MS = 30000                    # Tiempo de debounce para notificaciones del sensor
CHECK_SENSOR_INTERVAL_MS = 1000             # Intervalo para comprobar el estado del sensor una vez activado

# --- Pines ---
pin_sensor_1 = Pin('D0', Pin.IN, Pin.PULL_UP)
pin_sensor_2 = Pin('D2', Pin.IN, Pin.PULL_UP)
pin_sensor_3 = Pin('D3', Pin.IN, Pin.PULL_UP)
pin_sensor_4 = Pin('D4', Pin.IN, Pin.PULL_UP)
pin_sensor_5 = Pin('D8', Pin.IN, Pin.PULL_UP)
adc_battery = ADC('D1')
pin_camera = Pin('D12', Pin.OUT, value=0)

# ADC reference voltage
AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

# --- Estados del Dispositivo ---
STATE_STARTUP = 0
STATE_SLEEP = 1
STATE_REPORT_BATTERY = 2
STATE_SENSOR_ACTIVE = 3
STATE_SENSOR_TRIGGERED = 4
STATE_ERROR = 5

# --- Variables Globales ---
device_state = STATE_STARTUP
camera_on_time = 0
xb = None 
dog = None
pin_sensor_general = False
last_sensor_notification_time = 0
contador_fallo_comunicacion = 0                        # Indica las veces que se ha activado el sensor y no ha podido notificar    

# --- Funciones Auxiliares ---
def get_battery_status(as_string=True):
    """
    Lee el voltaje de la batería.
    Si as_string es True, devuelve un texto formateado.
    Si as_string es False, devuelve solo el valor numérico del voltaje.
    """
    try:
        
        # Obtener el voltaje de referencia configurado en el módulo.
        try:
            av = xbee.atcmd("AV")
        except KeyError:
            av = None # Por defecto para algunos módulos como el Cellular.
        reference_v = AV_VALUES[av]

        # Leer el valor crudo del ADC (0-4095).
        adc_raw_value = adc_battery.read()
        
        # Calcular el voltaje en el pin.
        pin_voltage = (adc_raw_value / 4095.0) * reference_v
        
        # Aplicar el factor de escala del divisor de voltaje (12V / 3.3V).
        battery_voltage = pin_voltage * (12.0 / 3.3) * 2.9 # Factor de corrección para divisor 12k+3.3k
        
        if as_string:
            # Formatear el resultado a dos decimales.
            return "Bateria: {:.2f}V".format(battery_voltage)
        else:
            return battery_voltage
    except Exception as e:
        print("Error al leer la bateria: {}".format(e))
        return "Bateria: ERROR" if as_string else 0.0

def safe_send(target_addr, message, retries=3):
    """
    Envía un mensaje y no espera confirmación.
    Reintenta hasta 'retries' veces si hay error en el envío.
    """
    global dog,xb,DEVICE_ID_NI
    for attempt in range(retries):
        try:
            print("Enviando sin ack (intento {}/{}) '{}'".format(attempt + 1, retries, message))
            xbee.transmit(target_addr, message)
            dog.feed()
            time.sleep_ms(100)
            return True
        except Exception as e:
            dog.feed()
            print("Error al transmitir/recibir: {}".format(e))
            if attempt < retries - 1:
                print("Reintentando en {} segundos...".format(RETRY_DELAY_MS / 1000))
                time.sleep_ms(RETRY_DELAY_MS)
            else:
                print("Fallo al enviar mensaje tras varios reintentos.")
                return False
    print("Mensaje enviado correctamente.")
    return True

def safe_send_and_wait_ack(target_addr, message, retries=3):
    """
    Envía un mensaje y espera un ACK del destinatario.
    Reintenta hasta 'retries' veces si no recibe confirmación.
    """
    global dog,xb,DEVICE_ID_NI
    respuesta_recibida = False
    for attempt in range(retries):
        try:
            print("Enviando con ACK (intento {}/{}) '{}'".format(attempt + 1, retries, message))
            xbee.transmit(target_addr, message)

            # Esperar feedback
            start_wait = time.ticks_ms()
            
            while time.ticks_diff(time.ticks_ms(), start_wait) < (HEARING_INTERVAL_MS):
                dog.feed()
                received_msg = xbee.receive()
                if received_msg and received_msg['sender_eui64'] == target_addr:
                    payload = received_msg['payload'].decode('utf-8')
                    print("Recibido: '{}'".format(payload))
                    respuesta_recibida = True
                    return True
                time.sleep_ms(100)
            if not respuesta_recibida:
                print("No se recibió confirmacion en el tiempo esperado.")

        except Exception as e:
            dog.feed()
            print("Error al transmitir/recibir: {}".format(e))

        if attempt < retries - 1:
            dog.feed()
            print("Reintentando en {} segundos...".format(RETRY_DELAY_MS / 1000))
            time.sleep_ms(RETRY_DELAY_MS)

    print("Fallo al enviar y confirmar mensaje tras varios reintentos.")
    return False

def check_pins_sensor():
    global pin_sensor_general
    if ( pin_sensor_5.value() != 0):
        pin_sensor_general = True
        
    else:
        pin_sensor_general = False

def send_report():
    """
    Envía un reporte de estado al coordinador.
    """
    global contador_fallo_comunicacion, DEVICE_ID_NI
    try:
        battery_voltage = get_battery_status(as_string=False)
        status_data = "Contador={}, Sensor={}".format(
            contador_fallo_comunicacion,
            "ON" if pin_sensor_general else "OFF"
            )
        message = "{}:{:.2f}:{}".format(DEVICE_ID_NI, battery_voltage, status_data)
        if safe_send_and_wait_ack(COORDINATOR_64BIT_ADDR, message):
            print("Reporte enviado correctamente.")
            contador = 0  # Resetear el contador tras un envío exitoso
        else:
            print("Fallo al enviar el reporte.")
            contador += 1  # Incrementar el contador de fallos
    except Exception as e:
        print("Error al enviar reporte: {}".format(e))

def check_and_process_incoming_messages():
    """
    Procesa los mensajes entrantes y responde cuando sea necesario.
    """
    global device_state, camera_on_time
    
    received_msg = xbee.receive()
    if not received_msg:
        return False

    payload = received_msg['payload'].decode('utf-8').strip()
    sender = received_msg['sender_eui64']
    
    print("Mensaje recibido: '{}' de {}".format(payload, [hex(b) for b in sender]))
    
    if payload == "REPORT":
        print("Solicitud de reporte recibida, enviando respuesta...")
        battery_voltage = get_battery_status(as_string=False)
        status_data = "Contador={}, Sensor={}".format(
            contador,
            "ON" if pin_sensor_general else "OFF"
            )
        response = "{}:{:.2f}:{}".format(DEVICE_ID_NI, battery_voltage, status_data)
        safe_send(sender, response)
        return True

    return False

# --- Lógica Principal (Máquina de Estados) ---
def main():
    global device_state, camera_on_time, xb, dog, DEVICE_ID_NI, pin_sensor_general, last_sensor_notification_time, contador

    # Inicialización del Watchdog y XBee
    try:
        dog = WDT(timeout=WATCHDOG_TIMEOUT_MS)
        dog.feed()
        xb = xbee.XBee()
        
        print("XBee y Watchdog inicializados.")
        print("XBee NI: {}".format(xbee.atcmd('NI')))
        print("Perfil: SENSOR REMOTO")
        DEVICE_ID_NI = xbee.atcmd('NI') or DEVICE_ID
        time.sleep_ms(5000) # Esperar para estabilizar
    except Exception as e:
        print("Error critico en inicializacion: {}".format(e))
        device_state = STATE_ERROR
    
    while True:
        
        dog.feed()
        
        try:

            # --- Máquina de Estados ---
            if device_state == STATE_STARTUP:
                print("--- Estado: STARTUP ---")
                battery_voltage = get_battery_status(as_string=False)
                message = "{}:{:.2f}:Dispositivo iniciado.".format(DEVICE_ID_NI, battery_voltage)
                if safe_send_and_wait_ack(COORDINATOR_64BIT_ADDR, message):
                    device_state = STATE_SLEEP
                else:
                    print("No se pudo contactar al coordinador en el arranque.")
                    device_state = STATE_ERROR

            elif device_state == STATE_SLEEP:
                print("--- Estado: SLEEP ---")
                while(True):
                    dog.feed()
                    # Comprobar mensajes entrantes
                    incoming_msg = xbee.receive()
                    if incoming_msg:
                        check_and_process_incoming_messages(incoming_msg)
                        break

                    # Comprobar si el sensor está activado
                    check_pins_sensor()
                    if pin_sensor_general:
                        print("Sensor activado, cambiando a estado SENSOR_TRIGGERED")
                        device_state = STATE_SENSOR_TRIGGERED
                        break
                    time.sleep_ms(SLEEP_DURATION_MS)
            
            elif device_state == STATE_SENSOR_TRIGGERED:
                print("--- Estado: SENSOR_TRIGGERED ---")
                check_pins_sensor()
                if pin_sensor_general == 1:
                    current_time = time.ticks_ms()
                    # Comprobar si ha pasado suficiente tiempo desde la última notificación para no saturar la red a mensajes
                    if time.ticks_diff(current_time, last_sensor_notification_time) >= DEBOUNCE_TIME_MS: 
                        command_to_send = "SENSOR:ON"
                        print("Enviando notificación de sensor activado")
                        if safe_send_and_wait_ack(CAMERA_DEVICE_64BIT_ADDR, command_to_send):
                            last_sensor_notification_time = current_time
                        else:
                            contador_fallo_comunicacion += 1
                            print("Fallo al notificar al dispositivo cámara. Contador de fallos: {}".format(contador_fallo_comunicacion))

                    else:
                        print("Esperando para reenviar notificación de sensor: {} segundos restantes".format(
                            (DEBOUNCE_TIME_MS - time.ticks_diff(current_time, last_sensor_notification_time)) // 1000))
                    
                    time.sleep_ms(CHECK_SENSOR_INTERVAL_MS)  # Esperar antes de verificar de nuevo
                    
                else:
                    # El sensor ya no está activado, volver a dormir
                    print("Sensor ya no activado, volviendo a modo SLEEP")
                    device_state = STATE_SLEEP

            elif device_state == STATE_ERROR:
                print("--- Estado: ERROR ---")
                print("Intentando reconectar en {} segundos...".format(STATE_ERROR_SLEEP_MS // 1000))
                time.sleep_ms(STATE_ERROR_SLEEP_MS)
                device_state = STATE_STARTUP 
                
        except Exception as e:
            print("Error inesperado en el bucle principal: {}".format(e))
            # Un error grave, se pone el dispositivo en estado de ERROR
            device_state = STATE_ERROR
            time.sleep_ms(10000) # Esperar antes de reintentar

if __name__ == '__main__':
    main()