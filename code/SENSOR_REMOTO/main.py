# -*- coding: utf-8 -*-
import sys
from machine import Pin
import machine
import time
import xbee
from tools import XBeeDevice  # Assuming tools.py is in the parent directory; adjust if needed


xbee_device = xbee.XBee()
# --- Configuración ---
TARGET_NODE_ID = "XBEE_COOR"
COORDINATOR_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8B\x99'


CAMERA_DEVICE_NODE_ID = "XBEE_CAMERA"
CAMERA_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8A\xAC'

class EndDevice(XBeeDevice):
    # Sobrescribir constantes específicas del dispositivo
    STATE_REPORT_BATTERY = 4
    STATE_SENSOR_ACTIVE = 5
    STATE_SENSOR_TRIGGERED = 6
    STATE_ERROR = 7

    def __init__(self, xbee_instance=None, deep_sleep=True, camera_remote=True, local_camera=False):
        super().__init__(device_id="XBEE_X", wdt_timeout=60000, battery_pin='D1', battery_scaling_factor=2.9, pin_camera='D12', xbee_instance=xbee_instance)
        self.coordinator_addr = COORDINATOR_64BIT_ADDR
        self.remote_camera_addr = CAMERA_64BIT_ADDR
        # Variables específicas del sensor remoto
        self.deep_sleep = deep_sleep                        # Habilitar deep sleep
        self.camera_remote = camera_remote                  # Usar cámara remota
        self.last_sensor_notification_time = 0              # Tiempo de la última notificación de sensor
        self.local_camera = local_camera
        self.pin_sensor_5 = Pin('D8', Pin.IN, Pin.PULL_UP)

    def check_pins_sensor(self):
        self.feed_watchdog()
        if (self.pin_sensor_5.value() != 0):
            self.pin_sensor_general = True
        else:
            self.pin_sensor_general = False

    def turn_on_camera(self):
        self.pin_camera.value(1)
        print("Cámara encendida.")

    def turn_off_camera(self):
        self.pin_camera.value(0)
        print("Cámara apagada.")       
        
    def run(self):
        self.setup()
        
        while True:
            self.feed_watchdog()
            try:
                
                # --- Máquina de Estados ---
                if self.device_state == self.STATE_STARTUP:
                    print("--- Estado: STARTUP ---")
                    self.feed_watchdog()
                    battery_voltage = self.get_battery_status(as_string=False)
                    message = "{}:{:.2f}:Dispositivo iniciado.".format(self.device_node_id, battery_voltage)
                    if self.safe_send_and_wait_ack(self.coordinator_addr, message):
                        if self.deep_sleep:
                            self.device_state = self.STATE_SLEEP
                        else:
                            self.device_state = self.STATE_IDLE
                    else:
                        print("No se pudo contactar al coordinador en el arranque.")
                        self.device_state = self.STATE_ERROR
                
                elif self.device_state == self.STATE_SLEEP:
                    
                    print("--- Estado: SLEEP --- ")
                    self.feed_watchdog()
                    try:
                        # Use XBee instance methods, not module functions
                        self.xbee_.sleep_now(self.DEEP_SLEEP_DURATION_MS, True)
                        wake_reason = self.xbee_.wake_reason()

                        # Use XBee instance constants for comparison
                        if wake_reason is xbee.PIN_WAKE:  # PIN_WAKE is a module constant
                            print("Despertado por el sensor.")
                            self.device_state = self.STATE_SENSOR_TRIGGERED
                        else:
                            print("Despertado por timeout de deep sleep.")
                            self.device_state = self.STATE_REPORT_BATTERY  #Enviar reporte periodico
                    except Exception as e:
                        print("Error al determinar la razón de wakeup: {}".format(e))
                        self.device_state = self.STATE_SENSOR_TRIGGERED
                        
                elif self.device_state == self.STATE_IDLE:
                    print("--- Estado: IDLE --- ")
                    while True:
                        self.feed_watchdog()
                        self.check_pins_sensor()
                        if self.pin_sensor_general:
                            self.device_state = self.STATE_SENSOR_TRIGGERED
                            break

                        time.sleep_ms(self.SLEEP_DURATION_MS)  # Pequeña pausa para no saturar CPU

                elif self.device_state == self.STATE_REPORT_BATTERY:
                    print("--- Estado: REPORT_BATTERY ---")
                    self.feed_watchdog()
                    battery_voltage = self.get_battery_status(as_string=False)
                    message = "{}:{:.2f}:Reporte periodico.".format(self.device_node_id, battery_voltage)
                    if not self.safe_send_and_wait_ack(self.coordinator_addr, message):
                        self.contador_fallo_comunicacion += 1
                    else:
                        self.contador_fallo_comunicacion = 0
                    if self.deep_sleep:
                        self.device_state = self.STATE_SLEEP
                    else:
                        self.device_state = self.STATE_IDLE

                elif self.device_state == self.STATE_SENSOR_TRIGGERED:
                    print("--- Estado: SENSOR_TRIGGERED ---")
                    self.feed_watchdog()
                    self.check_pins_sensor()
                    if self.pin_sensor_general == 1:
                        current_time = time.ticks_ms()
                        # Comprobar si ha pasado suficiente tiempo desde la última notificación para no saturar la red a mensajes
                        if self.camera_remote:
                            if time.ticks_diff(current_time, self.last_sensor_notification_time) >= self.DEBOUNCE_SENSOR_TIME_MS:  
                                command_to_send = "SENSOR:ON"
                                print("Enviando notificación de sensor activado")
                                if self.safe_send_and_wait_ack(self.remote_camera_addr, command_to_send):
                                    self.last_sensor_notification_time = current_time
                                else:
                                    self.contador_fallo_comunicacion += 1
                            else:
                                print("Esperando para reenviar notificación de sensor: {} segundos restantes".format((self.DEBOUNCE_SENSOR_TIME_MS - time.ticks_diff(current_time, self.last_sensor_notification_time) )//1000))
                                    
                        if self.local_camera:
                            if time.ticks_diff(current_time, self.camera_on_time) >= self.CAMERA_ON_DURATION_MS:
                                self.turn_on_camera()  # Activar cámara localmente
                                self.camera_on_time = current_time

                        time.sleep_ms(self.CHECK_SENSOR_INTERVAL_MS)  # Esperar antes de verificar de nuevo
                    else:
                        if self.local_camera and self.pin_camera.value() == 1:
                            self.turn_off_camera()
                            
                        # El sensor ya no está activado, volver a dormir
                        print("Sensor ya no activado, volviendo a modo SLEEP/IDLE")
                        if self.deep_sleep:
                            self.device_state = self.STATE_SLEEP
                        else:
                            self.device_state = self.STATE_IDLE
                
                elif self.device_state == self.STATE_ERROR:
                    print("--- Estado: ERROR ---")
                    self.feed_watchdog()
                    print("Intentando reconectar en {} segundos...".format(self.STATE_ERROR_SLEEP_MS / 1000))
                    time.sleep_ms(self.STATE_ERROR_SLEEP_MS)
                    self.setup()
                    self.feed_watchdog()
                    self.device_state = self.STATE_STARTUP
                    
                self.check_coordinator_retry() # Background check for coordinator retries
                
            except Exception as e:
                self.feed_watchdog()
                print("Error inesperado en el bucle principal: {}".format(e))
                self.device_state = self.STATE_ERROR
                time.sleep_ms(self.STATE_ERROR_SLEEP_MS)

# --- Lógica Principal ---
if __name__ == '__main__':
    end_device = EndDevice(xbee_instance=xbee_device, deep_sleep=False, camera_remote=True, local_camera=False)
    end_device.run()