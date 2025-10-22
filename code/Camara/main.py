# -*- coding: utf-8 -*-
import sys
from machine import Pin
import machine
import time
import xbee
from ..tools import XBeeDevice  # Assuming tools.py is in the parent directory; adjust if needed

# --- Configuración ---
# Objetivo para reportes periódicos y de estado
COORDINATOR_NODE_ID = "XBEE_COOR"
COORDINATOR_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8B\x99'

class Camara(XBeeDevice):
    # Sobrescribir constantes específicas de la cámara
    RETRY_DELAY_MS = 1000
    HEARING_INTERVAL_MS = 2000
    STATE_SENSOR_TRIGGERED = 3  # Estado adicional para activación por sensor

    def __init__(self):
        super().__init__(device_id="XBEE_CAM", wdt_timeout=120000, battery_pin='D1', battery_scaling_factor=2.9, pin_camera='D12')
        self.coordinator_addr = COORDINATOR_64BIT_ADDR        

    def check_and_process_incoming_messages(self):
        """
        Revisa si hay mensajes entrantes y los procesa.
        Devuelve True si se procesó un comando, False en caso contrario.
        """
        self.feed_watchdog()
        sender, payload = self.check_received_messages()
        if not payload:
            return False
        
        payload = payload.strip()
        print("Mensaje recibido de {}: '{}'".format(sender, payload))
        
        command = payload
        response_message = "{}:OK".format(command)
        
        if command == "TEL:ON":
            print("Comando ON recibido. Encendiendo cámara indefinidamente.")
            self.turn_on_camera()
            self.manual_camera = True  # Anula el temporizador
            self.device_state = self.STATE_SLEEP
            self.safe_send(sender, response_message)
            return True
        
        elif command == "TEL:OFF":
            print("Comando OFF recibido. Apagando cámara.")
            self.turn_off_camera()
            self.manual_camera = False
            self.device_state = self.STATE_SLEEP
            self.safe_send(sender, response_message)
            return True
        
        elif command == "REPORT":
            print("Comando REPORT recibido.")
            battery_status = self.get_battery_status(as_string=True)
            report = "Estado: {}, Camara: {}, {}, Manual: {}".format(self.device_state, "ON" if self.pin_camera.value() else "OFF", battery_status, self.manual_camera)
            self.safe_send(sender, "{}: {}".format(self.device_node_id, report))
            self.device_state = self.STATE_SLEEP
            return True
            
        elif command == "SENSOR:ON":
            print("Comando SENSOR:ON recibido. Encendiendo cámara por temporizador.")
            self.turn_on_camera()
            self.camera_on_time = time.ticks_ms()
            self.device_state = self.STATE_SLEEP
            self.safe_send(sender, response_message)
            return True
        
        else:
            response_message = "UNKNOWN COMMAND RECEIVED"
            self.safe_send(sender, response_message)
            
        return False

    def check_sensor_pins(self):
        self.feed_watchdog()
        """Devuelve True si algún sensor está activado, False si no."""
        return (self.pin_sensor_1.value() == 0 or self.pin_sensor_2.value() == 0 or
                self.pin_sensor_3.value() == 0 or self.pin_sensor_4.value() == 0)

    def run(self):
        self.setup()
        while True:
            self.feed_watchdog()
            
            try:
                # --- Procesar mensajes entrantes (tiene prioridad) ---
                if self.check_and_process_incoming_messages():
                    continue  # Si se procesó un comando, reiniciar el bucle
                
                # --- Máquina de Estados ---
                if self.device_state == self.STATE_STARTUP:
                    print("--- Estado: STARTUP ---")
                    self.feed_watchdog()
                    battery_voltage = self.get_battery_status(as_string=False)
                    message = "{}:{:.2f}:Dispositivo iniciado".format(self.device_node_id, battery_voltage)
                    if self.safe_send_and_wait_ack(self.coordinator_addr, message):
                        self.device_state = self.STATE_SLEEP
                    else:
                        self.device_state = self.STATE_ERROR
                
                elif self.device_state == self.STATE_SLEEP:
                    print("--- Estado: SLEEP ---")
                    self.feed_watchdog()
                    idle_start = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), idle_start) < self.SLEEP_DURATION_MS:
                        self.feed_watchdog()
                        if self.check_and_process_incoming_messages():
                            time.sleep_ms(100)
                            break
                        if self.pin_camera.value() == 1 and not self.manual_camera:
                            print("Tiempo restante para apagado: {} segundos.".format((self.CAMERA_ON_DURATION_MS - time.ticks_diff(time.ticks_ms(), self.camera_on_time)) // 1000))
                        # --- Gestión de la cámara (se apaga por temporizador solo si no es manual) ---
                        if self.pin_camera.value() == 1 and not self.manual_camera and time.ticks_diff(time.ticks_ms(), self.camera_on_time) > self.CAMERA_ON_DURATION_MS:
                            self.turn_off_camera()
                            print("Cámara apagada por temporizador.")
                            self.device_state = self.STATE_SLEEP
                            time.sleep_ms(50)
                
                elif self.device_state == self.STATE_SENSOR_TRIGGERED:
                    print("--- Estado: SENSOR_TRIGGERED ---")
                    self.feed_watchdog()
                    self.turn_on_camera()
                    self.camera_on_time = time.ticks_ms()
                    self.device_state = self.STATE_SLEEP
                
                elif self.device_state == self.STATE_ERROR:
                    print("--- Estado: ERROR ---")
                    self.feed_watchdog()
                    print("Intentando reiniciar en {} segundos...".format(self.STATE_ERROR_SLEEP_MS / 1000))
                    time.sleep_ms(self.STATE_ERROR_SLEEP_MS)
                    self.device_state = self.STATE_STARTUP
            
            except Exception as e:
                self.feed_watchdog()
                print("Error inesperado en el bucle principal: {}".format(e))
                self.device_state = self.STATE_ERROR
                time.sleep(10)
    
# --- Lógica Principal ---
if __name__ == '__main__':
    camara = Camara()
    camara.run()