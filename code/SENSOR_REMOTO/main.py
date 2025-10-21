# -*- coding: utf-8 -*-
import sys
from machine import Pin
import machine
import time
import xbee
from ..tools import XBeeDevice  # Assuming tools.py is in the parent directory; adjust if needed

# --- Configuración ---
TARGET_NODE_ID = "XBEE_COOR"
COORDINATOR_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8D\x6E'


CAMERA_DEVICE_NODE_ID = "XBEE_CAMERA"
CAMERA_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8D\x6E'

class EndDevice(XBeeDevice):
    # Sobrescribir constantes específicas del dispositivo
    STATE_REPORT_BATTERY = 4
    STATE_SENSOR_ACTIVE = 5
    STATE_SENSOR_TRIGGERED = 6
    STATE_ERROR = 7

    def __init__(self):
        super().__init__(device_id="XBEE_X", wdt_timeout=60000, battery_pin='D1', battery_scaling_factor=1.0, deep_sleep = False)  # Ajustar scaling si necesario
        self.coordinator_addr = COORDINATOR_64BIT_ADDR
        
        # Pines específicos del dispositivo
        self.pin_sensor_1 = Pin('D0', Pin.IN, Pin.PULL_UP)
        self.pin_sensor_2 = Pin('D2', Pin.IN, Pin.PULL_UP)
        self.pin_sensor_3 = Pin('D3', Pin.IN, Pin.PULL_UP)
        self.pin_sensor_4 = Pin('D4', Pin.IN, Pin.PULL_UP)
        self.pin_camera = Pin('D5', Pin.OUT, value=0)
        
        # Variables específicas
        self.camera_on_time = 0
        self.pin_sensor_general = False
        self.device_state = self.STATE_STARTUP
        self.deep_sleep = deep_sleep

    def check_pins_sensor(self):
        if (self.pin_sensor_1.value() != 0 or self.pin_sensor_2.value() != 0 or
                self.pin_sensor_3.value() != 0 or self.pin_sensor_4.value() != 0):
            self.pin_sensor_general = True
        else:
            self.pin_sensor_general = False

    def run(self):
        self.setup()
        
        while True:
            self.feed_watchdog()
            
            try:
                # --- Gestión de la cámara ---
                if self.pin_camera.value() == 1 and time.ticks_diff(time.ticks_ms(), self.camera_on_time) > self.CAMERA_ON_DURATION_MS:
                    self.pin_camera.value(0)
                    print("Cámara apagada por temporizador.")
                
                # --- Máquina de Estados ---
                if self.device_state == self.STATE_STARTUP:
                    print("--- Estado: STARTUP ---")
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
                    # Entrar en sueño profundo
                    self.xbee.sleep_now(self.DEEP_SLEEP_DURATION_MS, True)
                    
                    # Llamar a wake_reason() UNA SOLA VEZ y guardar el resultado
                    wake_reason = self.xbee.wake_reason()
                    if wake_reason is xbee.PIN_WAKE:
                        print("Despertado por el sensor.")
                        self.device_state = self.STATE_SENSOR_TRIGGERED
                    else:
                        print("Despertado por: {}".format(wake_reason))
                        self.device_state = self.STATE_REPORT_BATTERY  #Enviar reporte periodico
                        
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
                    battery_voltage = self.get_battery_status(as_string=False)
                    message = "{}:{:.2f}:Reporte periodico.".format(self.device_node_id, battery_voltage)
                    if not self.safe_send_and_wait_ack(self.coordinator_addr, message):
                        self.contador_fallo_comunicacion += 1
                    if self.deep_sleep:
                        self.device_state = self.STATE_SLEEP
                    else:
                        self.device_state = self.STATE_IDLE

                
                elif self.device_state == self.STATE_SENSOR_ACTIVE:
                    print("--- Estado: IDLE --- Esperando timer camera se acabe y el sensor se apague")
                    self.check_pins_sensor()
                    
                    if self.pin_sensor_general == 0:
                        print("Sensor apagado, pasamos a estado SLEEP.")
                        if self.deep_sleep:
                            self.device_state = self.STATE_SLEEP
                        else:
                            self.device_state = self.STATE_IDLE
                    
                    elif time.ticks_diff(time.ticks_ms(), self.camera_on_time) > self.TIME_TO_REPORT_SENSORT_TRIGERED:
                        battery_voltage = self.get_battery_status(as_string=False)
                        message = "{}:{:.2f}:ALERTA! Sensor activado.".format(self.device_id, battery_voltage)
                        if not self.safe_send_and_wait_ack(self.coordinator_addr, message):
                            self.contador_fallo_comunicacion += 1
                        self.device_state = self.STATE_SENSOR_ACTIVE  # Vuelve a esperar
                    time.sleep_ms(1000)
                
                elif self.device_state == self.STATE_SENSOR_TRIGGERED:
                    print("--- Estado: SENSOR_TRIGGERED ---")
                    self.pin_camera.value(1)
                    self.camera_on_time = time.ticks_ms()
                    print("Cámara activada.")
                    self.check_pins_sensor()
                    battery_voltage = self.get_battery_status(as_string=False)
                    message = "{}:{:.2f}:ALERTA! Sensor activado.".format(self.device_id, battery_voltage)
                    if not self.safe_send_and_wait_ack(self.coordinator_addr, message):
                        self.contador_fallo_comunicacion += 1
                    self.device_state = self.STATE_SENSOR_ACTIVE
                
                elif self.device_state == self.STATE_ERROR:
                    print("--- Estado: ERROR ---")
                    print("Intentando reconectar en {} segundos...".format(self.STATE_ERROR_SLEEP_MS / 1000))
                    time.sleep_ms(self.STATE_ERROR_SLEEP_MS)
                    self.device_state = self.STATE_STARTUP
            
            except Exception as e:
                print("Error inesperado en el bucle principal: {}".format(e))
                self.device_state = self.STATE_ERROR
                time.sleep(10)

# --- Lógica Principal ---
if __name__ == '__main__':
    end_device = EndDevice()
    end_device.run()