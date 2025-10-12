import xbee
import time
import machine
from machine import WDT
import network

try:
    from umqtt.simple import MQTTClient
except ImportError:
    print("Error: El módulo 'umqtt.simple' no se encuentra.")
    print("Asegúrese de que esté cargado en el sistema de archivos del XBee.")
    # Detiene la ejecución si la librería fundamental no está.
    while True: time.sleep(5)


# --- Configuración General ---
WDT_TIMEOUT = 120000  # Timeout del Watchdog en ms (120 segundos)
COORDINATOR_ID = "XBEE_COORD"

# --- Configuración MQTT ---
MQTT_BROKER_IP = "YOUR_MQTT_BROKER_IP"
MQTT_BROKER_PORT = 8883  # Puerto estándar para MQTT con SSL/TLS
MQTT_USER = "your_mqtt_user"
MQTT_PASSWORD = "your_mqtt_password"
# Tópico para publicar el estado de los sensores. El ID del nodo se añadirá dinámicamente.
# Tópico para publicar mensajes hacia el servidor.
MQTT_PUB_TOPIC = "xbee2server"
# Tópico para recibir comandos desde el servidor.
MQTT_SUB_TOPIC = "server2xbee"

# --- Estados del Dispositivo ---
STATE_STARTUP = 0
STATE_CONNECT_MQTT = 1
STATE_RUNNING = 2
STATE_ERROR = 3

# --- Variables Globales ---
device_state = STATE_STARTUP
wdt = None
net = None
mqtt_client = None
# Diccionario para almacenar el estado de los dispositivos remotos.
# Formato: { eui64: {'node_id': str, 'battery': float, 'last_report_time': int} }
device_database = {}

def feed_watchdog():
    """Alimenta al watchdog para evitar un reinicio del sistema."""
    if wdt:
        wdt.feed()

def get_eui64_by_node_id(node_id):
    """Busca la dirección EUI64 de un dispositivo a partir de su node_id."""
    for eui, data in device_database.items():
        if data.get('node_id') == node_id:
            return eui
    return None

def mqtt_callback(topic, msg):
    """
    Callback que se ejecuta al recibir un mensaje MQTT.
    Procesa los comandos y los retransmite al dispositivo XBee correspondiente.
    """
    feed_watchdog()
    try:
        topic_str = topic.decode('utf-8')
        payload_str = msg.decode('utf-8')
        print("\n[MQTT RX] Tópico: '{}', Payload: '{}'".format(topic_str, payload_str))

        # Formato esperado: "xbee_objetivo;orden" (ej: "XBEE_A;0")
        parts = payload_str.split(';', 1)
        if len(parts) == 2:
            target_node_id, command = parts
            print("Comando para el dispositivo: '{}', Orden: '{}'".format(target_node_id, command))

            # Buscar la dirección EUI64 del dispositivo en la base de datos
            target_eui64 = get_eui64_by_node_id(target_node_id)

            if target_eui64:
                print("Enviando orden '{}' a {} ({})...".format(
                    command, target_node_id, ''.join('{:02x}'.format(b) for b in target_eui64)))
                # Transmitir solo la orden al dispositivo final
                xbee.transmit(target_eui64, command)
                print("Orden enviada con éxito.")
            else:
                print("Error: No se encontró el dispositivo '{}' en la base de datos.".format(target_node_id))
        else:
            print("Advertencia: Payload MQTT no reconocido: {}".format(payload_str))

    except Exception as e:
        print("Error en el callback de MQTT: {}".format(e))

def publish_mqtt_message(topic, message):
    """Publica un mensaje en el broker MQTT."""
    if not mqtt_client:
        print("Error: Cliente MQTT no conectado para publicar.")
        return False
    try:
        feed_watchdog()
        mqtt_client.publish(topic, message)
        print("[MQTT TX] Publicado en '{}': '{}'".format(topic, message))
        return True
    except Exception as e:
        print("Error al publicar en MQTT: {}".format(e))
        global device_state
        device_state = STATE_ERROR # Marcar estado de error para forzar reconexión
        return False

def parse_and_process_xbee_message(msg):
    """Analiza un mensaje XBee, actualiza la BD y publica en MQTT."""
    sender_eui64 = msg['sender_eui64']
    payload_bytes = msg['payload']
    sender_addr_str = ''.join('{:02x}'.format(b).upper() for b in sender_eui64)
    print("\n[XBEE RX] Mensaje de {}".format(sender_addr_str))

    try:
        # Formato esperado: "BATERIA:DATOS" (ej: "4.15:ALERTA! Sensor activado.")
        payload_str = payload_bytes.decode('utf-8')
        parts = payload_str.split(':', 1)
        if len(parts) != 2:
            print("  Payload inválido (formato incorrecto): {}".format(payload_str))
            return

        battery_str, data = parts
        battery = float(battery_str)
        node_id = msg.get('node_id', 'UNKNOWN') # Obtener NI del paquete

        print("  Payload: ID={}, Batería={}V, Datos='{}'".format(node_id, battery, data))

        # Actualizar base de datos local
        current_time = time.ticks_ms()
        device_database[sender_eui64] = {
            'node_id': node_id,
            'battery': battery,
            'last_report_time': current_time
        }

        # Publicar en MQTT con el nuevo formato: "xbee_end;reporte"
        # ej: "XBEE_A;Bateria=4.15V, Status=ALERTA! Sensor activado."
        mqtt_message = "{};Bateria={:.2f}V, Status={}".format(node_id, battery, data)
        publish_mqtt_message(MQTT_PUB_TOPIC, mqtt_message)

    except (ValueError, IndexError) as e:
        print("  Error al analizar payload: {} ({})".format(payload_bytes, e))
    except Exception as e:
        print("  Error procesando mensaje XBee: {}".format(e))


def main_loop():
    """Bucle principal del coordinador."""
    global device_state, wdt, net, mqtt_client

    # Inicialización del Watchdog
    try:
        wdt = WDT(timeout=WDT_TIMEOUT)
        print("Watchdog iniciado ({} ms).".format(WDT_TIMEOUT))
    except Exception as e:
        print("Advertencia: No se pudo iniciar el watchdog. ({})".format(e))

    while True:
        feed_watchdog()
        try:
            if device_state == STATE_STARTUP:
                print("--- Estado: STARTUP (Conectando a la red) ---")
                net = network.WLAN() # o network.Cellular()
                if not net.isconnected():
                    print("Esperando conexión de red...")
                    while not net.isconnected():
                        time.sleep(1)
                        feed_watchdog()
                print("Conectado a la red. IP: {}".format(net.ifconfig()[0]))
                device_state = STATE_CONNECT_MQTT

            elif device_state == STATE_CONNECT_MQTT:
                print("--- Estado: CONNECT_MQTT ---")
                try:
                    if mqtt_client:
                        mqtt_client.disconnect()
                    
                    mqtt_client = MQTTClient(client_id=COORDINATOR_ID,
                                             server=MQTT_BROKER_IP,
                                             port=MQTT_BROKER_PORT,
                                             user=MQTT_USER,
                                             password=MQTT_PASSWORD,
                                             ssl=True)
                    mqtt_client.set_callback(mqtt_callback)
                    mqtt_client.connect()
                    mqtt_client.subscribe(MQTT_SUB_TOPIC)
                    print("Conectado al broker MQTT y suscrito a '{}'".format(MQTT_SUB_TOPIC))
                    # Publica un mensaje de estado del propio coordinador
                    online_message = "{};Status=online".format(COORDINATOR_ID)
                    publish_mqtt_message(MQTT_PUB_TOPIC, online_message)
                    device_state = STATE_RUNNING
                except Exception as e:
                    print("Fallo al conectar con el broker MQTT: {}".format(e))
                    device_state = STATE_ERROR

            elif device_state == STATE_RUNNING:
                # 1. Comprobar mensajes MQTT entrantes (comandos)
                mqtt_client.check_msg()

                # 2. Comprobar mensajes de la red XBee (reportes de sensores)
                received_msg = xbee.receive()
                if received_msg:
                    parse_and_process_xbee_message(received_msg)
                
                # Pequeña pausa para no consumir 100% CPU
                time.sleep_ms(100)

            elif device_state == STATE_ERROR:
                print("--- Estado: ERROR ---")
                print("Reintentando conexión en 15 segundos...")
                time.sleep(15)
                device_state = STATE_STARTUP # Reiniciar el ciclo de conexión

        except Exception as e:
            print("Error inesperado en el bucle principal: {}".format(e))
            device_state = STATE_ERROR
            time.sleep(10)

if __name__ == '__main__':
    main_loop()