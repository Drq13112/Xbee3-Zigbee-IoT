import xbee
import time
from machine import Pin, WDT, ADC
from sys import stdin, stdout
from tools import XBeeDevice  # Import base class

# --- Configuración ---
WDT_TIMEOUT = 60000
adc_battery = ADC('D1')
AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

class Coordinator(XBeeDevice):
    """Subclase del coordinador que hereda de XBeeDevice."""
    
    # Nuevos estados específicos del coordinador
    STATE_PROCESS_ESP32_REQUEST = 4  # Estado para procesar solicitudes del ESP32
    
    def __init__(self):
        super().__init__(device_id="XBEE_COOR", wdt_timeout=WDT_TIMEOUT, battery_pin='D1', battery_scaling_factor=2.9)
        self.device_database = {}  # Base de datos de dispositivos remotos
        self.esp32_command_buffer = ""  # Buffer para comandos del ESP32
    
    def parse_payload(self, payload_bytes):
        """Analiza el payload recibido de Zigbee."""
        try:
            payload_str = payload_bytes.decode('utf-8')
            parts = payload_str.split(':')
            if len(parts) != 3:
                return None, None, None
            node_id = parts[0]
            battery = float(parts[1])
            data = parts[2]
            return node_id, battery, data
        except (ValueError, UnicodeDecodeError):
            return None, None, None
    
    def update_device_database(self, sender_eui64, node_id, battery):
        """Actualiza la base de datos con info del dispositivo."""
        current_time = time.ticks_ms()
        if sender_eui64 not in self.device_database:
            self.device_database[sender_eui64] = {
                'node_id': node_id,
                'battery': battery,
                'last_report_time': current_time,
                'movement_count': 1
            }
            print("Nuevo dispositivo registrado: {}".format(node_id))
        else:
            db_entry = self.device_database[sender_eui64]
            db_entry.update({'node_id': node_id, 'battery': battery, 'last_report_time': current_time})
            db_entry['movement_count'] += 1
            print("Dispositivo actualizado: {}".format(node_id))
        
        # Imprimir base de datos
        print("--- Base de Datos ---")
        for eui, data in self.device_database.items():
            eui_str = ''.join('{:02x}'.format(b) for b in eui)
            print("  - {}: ID={}, Bat={}, Reportes={}".format(eui_str, data['node_id'], data['battery'], data['movement_count']))
        print("Total dispositivos: {}".format(len(self.device_database)))
    
    def send_report_to_esp32(self, node_id, battery, data):
        """Envía reporte a ESP32 via stdout."""
        message = "REPORT:{}:{:.2f}:{}".format(node_id, battery, data)
        stdout.write(message + "\n")
        print("Enviado a ESP32: {}".format(message))
    
    def handle_esp32_request(self, command):
        """Procesa solicitud del ESP32."""
        try:
            parts = command.strip().split(':')
            if len(parts) < 2:
                stdout.write("ERROR:INVALID_COMMAND\n")
                return
            
            cmd_type = parts[0].upper()
            target = parts[1]
            
            # Buscar dirección por nombre o usar directamente como dirección
            target_addr = None
            if len(target) == 16 and all(c in '0123456789ABCDEFabcdef' for c in target):    # Dirección EUI64
                target_addr = bytes.fromhex(target)
            else:                                                                           # Buscar por nombre
                for eui, data in self.device_database.items():
                    if data['node_id'] == target:
                        target_addr = eui
                        break
            
            if not target_addr:
                stdout.write("ERROR:DEVICE_NOT_FOUND\n")
                return
            
            if cmd_type == "REPORT":
                # Solicitar reporte al dispositivo remoto
                message = "{}:{:.2f}:Solicitud de reporte.".format(self.device_node_id, self.get_battery_status(as_string=False))
                if self.safe_send_and_wait_ack(target_addr, message):
                    # Esperar respuesta (simplificado; en práctica, manejar en bucle principal)
                    stdout.write("REPORT_RESPONSE:OK\n")
                else:
                    stdout.write("REPORT_RESPONSE:NO_RESPONSE\n")
            
            elif cmd_type == "CAMERA" and len(parts) == 3:
                action = parts[2].upper()
                if action in ["ON", "OFF"]:
                    message = "TEL:{}".format(action)
                    if self.safe_send_and_wait_ack(target_addr, message):
                        stdout.write("CAMERA_RESPONSE:OK\n")
                    else:
                        stdout.write("CAMERA_RESPONSE:NO_RESPONSE\n")
                else:
                    stdout.write("ERROR:INVALID_ACTION\n")
            else:
                stdout.write("ERROR:UNKNOWN_COMMAND\n")
        except Exception as e:
            print("Error procesando comando ESP32: {}".format(e))
            stdout.write("ERROR:PROCESSING_FAILED\n")
    
    def run(self):
        """Bucle principal del coordinador."""
        
        while(not self.setup()):
            time.sleep_ms(100)              # Esperar hasta inicializar
                    
        print("--- Coordinador iniciado. Esperando mensajes Zigbee y ESP32... ---")
        
        while True:
            self.feed_watchdog()
            
            # Procesar mensajes Zigbee
            try:
                received_msg = xbee.receive()
                if received_msg:
                    sender_eui64 = received_msg['sender_eui64']
                    payload = received_msg['payload']
                    
                    node_id, battery, data = self.parse_payload(payload)
                    if node_id and data:
                        self.update_device_database(sender_eui64, node_id, battery)     # Actualizar local DB
                        self.send_message(sender_eui64, "OK")                           # Feedback a dispositivo remoto
                        self.send_report_to_esp32(node_id, battery, data)               # Enviar a ESP32
            except Exception as e:
                print("Error en recepción Zigbee: {}".format(e))
            
            # Procesar comandos ESP32 (asíncrono)
            try:
                char = stdin.read(1)  # Leer carácter a carácter
                if char:
                    if char == '\n':
                        if self.esp32_command_buffer:
                            self.handle_esp32_request(self.esp32_command_buffer)
                            self.esp32_command_buffer = ""
                    else:
                        self.esp32_command_buffer += char
            except:
                pass  # Ignorar errores de lectura
            
            time.sleep_ms(10)  # Pausa para no sobrecargar CPU

# --- Lógica Principal ---
if __name__ == '__main__':
    coord = Coordinator()
    coord.run()