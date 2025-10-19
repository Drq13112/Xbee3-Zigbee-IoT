import time
import xbee
from machine import ADC, Pin, WDT

class XBeeDevice:
    AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

    def __init__(self, device_id, wdt_timeout=60000):
        self.device_id = device_id
        self.device_node_id = "NONE"
        self.wdt_timeout = wdt_timeout
        self.adc_battery = ADC('D1')
        self.wdt = WDT(timeout=self.wdt_timeout)
        self.xbee = xbee.XBee()
        self.device_state = 0  # Puede interpretarse como STATE_STARTUP
        self.init_watchdog()

    def init_watchdog(self):
        self.feed_watchdog()

    def feed_watchdog(self):
        if self.wdt:
            self.wdt.feed()

    def get_battery_status(self, as_string=True):
        try:
            try:
                av = xbee.atcmd("AV")
            except KeyError:
                av = None
            reference_v = self.AV_VALUES.get(av, 2.5)
            adc_raw_value = self.adc_battery.read()
            pin_voltage = (adc_raw_value / 4095.0) * reference_v
            battery_voltage = pin_voltage * (12.0 / 3.3) * 2.9
            if as_string:
                return "Bateria: {:.2f}V".format(battery_voltage)
            return battery_voltage
        except Exception as e:
            print("Error leyendo batería: {}".format(e))
            return "Bateria: ERROR" if as_string else 0.0

    def send_message(self, target_addr, message):
        try:
            self.xbee.transmit(target_addr, message)
            self.feed_watchdog()
            return True
        except Exception as e:
            print("Error al enviar mensaje: {}".format(e))
            return False

    def safe_send(self, target_addr, message, retries=3, delay_ms=3000):
        for attempt in range(retries):
            if self.send_message(target_addr, message):
                return True
            print("Reintentando en {} ms...".format(delay_ms))
            time.sleep_ms(delay_ms)
        print("Fallo al enviar mensaje tras {} reintentos.".format(retries))
        return False

    def safe_send_and_wait_ack(self, target_addr, message, retries=3, delay_ms=3000):
        for attempt in range(retries):
            if self.send_message(target_addr, message):
                start_wait = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), start_wait) < delay_ms:
                    self.feed_watchdog()
                    received_msg = self.xbee.receive()
                    if received_msg and received_msg.get('sender_eui64') == target_addr:
                        return True
                    time.sleep_ms(10)
            print("No se recibió ACK, reintentando...")
            time.sleep_ms(delay_ms)
        print("Fallo al enviar mensaje con ACK tras {} intentos.".format(retries))
        return False

#--------------------------------------------------------
# Clase especializada para el perfil de Coordinador (Sin sleep)
#--------------------------------------------------------
class Coordinator(XBeeDevice):
    def __init__(self, device_id="XBEE_COOR", **kwargs):
        super().__init__(device_id, **kwargs)
        self.device_database = {}

    def parse_payload(self, payload_bytes):
        try:
            payload_str = payload_bytes.decode('utf-8')
            parts = payload_str.split(':')
            if len(parts) != 3:
                print("Error: Formato incorrecto en payload")
                return None, None, None
            node_id = parts[0]
            battery = float(parts[1])
            data = parts[2]
            return node_id, battery, data
        except Exception as e:
            print("Error al parsear payload: {}".format(e))
            return None, None, None

    def update_device_database(self, sender_eui64, node_id, battery):
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
            db_entry['node_id'] = node_id
            db_entry['battery'] = battery
            db_entry['last_report_time'] = current_time
            db_entry['movement_count'] += 1
            print("Dispositivo actualizado: {}".format(node_id))

    def send_feedback(self, recipient_eui64, payload):
        try:
            print("Enviando feedback a {}".format(''.join('{:02x}'.format(b) for b in recipient_eui64)))
            self.xbee.transmit(recipient_eui64, payload)
            print("Feedback enviado con éxito.")
        except Exception as e:
            print("Error enviando feedback: {}".format(e))

#--------------------------------------------------------
# Clase especializada para el perfil de Cámara (Sin sleep)
#--------------------------------------------------------
class Camera(XBeeDevice):
    def __init__(self, device_id="XBEE_CAM", camera_pin='D12', **kwargs):
        super().__init__(device_id, **kwargs)
        self.pin_camera = Pin(camera_pin, Pin.OUT, value=0)
        self.manual_mode = False

    def turn_on_camera(self):
        self.pin_camera.value(1)
        print("Cámara encendida.")

    def turn_off_camera(self):
        self.pin_camera.value(0)
        print("Cámara apagada.")

    def process_command(self, command, sender_addr):
        response_message = "{}:OK".format(command)
        if command == "TEL:ON":
            self.turn_on_camera()
            self.manual_mode = True
        elif command == "TEL:OFF":
            self.turn_off_camera()
            self.manual_mode = False
        elif command == "REPORT":
            battery_status = self.get_battery_status(as_string=True)
            report = "Estado: {}, Cámara: {}, {}".format(
                self.device_state, "ON" if self.pin_camera.value() else "OFF", battery_status)
            response_message = "{}: {}".format(self.device_node_id, report)
        elif command == "SENSOR:ON":
            self.turn_on_camera()
        else:
            response_message = "UNKNOWN COMMAND RECEIVED"
        self.safe_send(sender_addr, response_message)

#--------------------------------------------------------
# Clase especializada para el perfil de Telemando (Sin sleep)
#--------------------------------------------------------
class Telemand(XBeeDevice):

    def __init__(self, device_id="XBEE_TELEMANDO", camera_addr=None, debounce_btn_ms=4000, **kwargs):
        super().__init__(device_id, **kwargs)
        self.camera_addr = camera_addr
        self.debounce_btn_ms = debounce_btn_ms
        
        self.pin_cmd_on = Pin('D3', Pin.IN, Pin.PULL_UP)
        self.pin_cmd_off = Pin('D4', Pin.IN, Pin.PULL_UP)
        self.pin_report_req = Pin('D2', Pin.IN, Pin.PULL_UP)
        
        self.last_press_time = 0
        self.last_command_code = 0 # 1:ON, 2:OFF, 3:REPORT
        self.command_to_send = ""
        self.communication_failures = 0
        
    def check_buttons(self):
        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, self.last_press_time) > self.debounce_btn_ms:
            self.last_command_code = 0

        if time.ticks_diff(current_time, self.last_press_time) > 1000: # Evitar rebotes rápidos
            if self.pin_cmd_on.value() == 0 and self.last_command_code != 1:
                return "TEL:ON", 1
            if self.pin_cmd_off.value() == 0 and self.last_command_code != 2:
                return "TEL:OFF", 2
            if self.pin_report_req.value() == 0 and self.last_command_code != 3:
                return "REPORT", 3
        return None, 0
        

#--------------------------------------------------------
# Clase especializada para el perfil de Router (Sin sleep)
#--------------------------------------------------------
class Router(XBeeDevice):
    def __init__(self, device_id="XBEE_ROUTER", **kwargs):
        super().__init__(device_id, **kwargs)
        

#--------------------------------------------------------
# Clase especializada para el perfil de Sensor Remoto (Con sleep o sin sleep)
#--------------------------------------------------------
class RemoteSensor(XBeeDevice):
    STATE_SENSOR_TRIGGERED = 5

    def __init__(self, device_id="XBEE_SENSOR", camera_addr=None, debounce_ms=30000, **kwargs):
        super().__init__(device_id, **kwargs)
        self.camera_addr = camera_addr
        self.debounce_ms = debounce_ms
        self.sensor_pin = Pin('D8', Pin.IN, Pin.PULL_UP)
        self.last_notification_time = 0
        self.communication_failures = 0

    def check_incoming_messages(self):
        msg = self.xbee.receive()
        if msg:
            sender = msg['sender_eui64']
            payload = msg['payload'].decode('utf-8').strip()
            print("Mensaje recibido: '{}' de {}".format(payload, ''.join('{:02x}'.format(b) for b in sender)))
            if payload == "REPORT":
                battery = self.get_battery_status(as_string=False)
                response = "{}:{:.2f}:Failures={}".format(self.device_node_id, battery, self.communication_failures)
                self.safe_send(sender, response)
    
    
#--------------------------------------------------------
# Clase especializada para el perfil End Device con accionamiento de camara (Con sleep o sin sleep)
#--------------------------------------------------------

class EndDeviceCamera(XBeeDevice):
    def __init__(self, device_id="XBEE_ENDCAM", sleep_mode=True, camera_pin='D12', **kwargs):
        super().__init__(device_id, **kwargs)
        self.sleep_mode = sleep_mode
        self.pin_camera = Pin(camera_pin, Pin.OUT, value=0)

    def turn_on_camera(self):
        self.pin_camera.value(1)
        print("Cámara encendida.")

    def turn_off_camera(self):
        self.pin_camera.value(0)
        print("Cámara apagada.")