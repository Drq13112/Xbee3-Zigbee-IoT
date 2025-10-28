from machine import Pin, WDT, ADC, I2C
import time
import xbee
# Import SSD1306 directly
from ssd1306 import SSD1306_I2C
from sys import stdin, stdout

from xbee_devices import COORDINATORS, DEVICES, DEFAULT_DID
from xbee_devices import get_device_names, get_coordinator_names
from menu_handler import MenuHandler

# --- Config ---
# Instead of hardcoded addresses, use the current selected device
current_device_name = get_device_names()[0]  # Start with first device
current_coordinator_name = get_coordinator_names()[0]  # Start with first coordinator

# These variables will be updated when user selects a different device
C_ADDR = COORDINATORS[current_coordinator_name]
D_ADDR = DEVICES[current_device_name]
DID = DEFAULT_DID

# --- Timers ---
T_SLEEP = 900000     # 15 min
T_RETRY = 100       # 100 milisegundos
T_WDT = 10000        # 10 segundos
T_DEB = 20          # debounce

# --- Pines ---
bUP = Pin('D5', Pin.IN, Pin.PULL_UP)
bOK = Pin('D9', Pin.IN, Pin.PULL_UP)
bDN = Pin('D7', Pin.IN, Pin.PULL_UP)
bat = ADC('D0')

# ADC reference voltage
AV_VALUES = {0: 1.25, 1: 2.5, 2: 3.3, None: 2.5}

# --- Estados ---
S_INIT = 0
S_IDLE = 1
S_REP = 2
S_CMD = 3
S_ERR = 4

# --- Vars ---
state = S_INIT
w = None
last = 0
cmd = ""
msg = ""
last_act = 0
uart = None  # Para comandos seriales

# --- Funciones ---
def bat_st(as_string=True):
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
        adc_raw_value = bat.read()
        
        # Calcular el voltaje en el pin.
        pin_voltage = (adc_raw_value / 4095.0) * reference_v
        
        # Aplicar el factor de escala del divisor de voltaje (12V / 3.3V).
        battery_voltage = pin_voltage * (12.0 / 3.3) * 2.9 # Factor de corrección para divisor 12k+3.3k
        
        if as_string:
            # Formatear el resultado a dos decimales.
            return "Bateria: {:.2f}V".format(battery_voltage)
        else:
            return battery_voltage
    except Exception as e:
        print("Error al leer la bateria: {}".format(e))
        return "Bateria: ERROR" if as_string else 0.0

def update_device(device_name):
    """Update current device and its address"""
    global current_device_name, D_ADDR
    current_device_name = device_name
    D_ADDR = DEVICES[current_device_name]

def net_ok():
    try:
        ai = xbee.atcmd("AI")
        return ai == 0
    except Exception as e:
        return False

def send_message(target_addr, message):
    """
    Envía un mensaje sin esperar confirmación.
    """
    w.feed()  # Usar watchdog global
    try:
        xbee.transmit(target_addr, message)
        w.feed()
        return True
    except Exception as e:
        w.feed()
        print("Error al enviar mensaje: {}".format(e))
        return False

def safe_send_and_wait_ack(target_addr, message, retries=3):
    """
    Envía un mensaje y espera un ACK del destinatario.
    Reintenta hasta 'retries' veces si no recibe confirmación.
    """
    w.feed()
    respuesta_recibida = False
    for attempt in range(retries):
        try:
            print("Enviando con ACK (intento {}/{}) '{}'".format(attempt + 1, retries, message))
            xbee.transmit(target_addr, message)
            
            # Esperar feedback
            start_wait = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start_wait) < 3000:  # HEARING_INTERVAL_MS = 3000
                w.feed()
                receivedg = xbee.receive()
                if receivedg and receivedg['sender_eui64'] == target_addr:
                    payload = receivedg['payload'].decode('utf-8')
                    print("Recibido: '{}'".format(payload))
                    respuesta_recibida = True
                    return True
                time.sleep_ms(100)  # SLEEP_DURATION_MS = 100
            if not respuesta_recibida:
                print("No se recibió confirmacion en el tiempo esperado.")
        except Exception as e:
            w.feed()
            print("Error al transmitir/recibir: {}".format(e))
        if attempt < retries - 1:
            w.feed()
            print("Reintentando en {} segundos...".format(1))  # RETRY_DELAY_MS / 1000 = 1
            time.sleep_ms(1000)  # RETRY_DELAY_MS = 1000
    print("Fallo al enviar y confirmar mensaje tras varios reintentos.")
    return False

def send(addr, mensaje, wait=False, retry=1):
    global w, menu_handler
    menu_handler.extra_msg = ""  # Reset extra message
    if not net_ok():
        menu_handler.msg = "NO RED"
        return False
    
    if not wait:
        # Usar send_message para envío sin ACK
        return send_message(addr, mensaje.encode('utf-8'))
    else:
        # Usar safe_send_and_wait_ack para envío con ACK
        return safe_send_and_wait_ack(addr, mensaje.encode('utf-8'), retries=retry)

def main():
    global state, w, last, cmd, last_act, uart, menu_handler
    
    try:
        # Init HW
        w = WDT(timeout=T_WDT)
        w.feed()
        did = xbee.atcmd('NI') or DID
        
        # Initialize I2C with explicit pins and frequency
        i2c = I2C(1, freq=400000)  # Use 400kHz standard frequency
        time.sleep_ms(100)  # Allow I2C to stabilize
        
        print("Scanning I2C bus...")
        devs = i2c.scan()
        print("I2C devices found:", [hex(d) for d in devs])
        
        if not devs:
            print("No I2C devices")
            return
        
        # Create LCD with more explicit initialization
        lcd = SSD1306_I2C(128, 64, i2c)
        
        # Manual reset sequence for OLED
        lcd.write_cmd(0xAE)  # Power off
        time.sleep_ms(100)
        lcd.write_cmd(0xAF)  # Power on
        time.sleep_ms(100)
        
        # Re-initialize
        lcd.contrast(255)
        lcd.invert(0)
        
        # Clear and test display
        lcd.fill(0)
        lcd.show()
        time.sleep_ms(100)
        
        # Test pattern
        lcd.fill(0)
        lcd.text("INICIANDO", 20, 14)
        lcd.show()
        time.sleep_ms(1000)
        w.feed()
        
        # Initialize menu handler
        menu_handler = MenuHandler(lcd, bat_st)
        menu_handler.set_device_info(current_device_name, current_coordinator_name)
        menu_handler.mact = True  # Force menu to be active from start
        
        if not net_ok():
            menu_handler.msg = "RED ERROR"
        else:
            menu_handler.msg = "RED OK"
            
        menu_handler.menu_display()
        time.sleep_ms(500)
        w.feed()
        
    except Exception as e:
        print("Err: {}".format(e))
        if w is None:
            w = WDT(timeout=T_WDT)
        return

    # Main loop
    while True:
        try:
            w.feed()

            # FSM
            if state == S_INIT:
                if net_ok():
                    lcd.fill(0)
                    lcd.text("RED OK", 30, 16)
                    lcd.show()
                    time.sleep_ms(500)
                    send(C_ADDR, did+":"+str(int(bat_st(False)))+":INICIO", False)
                else:
                    lcd.fill(0)
                    lcd.text("RED ERROR", 30, 16)
                    lcd.show()
                state = S_IDLE
                    
            elif state == S_CMD:
                menu_handler.msg = "ENVIANDO"
                menu_handler.menu_display()
                w.feed()
                
                
                # Update last activity to prevent menu timeout
                menu_handler.last_act = time.ticks_ms()
                
                send(D_ADDR, cmd, True)
                menu_handler.menu_display()
                
                state = S_IDLE
                cmd = ""
                w.feed()
                
            elif state == S_IDLE:
                if not menu_handler.mact:
                    menu_handler.standby_display()
                else:
                    # Always refresh the menu when active
                    if menu_handler.selection_menu:
                        menu_handler.device_selection_menu(get_device_names())
                    else:
                        menu_handler.menu_display()
                
                t_start = time.ticks_ms()
                
                while time.ticks_diff(time.ticks_ms(), t_start) < T_SLEEP:
                    w.feed()
                    now = time.ticks_ms()
                    
                    # Auto exit menu after inactivity
                    # menu_handler.check_timeout(now)
                    
                    if time.ticks_diff(now, last) > T_DEB:
                        if bUP.value() == 0:
                            last = now
                            state_change, new_state = menu_handler.handle_button_press('UP', now, get_device_names, update_device)
                            if state_change:
                                state = S_CMD if new_state == 'CMD' else S_IDLE
                                cmd = menu_handler.get_command()
                                break
                            # time.sleep_ms(T_DEB)
                            
                        elif bDN.value() == 0:
                            last = now
                            state_change, new_state = menu_handler.handle_button_press('DOWN', now, get_device_names, update_device)
                            if state_change:
                                state = S_CMD if new_state == 'CMD' else S_IDLE
                                cmd = menu_handler.get_command()
                                break
                            # time.sleep_ms(T_DEB)
                            
                        elif bOK.value() == 0:
                            last = now
                            state_change, new_state = menu_handler.handle_button_press('OK', now, get_device_names, update_device)
                            if state_change:
                                state = S_CMD if new_state == 'CMD' else S_IDLE
                                cmd = menu_handler.get_command()
                                break
                            # time.sleep_ms(T_DEB)
                
                    time.sleep_ms(50)
                    
                    if time.ticks_diff(time.ticks_ms(), t_start) >= T_SLEEP:
                        break

                # if state == S_IDLE and time.ticks_diff(time.ticks_ms(), t_start) >= T_SLEEP:
                #     state = S_REP
                
            elif state == S_REP:
                w.feed()
                message = "{}:{:.1f}:REPORTE".format(did, bat_st(False))
                
                if menu_handler.mact:
                    menu_handler.msg = "REPORTE"
                    menu_handler.menu_display()
                else:
                    menu_handler.standby_display()
                
                if not net_ok():
                    menu_handler.msg = "RED ERROR"
                    state = S_IDLE
                    continue
                    
                send(C_ADDR, message, False)
                
                state = S_IDLE
                # time.sleep_ms(20)
                w.feed()

            elif state == S_ERR:
                w.feed()
                lcd.fill(0)
                lcd.text("ERROR", 40, 8)
                lcd.show()
                time.sleep_ms(2000)
                state = S_IDLE

        except Exception as e:
            w.feed()
            print("Err: {}".format(e))
            try:
                lcd.fill(0)
                lcd.text("ERROR SISTEMA", 0, 8)
                lcd.show()
            except:
                pass
            time.sleep_ms(1000)
            state = S_IDLE

if __name__ == '__main__':
    main()