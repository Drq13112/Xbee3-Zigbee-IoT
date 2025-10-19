# -*- coding: utf-8 -*-
import sys
from machine import Pin, WDT, ADC
import machine
import time
import xbee

# --- Configuración ---
# Objetivo para reportes periódicos y de estado
COORDINATOR_NODE_ID = "XBEE_COOR"
COORDINATOR_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8B\x99'

DEVICE_ID = "XBEE_CAM"
DEVICE_ID_NI = "NONE"

# Periodos de tiempo (en milisegundos)
SLEEP_DURATION_MS = 100                     # Tiempo de espera en modo sleep       
RETRY_DELAY_MS = 1000                        # Tiempo de espera entre reintentos de envio
HEARING_INTERVAL_MS = 2000                  # Tiempo escuchando ACK tras envio  
WATCHDOG_TIMEOUT_MS = 120000                # Tiempo de timeout del watchdog
STATE_ERROR_SLEEP_MS = 5000                 # Segundos en estado de error
DEBOUNCE_TIME_MS = 30000                    # Tiempo de debounce para notificaciones del sensor
CHECK_SENSOR_INTERVAL_MS = 1000             # Intervalo para comprobar el estado del sensor una vez activado
CAMERA_ON_DURATION_MS = 60000               # Duración en ms que la cámara permanece encendida tras activación por sensor

# --- Pines ---
pin_sensor_1 = Pin('D0', Pin.IN, Pin.PULL_UP)
pin_sensor_2 = Pin('D2', Pin.IN, Pin.PULL_UP)
pin_sensor_3 = Pin('D3', Pin.IN, Pin.PULL_UP)
pin_sensor_4 = Pin('D4', Pin.IN, Pin.PULL_UP)
adc_battery = ADC('D1')
pin_camera = Pin('D12', Pin.OUT, value=0)

# ADC reference voltage
AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

# --- Estados del Dispositivo ---
STATE_STARTUP = 0
STATE_SLEEP = 1
STATE_REPORT_BATTERY = 2
STATE_SENSOR_TRIGGERED = 3
STATE_ERROR = 4

# --- Variables Globales ---
device_state = STATE_STARTUP
camera_on_time = 0
xb = None 
dog = None
manual_camera = False # Flag para anular el temporizador de la cámara
report_time = 0
contador_fallo_comunicacion = 0

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

def check_and_process_incoming_messages():
    """
    Revisa si hay mensajes entrantes y los procesa.
    Devuelve True si se procesó un comando, False en caso contrario.
    """
    global device_state, camera_on_time, manual_camera
    
    received_msg = xbee.receive()
    if not received_msg:
        return False

    sender_addr = received_msg['sender_eui64']
    payload_str = received_msg['payload'].decode('utf-8')
    print("Mensaje recibido de {}: '{}'".format(sender_addr, payload_str))

    # Comandos esperados: "TEL:ON", "TEL:OFF", "REPORT", "SENSOR:ON"

    command = payload_str
    response_message = "{}:OK".format(command)
    
    if command == "TEL:ON":
        print("Comando ON recibido. Encendiendo cámara indefinidamente.")
        pin_camera.value(1)
        manual_camera = True # Anula el temporizador
        device_state = STATE_SLEEP
        safe_send(sender_addr, response_message)
        return True

    elif command == "TEL:OFF":
        print("Comando OFF recibido. Apagando cámara.")
        pin_camera.value(0)
        manual_camera = False
        device_state = STATE_SLEEP 
        safe_send(sender_addr, response_message)
        return True

    elif command == "REPORT":
        print("Comando REPORT recibido.")
        battery_status = get_battery_status(as_string=True)
        report = "Estado: {}, Camara: {}, {}, Manual: {}".format(device_state, "ON" if pin_camera.value() else "OFF", battery_status, manual_camera)
        safe_send(sender_addr, "{}: {}".format(DEVICE_ID_NI, report))
        device_state = STATE_SLEEP
        return True
        
    elif command == "SENSOR:ON":
        print("Comando SENSOR:ON recibido. Encendiendo cámara por temporizador.")
        pin_camera.value(1)
        camera_on_time = time.ticks_ms()
        device_state = STATE_SLEEP
        safe_send(sender_addr, response_message)
        return True
    
    else:
        response_message = "UNKNOWN COMMAND RECEIVED"
        safe_send(sender_addr, response_message)
        
    return False

def check_sensor_pins():
    """Devuelve True si algún sensor está activado, False si no."""
    return (pin_sensor_1.value() == 0 or pin_sensor_2.value() == 0 or
            pin_sensor_3.value() == 0 or pin_sensor_4.value() == 0)
        
# --- Lógica Principal (Máquina de Estados) ---
def main():
    global device_state, camera_on_time, xb, dog, DEVICE_ID_NI, manual_camera, contador_fallo_comunicacion

    try:
        dog = WDT(timeout=WATCHDOG_TIMEOUT_MS)
        dog.feed()
        xb = xbee.XBee()
        print("XBee y Watchdog inicializados.")
        print("XBee NI: {}".format(xbee.atcmd('NI')))
        print( "Perfil: CAMARA")
        DEVICE_ID_NI = xbee.atcmd('NI') or DEVICE_IDtime.sleep_ms(5000) # Esperar para estabilizar
    except Exception as e:
        print("Error critico en inicializacion: {}".format(e))
        while True:
            time.sleep(5)

    while True:
        dog.feed()

        try:

            # --- Procesar mensajes entrantes (tiene prioridad) ---
            if check_and_process_incoming_messages():
                continue # Si se procesó un comando, reiniciar el bucle

            # --- Máquina de Estados ---
            if device_state == STATE_STARTUP:
                print("--- Estado: STARTUP ---")
                battery_voltage = get_battery_status(as_string=False)
                # Formato ID_NODO:BATERIA:DATOS
                message = "{}:{:.2f}:Dispositivo iniciado".format(DEVICE_ID_NI, battery_voltage)
                if safe_send_and_wait_ack(COORDINATOR_64BIT_ADDR, message):
                    device_state = STATE_SLEEP
                else:
                    device_state = STATE_ERROR

            elif device_state == STATE_SLEEP:
                print("--- Estado: SLEEP ---")
                idle_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), idle_start) < SLEEP_DURATION_MS:
                    dog.feed()
                    if check_and_process_incoming_messages():
                        time.sleep_ms(100)
                        break
                    if pin_camera.value() == 1 and not manual_camera:
                        print("Tiempo restante para apagado: {} segundos.".format((CAMERA_ON_DURATION_MS - time.ticks_diff(time.ticks_ms(), camera_on_time)) // 1000))
                    # --- Gestión de la cámara (se apaga por temporizador solo si no es manual) ---
                    if pin_camera.value() == 1 and not manual_camera and time.ticks_diff(time.ticks_ms(), camera_on_time) > CAMERA_ON_DURATION_MS:
                        pin_camera.value(0)
                        print("Cámara apagada por temporizador.")
                        device_state = STATE_SLEEP
                        time.sleep_ms(50)
                

            elif device_state == STATE_SENSOR_TRIGGERED:
                print("--- Estado: SENSOR_TRIGGERED ---")
                pin_camera.value(1)
                camera_on_time = time.ticks_ms()
                device_state = STATE_SLEEP

            elif device_state == STATE_ERROR:
                print("--- Estado: ERROR ---")
                print("Intentando reiniciar en {} segundos...".format(STATE_ERROR_SLEEP_MS / 1000))
                time.sleep_ms(STATE_ERROR_SLEEP_MS)
                device_state = STATE_STARTUP

        except Exception as e:
            print("Error inesperado en el bucle principal: {}".format(e))
            device_state = STATE_ERROR
            time.sleep(10)

if __name__ == '__main__':
    main()