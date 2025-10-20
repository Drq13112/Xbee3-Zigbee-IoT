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

# Objetivo para los comandos ON/OFF
CAMERA_DEVICE_NODE_ID = "XBEE_CAM"  # Reemplaza con el NI del dispositivo cámara
CAMERA_DEVICE_64BIT_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8A\xAC'  # Reemplaza con la dirección del dispositivo cámara

class Telemando(XBeeDevice):
    STATE_SEND_COMMAND = 4  # Nuevo estado para enviar comandos
    def __init__(self):
        super().__init__(device_id="XBEE_TELEMANDO", battery_pin='D1', battery_scaling_factor=2.9)
        self.coordinator_addr = COORDINATOR_64BIT_ADDR
        self.camera_addr = CAMERA_DEVICE_64BIT_ADDR
        
        # Pines específicos del telemando
        self.pin_sensor_1 = Pin('D0', Pin.IN, Pin.PULL_UP)   # Sensor digital (no usado en telemando)
        self.pin_report_req = Pin('D2', Pin.IN, Pin.PULL_UP) # Solicitar reporte
        self.pin_cmd_on = Pin('D3', Pin.IN, Pin.PULL_UP)     # Comando ON
        self.pin_cmd_off = Pin('D4', Pin.IN, Pin.PULL_UP)    # Comando OFF
        
        # Variables específicas
        self.last_press_time = 0
        self.command_to_send = ""
        self.last_command = 0
        self.contador_sensor = 0

    def check_and_process_incoming_messages(self):
        """
        Procesa los mensajes entrantes y responde cuando sea necesario.
        """
        sender, payload = self.check_received_messages()
        if not payload:
            return False
        
        payload = payload.strip()
        
        print("Mensaje recibido: '{}' de {}".format(payload, [hex(b) for b in sender]))
        
        if payload == "REPORT":
            print("Solicitud de reporte recibida, enviando respuesta...")
            battery_voltage = self.get_battery_status(as_string=False)
            status_data = "Contador={}".format(self.contador_sensor)
            response = "{}:{:.2f}:{}".format(self.device_node_id, battery_voltage, status_data)
            self.safe_send(sender, response)
            return True
        
        return False

    def run(self):
        self.setup()

        while True:
            self.feed_watchdog()
            
            try:
                # --- Máquina de Estados ---
                if self.device_state == self.STATE_STARTUP:
                    print("--- Estado: STARTUP ---")
                    battery_voltage = self.get_battery_status(as_string=False)
                    message = "{}:{:.2f}:Dispositivo iniciado.".format(self.device_node_id, battery_voltage)
                    if self.safe_send_and_wait_ack(self.coordinator_addr, message):
                        self.device_state = self.STATE_SLEEP
                    else:
                        print("No se pudo contactar al coordinador en el arranque.")
                        self.device_state = self.STATE_ERROR
                
                elif self.device_state == self.STATE_SLEEP:
                    print("--- Estado: SLEEP --- (Esperando comandos)")
                    
                    while True:
                        self.feed_watchdog()
                        
                        current_time = time.ticks_ms()
                        if time.ticks_diff(current_time, self.last_press_time) > self.DEBOUNCE_BOTTON_TIME_MS:
                            self.last_command = 0 
                        
                        # Comprobar si ha pasado el tiempo de debounce
                        if time.ticks_diff(current_time, self.last_press_time) > 1000:
                            if self.pin_cmd_on.value() == 0 and self.last_command != 1:
                                print("Boton ON presionado.")
                                self.command_to_send = "TEL:ON"
                                self.device_state = self.STATE_SEND_COMMAND
                                self.last_command = 1
                                break
                            elif self.pin_cmd_off.value() == 0 and self.last_command != 2:
                                print("Boton OFF presionado.")
                                self.command_to_send = "TEL:OFF"
                                self.device_state = self.STATE_SEND_COMMAND
                                self.last_command = 2
                                break
                            elif self.pin_report_req.value() == 0 and self.last_command != 3:
                                print("Boton REPORTE presionado.")
                                self.command_to_send = "REPORT"
                                self.device_state = self.STATE_SEND_COMMAND
                                self.last_command = 3
                                break
                            
                        if self.check_and_process_incoming_messages():
                            continue  # Si se procesó un comando, reiniciar el bucle
                        
                        time.sleep_ms(self.SLEEP_DURATION_MS)  # Pequeña pausa para no saturar CPU
                
                elif self.device_state == self.STATE_SEND_COMMAND:
                    print("--- Estado: SEND_COMMAND ---")
                    self.last_press_time = time.ticks_ms()
                    message = self.command_to_send
                    if not self.safe_send_and_wait_ack(self.camera_addr, message):
                        self.contador_sensor += 1
                        print("Fallo al notificar al dispositivo cámara. Contador de fallos: {}".format(self.contador_sensor))
                    self.device_state = self.STATE_SLEEP
                    self.command_to_send = ""
                
                elif self.device_state == self.STATE_ERROR:
                    print("--- Estado: ERROR ---")
                    print("Intentando reiniciar en {} segundos...".format(self.STATE_ERROR_SLEEP_MS / 1000))
                    time.sleep_ms(self.STATE_ERROR_SLEEP_MS)
                    self.device_state = self.STATE_STARTUP
            
            except Exception as e:
                print("Error inesperado en el bucle principal: {}".format(e))
                self.device_state = self.STATE_ERROR
                time.sleep(10)

# --- Lógica Principal ---
if __name__ == '__main__':
    telemando = Telemando()
    telemando.run()