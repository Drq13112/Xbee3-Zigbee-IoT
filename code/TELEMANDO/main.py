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

# Objetivo para los comandos ON/OFF
CAMERA_DEVICE_NODE_ID = "XBEE_CAM" # Reemplaza con el NI del dispositivo cámara
CAMERA_DEVICE_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8A\xAC' # Reemplaza con la dirección del dispositivo cámara

DEVICE_ID = "XBEE_TELEMANDO"
DEVICE_ID_NI = "NONE"

# Periodos de tiempo (en milisegundos)
SLEEP_DURATION_MS = 100                     # Tiempo de espera en modo sleep       
RETRY_DELAY_MS = 100                        # Tiempo de espera entre reintentos de envio
HEARING_INTERVAL_MS = 3000                  # Tiempo escuchando ACK tras envio
WATCHDOG_TIMEOUT_MS = 120000                # Tiempo de timeout del watchdog
STATE_ERROR_SLEEP_MS = 5000                 # Segundos en estado de error
DEBOUNCE_BOTTON_TIME_MS = 4000              # Tiempo para resetear último comando tras inactividad
DEBOUNCE_SENSOR_TIME_MS = 30000             # Tiempo de debounce para notificaciones del sensor
CHECK_SENSOR_INTERVAL_MS = 1000             # Intervalo para comprobar el estado del sensor una vez activado
CAMERA_ON_DURATION_MS = 60000               # Duración en ms que la cámara permanece encendida tras activación por sensor


# --- Pines ---
pin_sensor_1 = Pin('D0', Pin.IN, Pin.PULL_UP)   # Sensor digital (no usado en telemando)
pin_report_req = Pin('D2', Pin.IN, Pin.PULL_UP) # Solicitar reporte
pin_cmd_on = Pin('D3', Pin.IN, Pin.PULL_UP)     # Comando ON
pin_cmd_off = Pin('D4', Pin.IN, Pin.PULL_UP)    # Comando OFF
adc_battery = ADC('D1')                         # Lectura de batería

# ADC reference voltage
AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

# --- Estados del Dispositivo ---
STATE_STARTUP = 0
STATE_SLEEP = 1
STATE_REPORT_BATTERY = 2
STATE_SEND_COMMAND = 3
STATE_ERROR = 4

# --- Variables Globales ---
device_state = STATE_STARTUP
xb = None 
dog = None
last_press_time = 0
command_to_send = ""
last_command = 0
contador_sensor = 0

# --- Funciones Auxiliares ---
def get_battery_status(as_string=True):
    """
    Lee el voltaje de la batería.
    Si as_string es True, devuelve un texto formateado.
    Si as_string es False, devuelve solo el valor numérico del voltaje.
    """
    try:
        try:
            av = xbee.atcmd("AV")
        except KeyError:
            av = None
        reference_v = AV_VALUES[av]
        adc_raw_value = adc_battery.read()
        pin_voltage = (adc_raw_value / 4095.0) * reference_v
        battery_voltage = pin_voltage * (12.0 / 3.3) * 2.9 # Factor de corrección para divisor 12k+3.3k
        
        if as_string:
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
    Procesa los mensajes entrantes y responde cuando sea necesario.
    """
    global device_state, contador_sensor
    
    received_msg = xbee.receive()
    if not received_msg:
        return False

    payload = received_msg['payload'].decode('utf-8').strip()
    sender = received_msg['sender_eui64']
    
    print("Mensaje recibido: '{}' de {}".format(payload, [hex(b) for b in sender]))
    
    if payload == "REPORT":
        print("Solicitud de reporte recibida, enviando respuesta...")
        battery_voltage = get_battery_status(as_string=False)
        status_data = "Contador={}".format(
            contador_sensor
            )
        response = "{}:{:.2f}:{}".format(DEVICE_ID_NI, battery_voltage, status_data)
        safe_send(sender, response)
        return True

    return False

# --- Lógica Principal (Máquina de Estados) ---
def main():
    global device_state, xb, dog, DEVICE_ID_NI, last_press_time, command_to_send, last_command, contador_sensor

    try:
        dog = WDT(timeout=WATCHDOG_TIMEOUT_MS)
        dog.feed()
        xb = xbee.XBee()
        print("XBee y Watchdog inicializados.")
        print("XBee NI: {}".format(xbee.atcmd('NI')))
        print( "Perfil: TELEMANDO")
        DEVICE_ID_NI = xbee.atcmd('NI') or DEVICE_ID
        time.sleep_ms(5000) # Esperar para estabilizar
    except Exception as e:
        print("Error critico en inicializacion: {}".format(e))
        while True:
            time.sleep(5)

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
                print("--- Estado: SLEEP --- (Esperando comandos)")
                
                while (True):
                    dog.feed()
                    
                    current_time = time.ticks_ms()
                    if time.ticks_diff(current_time, last_press_time) > DEBOUNCE_BOTTON_TIME_MS:
                        last_command = 0 

                    # Comprobar si ha pasado el tiempo de debounce
                    if time.ticks_diff(current_time, last_press_time) > 1000:
                        if pin_cmd_on.value() == 0 and last_command != 1:
                            print("Boton ON presionado.")
                            command_to_send = "TEL:ON"
                            device_state = STATE_SEND_COMMAND
                            last_command = 1
                            break
                        elif pin_cmd_off.value() == 0 and last_command != 2:
                            print("Boton OFF presionado.")
                            command_to_send = "TEL:OFF"
                            device_state = STATE_SEND_COMMAND
                            last_command = 2
                            break
                        elif pin_report_req.value() == 0 and last_command != 3:
                            print("Boton REPORTE presionado.")
                            command_to_send = "REPORT"
                            device_state = STATE_SEND_COMMAND
                            last_command = 3
                            break
                        
                    if check_and_process_incoming_messages():
                        continue # Si se procesó un comando, reiniciar el bucle

                    time.sleep_ms(SLEEP_DURATION_MS) # Pequeña pausa para no saturar CPU

            elif device_state == STATE_SEND_COMMAND:
                print("--- Estado: SEND_COMMAND ---")
                last_press_time = time.ticks_ms()
                message = command_to_send
                if not safe_send_and_wait_ack(CAMERA_DEVICE_64BIT_ADDR, message):
                    contador_sensor += 1
                    print("Fallo al notificar al dispositivo cámara. Contador de fallos: {}".format(contador_sensor))
                device_state = STATE_SLEEP
                command_to_send = ""

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