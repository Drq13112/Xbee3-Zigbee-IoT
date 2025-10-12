from machine import Pin, WDT, ADC, I2C
import time
import xbee
# Import SSD1306 directly
from ssd1306 import SSD1306_I2C
from sys import stdin, stdout


# --- Config ---
C_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8B\x99'
D_ADDR = b'\x00\x13\xA2\x00\x42\x3D\x8A\xAC'
DID = "XBEE_TELEMANDO"

# --- Timers ---
T_SLEEP = 900000     # 15 min
T_RETRY = 1000       # 1 segundo
T_WDT = 10000        # 10 segundos
T_DEB = 100          # debounce

# --- Pines ---
bUP = Pin('D2', Pin.IN, Pin.PULL_UP)
bOK = Pin('D3', Pin.IN, Pin.PULL_UP)
bDN = Pin('D4', Pin.IN, Pin.PULL_UP)
bat = ADC('D1')

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
mpos = 0
mact = False
msg = ""
last_act = 0
uart = None  # Para comandos seriales
extra_msg = ""  # For additional status line


# --- Menu ---
M_OPT = ["CAMARA ON", "CAMARA OFF", "CAMARA REPORT"]
M_CMD = ["TEL:ON", "TEL:OFF", "TEL:REPORT"]

# --- Display functions ---
def menu_display(lcd, ops, pos, sts=""):
    """Display menu with options and selection indicator"""
    global extra_msg
    lcd.fill(0)
    
    # Title
    lcd.text("TELEMANDO", 0, 0)
    lcd.text("{:.1f}V".format(bat_st(False)), lcd.width - 40, 0)

    # Separator line
    lcd.hline(0, 10, lcd.width, 1)
    
    # Menu options - maximum 4 options
    for i, op in enumerate(ops):
        if i < 3:
            y = 16 + (i * 8)
            
            # Show menu text
            lcd.text(op[:15], 8, y)
            
            # Show selection arrow on the right side
            if i == pos:
                lcd.text(">", lcd.width - 10, y)
    
    # Status text at the bottom (two lines)
    if extra_msg:
        lcd.text(sts[:32], 0, lcd.height - 16)
        lcd.text(extra_msg[:32], 0, lcd.height - 8)
    
    if sts and not extra_msg:
        lcd.text(sts[:32], 32, lcd.height - 16)
        lcd.text(extra_msg[:32], 0, lcd.height - 8)
        
    lcd.show()

def standby_display(lcd, bat):
    """Display standby screen with battery status"""
    lcd.fill(0)
    lcd.text("TELEMANDO", 20, 8)
    lcd.text(bat, 20, 24)
    lcd.show()

# --- Funciones ---
def bat_st(as_string=True):
    try:
        ref = 2.5
        raw = bat.read()
        v = (raw / 4095.0) * ref * (12.0 / 3.3) * 2.9
        
        if as_string:
            return "BAT:{:.1f}V".format(v)
        else:
            return v
    except:
        return "BAT: ERR" if as_string else 0.0

def net_ok():
    try:
        ai = xbee.atcmd("AI")
        return ai == 0
    except Exception as e:
        return False

def send(addr, mensaje, wait=False, retry=1):
    global w, msg, extra_msg
    extra_msg = ""  # Reset extra message
    if not net_ok():
        msg = "NO RED"
        return False
    
    start = time.ticks_ms()
    for att in range(retry):
        try:
            w.feed()
            print("Enviando: {} a {}".format(mensaje, [hex(b) for b in addr]))
            xbee.transmit(addr, mensaje.encode('utf-8'))
            
            if not wait:
                msg = "OK"
                return True
            
            t_start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t_start) < T_RETRY:
                w.feed()
                rx = xbee.receive()
                if rx and rx['sender_eui64'] == addr:
                    try:
                        payload = rx['payload'].decode('utf-8')
                    except UnicodeError:
                        payload = "" # Or handle the error as you see fit
                    print("Recibido: {}".format(payload))
                    
                    # Parse payload for relevant info
                    parts = payload.split(', ')
                    camara = ""
                    bateria = ""
                    for part in parts:
                        if part.startswith('Camara:'):
                            camara = part
                        elif part.startswith('Bateria:'):
                            bateria = part
                    
                    msg = camara if camara else "ACK OK"
                    extra_msg = bateria if bateria else ""
                    
                    return True
                time.sleep_ms(10)
                
                if time.ticks_diff(time.ticks_ms(), start) > 5000:
                    msg = "TIMEOUT"
                    return False
                
            msg = "NO ACK"
            
        except Exception as e:
            w.feed()
            print("Error: {}".format(e))
            msg = "ERR"
            
        if att < retry - 1:
            w.feed()
            time.sleep_ms(250)
    
    msg = "FALLO"
    return False

def main():
    global state, w, last, cmd, mpos, mact, msg, last_act, uart, extra_msg
    
    try:
        # Init HW
        w = WDT(timeout=T_WDT)
        w.feed()
        did = xbee.atcmd('NI') or DID
        
        # No need for UART init, using sys.stdin for console
        
        # Initialize I2C with explicit pins and frequency
        i2c = I2C(1)  # Use 400kHz standard frequency
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
        # Power off
        lcd.write_cmd(0xAE)  # SET_DISP | 0x00
        time.sleep_ms(100)
        # Power on
        lcd.write_cmd(0xAF)  # SET_DISP | 0x01
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
        
        # Force menu to be active from start
        mact = True
        if not net_ok():
            msg = "RED ERROR"
        else:
            msg = "RED OK"
        menu_display(lcd, M_OPT, mpos, msg)
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
                    send(C_ADDR, "{}:{:.1f}:INICIO".format(did, bat_st(False)), False)
                else:
                    lcd.fill(0)
                    lcd.text("RED ERROR", 30, 16)
                    lcd.show()
                state = S_IDLE
                    
            elif state == S_IDLE:
                if not mact:
                    standby_display(lcd, bat_st())
                else:
                    # Always refresh the menu when active
                    menu_display(lcd, M_OPT, mpos, msg)
                
                t_start = time.ticks_ms()
                
                while time.ticks_diff(time.ticks_ms(), t_start) < T_SLEEP:
                    w.feed()
                    now = time.ticks_ms()
                    
                    # Auto exit menu after inactivity
                    if mact and time.ticks_diff(now, last_act) > 60000:
                        mact = False
                        standby_display(lcd, bat_st())
                        
                    if not net_ok():
                        msg = "RED ERROR"
                    else:
                        msg = "RED OK"
                    
                    # Serial command simulation (from XCTU terminal)
                    try:
                        serial_cmd = stdin.read()  # Non-blocking read
                        if serial_cmd:
                            serial_cmd = serial_cmd.upper()
                            if 'U' in serial_cmd:
                                last = now
                                last_act = now
                                if not mact:
                                    mact = True
                                else:
                                    mpos = (mpos - 1) % len(M_OPT)
                                extra_msg = ""  # Reset extra message
                                menu_display(lcd, M_OPT, mpos, msg)
                            elif 'O' in serial_cmd:
                                last = now
                                last_act = now
                                if mact:
                                    cmd = M_CMD[mpos]
                                    state = S_CMD
                                    msg = "ENVIANDO"
                                    extra_msg = ""  # Reset extra message
                                    menu_display(lcd, M_OPT, mpos, msg)
                                    break
                                else:
                                    mact = True
                                    menu_display(lcd, M_OPT, mpos, msg)
                            elif 'D' in serial_cmd:
                                last = now
                                last_act = now
                                if not mact:
                                    mact = True
                                else:
                                    mpos = (mpos + 1) % len(M_OPT)
                                extra_msg = ""  # Reset extra message
                                menu_display(lcd, M_OPT, mpos, msg)
                    except:
                        pass
                    
                    # Button handling
                    if time.ticks_diff(now, last) > T_DEB:
                        if bUP.value() == 0:
                            last = now
                            last_act = now
                            
                            if not mact:
                                mact = True
                            else:
                                mpos = (mpos - 1) % len(M_OPT)
                            
                            menu_display(lcd, M_OPT, mpos, msg)
                            time.sleep_ms(T_DEB)
                            
                        elif bDN.value() == 0:
                            last = now
                            last_act = now
                            
                            if not mact:
                                mact = True
                            else:
                                mpos = (mpos + 1) % len(M_OPT)
                            
                            menu_display(lcd, M_OPT, mpos, msg)
                            time.sleep_ms(T_DEB)
                            
                        elif bOK.value() == 0:
                            last = now
                            last_act = now
                            
                            if mact:
                                cmd = M_CMD[mpos]
                                state = S_CMD
                                msg = "ENVIANDO"
                                menu_display(lcd, M_OPT, mpos, msg)
                                break
                            else:
                                mact = True
                                menu_display(lcd, M_OPT, mpos, msg)
                            
                            time.sleep_ms(T_DEB)
                    
                    time.sleep_ms(50)
                    
                    if time.ticks_diff(time.ticks_ms(), t_start) >= T_SLEEP:
                        break

                if state == S_IDLE and time.ticks_diff(time.ticks_ms(), t_start) >= T_SLEEP:
                    state = S_REP
                
            elif state == S_CMD:
                menu_display(lcd, M_OPT, mpos, "ENVIANDO")
                w.feed()
                
                if not net_ok():
                    menu_display(lcd, M_OPT, mpos, "RED ERROR")
                    time.sleep_ms(1000)
                    state = S_IDLE
                    continue
                
                send(D_ADDR, cmd, True)
                menu_display(lcd, M_OPT, mpos, msg)
                
                state = S_IDLE
                cmd = ""
                time.sleep_ms(1000)
                w.feed()

            elif state == S_REP:
                w.feed()
                message = "{}:{:.1f}:REPORTE".format(did, bat_st(False))
                
                if mact:
                    menu_display(lcd, M_OPT, mpos, "REPORTE")
                else:
                    standby_display(lcd, "REPORTE")
                
                if not net_ok():
                    msg = "RED ERROR"
                    state = S_IDLE
                    continue
                    
                send(C_ADDR, message, False)
                
                state = S_IDLE
                time.sleep_ms(1000)
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
                lcd.text("ERROR", 0, 8)
                lcd.show()
            except:
                pass
            time.sleep_ms(1000)
            state = S_IDLE

if __name__ == '__main__':
    main()