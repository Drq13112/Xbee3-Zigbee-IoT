import time
import xbee
from machine import ADC, Pin, WDT

class XBeeDevice:
    """Clase base para todos los perfiles de dispositivos XBee."""
    AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}
    
    # --- Estados del Dispositivo ---
    STATE_STARTUP = 0                           # Estado de arranque
    STATE_SLEEP = 1                             # Estado de sleep
    STATE_IDLE = 2                              # Estado genérico para espera activa
    STATE_ERROR = 3                             # Estado de error crítico

    
    # --- Periodos de tiempo (en milisegundos) ---
    STABILIZATION_TIME_MS = 5000                # Tiempo de estabilización tras wakeup
    SLEEP_DURATION_MS = 100                     # Tiempo de espera en modo sleep       
    RETRY_DELAY_MS = 100                        # Tiempo de espera entre reintentos de envio
    HEARING_INTERVAL_MS = 3000                  # Tiempo escuchando ACK tras envio
    WATCHDOG_TIMEOUT_MS = 120000                # Tiempo de timeout del watchdog
    STATE_ERROR_SLEEP_MS = 5000                 # Segundos en estado de error
    DEBOUNCE_BOTTON_TIME_MS = 4000              # Tiempo para resetear último comando tras inactividad
    DEBOUNCE_SENSOR_TIME_MS = 30000             # Tiempo de debounce para notificaciones del sensor
    CHECK_SENSOR_INTERVAL_MS = 1000             # Intervalo para comprobar el estado del sensor una vez activado
    CAMERA_ON_DURATION_MS = 60000               # Duración en ms que la cámara permanece encendida tras activación por sensor
    


    def __init__(self, device_id="XBEE_DEVICE", wdt_timeout=60000, battery_pin='D1', battery_scaling_factor=2.9):
        self.device_id = device_id
        self.device_node_id = "NONE"
        self.wdt_timeout = wdt_timeout
        self.adc_battery = ADC(battery_pin)
        self.battery_scaling_factor = battery_scaling_factor
        self.wdt = None
        self.xbee = None
        self.device_state = self.STATE_STARTUP
        self.contador_fallo_comunicacion = 0
        self.coordinator_addr = b'\x00\x13\xA2\x00\x42\x3D\x8D\x6E' # Dirección por defecto, puede ser sobreescrita

    def setup(self):
        """Inicializa hardware como WDT y XBee. Se llama al inicio de run()."""
        try:
            self.wdt = WDT(timeout=self.wdt_timeout)
            self.feed_watchdog()
            self.xbee = xbee.XBee()
            self.device_node_id = self.xbee.atcmd('NI') or self.device_id
            print("--- SETUP COMPLETO ---")
            print("Perfil: {}".format(self.__class__.__name__))
            print("Device NI: {}".format(self.device_node_id))
            self.xbee.sleep_ms(self.STABILIZATION_TIME_MS)  # Espera para estabilizar XBee
            return True
        except Exception as e:
            print("Error critico en inicializacion: {}".format(e))
            self.device_state = self.STATE_ERROR
            return False
        
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
        """
        Envía un mensaje sin esperar confirmación.
        """
        try:
            self.xbee.transmit(target_addr, message)
            self.feed_watchdog()
            return True
        except Exception as e:
            print("Error al enviar mensaje: {}".format(e))
            return False

    def safe_send(self, target_addr, message, retries=3):
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
                    print("Reintentando en {} segundos...".format(self.RETRY_DELAY_MS / 1000))
                    time.sleep_ms(self.RETRY_DELAY_MS)
                else:
                    print("Fallo al enviar mensaje tras varios reintentos.")
                    return False
        print("Mensaje enviado correctamente.")
        return True

    def safe_send_and_wait_ack(self, target_addr, message, retries=3):
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

                while time.ticks_diff(time.ticks_ms(), start_wait) < (self.HEARING_INTERVAL_MS):
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
                print("Reintentando en {} segundos...".format(self.RETRY_DELAY_MS / 1000))
                time.sleep_ms(self.RETRY_DELAY_MS)

        print("Fallo al enviar y confirmar mensaje tras varios reintentos.")
        return False
    
    def turn_on_camera(self):
        self.pin_camera.value(1)
        print("Cámara encendida.")

    def turn_off_camera(self):
        self.pin_camera.value(0)
        print("Cámara apagada.")
        
    def check_received_messages(self):
        """
        Revisa si han llegado mensajes y los devuelve.
        """
        try:
            received_msg = self.xbee.receive()
            self.feed_watchdog()
            if received_msg:
                payload = received_msg['payload'].decode('utf-8')
                sender = received_msg['sender_eui64']
                print("Mensaje recibido de {}: '{}'".format(sender, payload))
                return sender, payload
            return None, None
        except Exception as e:
            self.feed_watchdog()
            print("Error al recibir mensaje: {}".format(e))
            return None, None