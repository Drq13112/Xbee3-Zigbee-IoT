# -*- coding: utf-8 -*-
import sys
from machine import Pin, WDT, ADC
import machine
import time
import xbee

# --- Configuración ---
TARGET_NODE_ID = "XBEE_COOR"
COORDINATOR_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8B\x99'
DEVICE_ID = "XBEE_X"
DEVICE_ID_NI = "NONE"

# Periodos de tiempo (en milisegundos)
SLEEP_DURATION_MS = 3000
CAMERA_ON_DURATION_MS = 30000  # 30 segs
RETRY_DELAY_S = 5
WATCHDOG_TIMEOUT_MS = 60000 # 60 segundos. Debe ser mayor que cualquier espera.
STATE_ERROR_SLEEP_MS = 5000 # 5 segundos en estado de error
TIME_TO_REPORT_SENSORT_TRIGERED = 5000 # 5 segundos para enviar alerta tras sensor activado

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
STATE_SENSOR_ACTIVE = 3
STATE_SENSOR_TRIGGERED = 4
STATE_ERROR = 5

# --- Variables Globales ---
device_state = STATE_STARTUP
camera_on_time = 0
xb = None 
dog = None
pin_sensor_general = False

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
        battery_voltage = pin_voltage * (12.0 / 3.3)
        
        if as_string:
            # Formatear el resultado a dos decimales.
            return "Bateria: {:.2f}V".format(battery_voltage)
        else:
            return battery_voltage
    except Exception as e:
        print("Error al leer la bateria: {}".format(e))
        return "Bateria: ERROR" if as_string else 0.0

def safe_send_message(target_addr, message, retries=3):
    """
    Envía un mensaje de forma segura, con reintentos y alimentando el watchdog.
    Espera un feedback (cualquier mensaje) del coordinador para confirmar.
    """
    global dog,xb,DEVICE_ID_NI
    for attempt in range(retries):
        try:
            print("Enviando (intento {}/{})".format(attempt + 1, retries))
            xbee.transmit(target_addr, message)

            # Esperar feedback
            start_wait = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start_wait) < (RETRY_DELAY_S * 1000):
                dog.feed() # Alimentar mientras se espera
                received_msg = xbee.receive()
                if received_msg and received_msg['sender_eui64'] == target_addr:
                    print("Feedback recibido del coordinador.")
                    return True
                time.sleep_ms(100)

            print("No se recibió feedback en el tiempo esperado.")

        except Exception as e:
            print("Error al transmitir: {}".format(e))

        # Si falla, esperar antes de reintentar
        if attempt < retries - 1:
            print("Reintentando en {} segundos...".format(RETRY_DELAY_S))
            time.sleep(RETRY_DELAY_S)

    print("Fallo al enviar mensaje tras varios reintentos.")
    return False

def check_pins_sensor():
    global pin_sensor_general
    if (pin_sensor_1.value() != 0 or pin_sensor_2.value() != 0 or
            pin_sensor_3.value() != 0 or pin_sensor_4.value() != 0):
        pin_sensor_general = True
    else:
        pin_sensor_general = False
        
        
# --- Lógica Principal (Máquina de Estados) ---
def main():
    global device_state, camera_on_time, xb, dog, DEVICE_ID_NI, pin_sensor_general

    # Inicialización del Watchdog y XBee
    try:
        dog = WDT(timeout=WATCHDOG_TIMEOUT_MS)
        dog.feed()
        xb = xbee.XBee()
        
        print("XBee y Watchdog inicializados.")
        DEVICE_ID_NI = xbee.atcmd('NI') or DEVICE_ID
    except Exception as e:
        print("Error critico en inicializacion: {}".format(e))
        # Sin WDT o XBee, no podemos hacer nada. Parpadea un LED o similar.
        while True:
            time.sleep(5)

    while True:
        dog.feed() # Alimentar al inicio de cada ciclo del bucle

        try:
            # --- Gestión de la cámara (se ejecuta en paralelo a los estados) ---
            if pin_camera.value() == 1 and time.ticks_diff(time.ticks_ms(), camera_on_time) > CAMERA_ON_DURATION_MS:
                pin_camera.value(0)
                print("Cámara apagada por temporizador.")
                device_state = STATE_REPORT_BATTERY


            # --- Máquina de Estados ---
            if device_state == STATE_STARTUP:
                print("--- Estado: STARTUP ---")
                battery_voltage = get_battery_status(as_string=False)
                message = "{}:{:.2f}:Dispositivo iniciado.".format(DEVICE_ID_NI, battery_voltage)
                if safe_send_message(TARGET_64BIT_ADDR, message):
                    device_state = STATE_SLEEP
                else:
                    print("No se pudo contactar al coordinador en el arranque.")
                    device_state = STATE_ERROR

            elif device_state == STATE_SLEEP:
                print("--- Estado: SLEEP --- (durante {}s)".format(SLEEP_DURATION_MS / 1000))
                # El modulo no se duerme, pero se queda en reposo hasta que llegue la hora de reporte o se active un sensor.
                sleep_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), sleep_start) < SLEEP_DURATION_MS:
                    dog.feed()
                    if pin_sensor_general == 1:
                        print("Sensor activado durante la espera.")
                        device_state = STATE_SENSOR_TRIGGERED
                        break
                    time.sleep_ms(100)
                device_state = STATE_REPORT_BATTERY
                
            elif device_state == STATE_REPORT_BATTERY:
                print("--- Estado: REPORT_BATTERY ---")
                battery_voltage = get_battery_status(as_string=False)
                message = "{}:{:.2f}:Reporte periodico.".format(DEVICE_ID_NI, battery_voltage)
                if safe_send_message(TARGET_64BIT_ADDR, message):
                    # El reporte fue exitoso y se recibió FBK, volver a dormir.
                    print("Reporte de batería enviado con éxito.")
                    device_state = STATE_SLEEP
                else:
                    # No se recibió FBK, se asume pérdida de conexión.
                    print("Fallo al enviar reporte de batería. Entrando en modo de error para reconectar.")
                    device_state = STATE_ERROR

            elif device_state == STATE_SENSOR_ACTIVE:
                print("--- Estado: IDLE --- Espererando timer camera se acabe y el sensor se apague")
                # El dispositivo está despierto, esperando la activación del sensor

                check_pins_sensor()
                print("pin_sensor_general =", pin_sensor_general)
                print("pin_sensor_1.value() =", pin_sensor_1.value())
                print("pin_sensor_2.value() =", pin_sensor_2.value())
                print("pin_sensor_3.value() =", pin_sensor_3.value())
                print("pin_sensor_4.value() =", pin_sensor_4.value())
                print("Camera timer:", time.ticks_diff(time.ticks_ms(), camera_on_time), "ms")
                
                if pin_sensor_general == 0:
                    print("Sensor apagado, pasamos a estado REPORT_BATTERY.")
                    device_state = STATE_REPORT_BATTERY
                    
                elif time.ticks_diff(time.ticks_ms(), camera_on_time) > TIME_TO_REPORT_SENSORT_TRIGERED:
                    battery_voltage = get_battery_status(as_string=False)
                    message = "{}:{:.2f}:ALERTA! Sensor activado.".format(DEVICE_ID, battery_voltage)
                    if not safe_send_message(TARGET_64BIT_ADDR, message):
                        print("Fallo al enviar la alerta.")
                    device_state = STATE_SENSOR_ACTIVE # Vuelve a esperar
                time.sleep_ms(1000)

            elif device_state == STATE_SENSOR_TRIGGERED:
                print("--- Estado: SENSOR_TRIGGERED ---")
                pin_camera.value(1)
                camera_on_time = time.ticks_ms()
                print("Cámara activada.")
                check_pins_sensor()
                battery_voltage = get_battery_status(as_string=False)
                message = "{}:{:.2f}:ALERTA! Sensor activado.".format(DEVICE_ID, battery_voltage)
                if not safe_send_message(TARGET_64BIT_ADDR, message):
                    print("Fallo al enviar la alerta.")
                    # Aunque falle el envío, la cámara ya está encendida.
                device_state = STATE_SENSOR_ACTIVE # Vuelve a esperar

            elif device_state == STATE_ERROR:
                print("--- Estado: ERROR ---")
                # Intentar recuperarse cada 60 segundos
                print("Intentando reconectar en 60 segundos...")
                time.sleep(STATE_ERROR_SLEEP_MS)
                device_state = STATE_STARTUP # Intenta el ciclo de arranque de nuevo

        except Exception as e:
            print("Error inesperado en el bucle principal: {}".format(e))
            # Un error grave podría poner el dispositivo en estado de ERROR
            device_state = STATE_ERROR
            time.sleep(10) # Esperar antes de reintentar

if __name__ == '__main__':
    main()