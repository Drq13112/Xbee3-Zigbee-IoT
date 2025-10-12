import xbee
import time
from machine import Pin, WDT, ADC

# --- Configuración ---
# Timeout para el Watchdog en milisegundos. 60 segundos.
# El dispositivo se reiniciará si no se alimenta al watchdog en este tiempo.
WDT_TIMEOUT = 60000

adc_battery = ADC('D1')
# ADC reference voltage
AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

# --- Variables Globales ---
# Diccionario para almacenar el estado de los dispositivos remotos.
# Formato: { eui64: {'node_id': str, 'battery': int, 'last_report_time': int, 'movement_count': int} }
device_database = {}

# Inicialización del Watchdog Timer
try:
    wdt = WDT(timeout=WDT_TIMEOUT)
    print("Watchdog timer iniciado con un timeout de {} ms.".format(WDT_TIMEOUT))
except Exception as e:
    wdt = None
    print("Advertencia: No se pudo iniciar el watchdog timer. ({})".format(e))


def feed_watchdog():
    """Alimenta al watchdog para evitar un reinicio del sistema."""
    if wdt:
        wdt.feed()


def parse_payload(payload_bytes):
    """
    Analiza el payload recibido.
    Formato esperado: "ID_NODO:BATERIA:DATOS" (ej: "SENSOR_1:95:MOTION")
    Retorna una tupla (node_id, battery, data) o (None, None, None) si el formato es incorrecto.
    """
    try:
        payload_str = payload_bytes.decode('utf-8')
    except ValueError:
        print("Error al decodificar el payload (no es UTF-8 válido): {}".format(payload_bytes))
        return None, None, None

    try:
        parts = payload_str.split(':')
        if len(parts) != 3:
            print("Error de formato: Se esperaban 3 partes, se recibieron {}: {}".format(len(parts), payload_str))
            return None, None, None

        node_id = parts[0]
        battery = float(parts[1])
        data = parts[2]
        return node_id, battery, data
    except ValueError:
        # Este error puede ocurrir si float(parts[1]) falla.
        print("Error al analizar las partes del payload: {}".format(payload_str))
        return None, None, None


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
    
def update_device_database(sender_eui64, node_id, battery):
    """
    Actualiza la base de datos en memoria con la información del dispositivo.
    """
    current_time = time.ticks_ms()
    if sender_eui64 not in device_database:
        # Si es un dispositivo nuevo, lo inicializamos en la base de datos
        device_database[sender_eui64] = {
            'node_id': node_id,
            'battery': battery,
            'last_report_time': current_time,
            'movement_count': 1
        }
        print("Nuevo dispositivo registrado: {}".format(node_id))
    else:
        # Si el dispositivo ya existe, actualizamos sus datos
        db_entry = device_database[sender_eui64]
        db_entry['node_id'] = node_id  # Actualiza por si cambia
        db_entry['battery'] = battery
        db_entry['last_report_time'] = current_time
        db_entry['movement_count'] += 1
        print("Dispositivo actualizado: {}".format(node_id))

    # Imprime el estado actual de la base de datos para depuración
    print("--- Base de Datos de Dispositivos ---")
    for eui, data in device_database.items():
        eui_str = ''.join('{:02x}'.format(b) for b in eui)
        print("  - {}: ID={}, Bat={}, Reportes={}, UltimaVez={}".format(
            eui_str, data['node_id'], data['battery'], data['movement_count'], data['last_report_time']))
    print("------------------------------------")

    print("Nivel de batería del coordinador: {:.2f}%".format((get_battery_status(as_string=False))))

    print("Número total de dispositivos en la base de datos: {}".format(len(device_database)))
    
    print("------------------------------------")


def send_feedback(recipient_eui64, original_payload):
    """
    Envía un mensaje de feedback (FBK) de vuelta al remitente original.
    """
    try:
        print("Enviando FBK a {}...".format(''.join('{:02x}'.format(b) for b in recipient_eui64)))
        xbee.transmit(recipient_eui64, original_payload)
        print("FBK enviado con éxito.")
    except Exception as e:
        # Un error en la transmisión no debe detener al coordinador
        print("Error al enviar FBK: {}".format(e))


def main_coordinator():
    """
    Bucle principal del coordinador.
    """
    print("\n--- Coordinador XBee iniciado. Esperando mensajes... ---")

    while True:
        feed_watchdog()  # Previene el reinicio por inactividad

        try:
            # Espera a recibir un mensaje
            received_msg = xbee.receive()

            if received_msg:
                sender_eui64 = received_msg['sender_eui64']
                payload = received_msg['payload']
                sender_addr_str = ''.join('{:02x}'.format(b).upper() for b in sender_eui64)

                print("\n>>> Mensaje recibido de {}".format(sender_addr_str))

                # 1. Analizar el payload
                node_id, battery, data = parse_payload(payload)

                if node_id and data:
                    # 2. Si el payload es válido, actualizar la base de datos
                    print("  Payload: ID={}, Batería={}, Datos={}".format(node_id, battery, data))
                    update_device_database(sender_eui64, node_id, battery)

                    answer = "OK"
                    # 3. Enviar un feedback (FBK) de vuelta al remitente
                    send_feedback(sender_eui64, answer)
                else:
                    print("Payload inválido o malformado recibido: {}".format(payload))

        except Exception as e:
            print("Error en el bucle de recepción: {}".format(e))
            # Espera un poco antes de continuar para no sobrecargar en caso de errores repetidos
            time.sleep_ms(1000)

        # Pequeña pausa para no consumir el 100% de la CPU
        time.sleep_ms(100)


if __name__ == '__main__':
    while True:
        try:
            main_coordinator()
        except Exception as e:
            print("\n¡¡¡ERROR CRÍTICO EN EL BUCLE PRINCIPAL!!!: {}".format(e))
            print("El sistema se reiniciará en 5 segundos...")
            time.sleep(5)
            # machine.reset()