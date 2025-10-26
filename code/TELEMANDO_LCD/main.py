from machine import Pin, WDT, ADC, I2C
import time
import xbee
from ssd1306 import SSD1306_I2C
from sys import stdin, stdout

from xbee_devices import COORDINATORS, DEVICES, DEFAULT_DID
from xbee_devices import get_device_names, get_coordinator_names
from menu_handler import MenuHandler
import tools

class Telemand(tools.XBeeDevice):
    """Subclase del telemando que hereda de XBeeDevice."""
    
    # Estados específicos del telemando
    S_INIT = 0
    S_IDLE = 1
    S_REP = 2
    S_CMD = 3
    S_ERR = 4
    
    def __init__(self):
        # Inicializar padre con parámetros específicos
        super().__init__(device_id="TELEMANDO", wdt_timeout=10000, battery_pin='D0', battery_scaling_factor=2.9)
        
        # Variables específicas del telemando
        self.state = self.S_INIT
        self.last = 0
        self.cmd = ""
        self.msg = ""
        self.last_act = 0
        self.current_device_name = get_device_names()[0]
        self.current_coordinator_name = get_coordinator_names()[0]
        self.C_ADDR = COORDINATORS[self.current_coordinator_name]
        self.D_ADDR = DEVICES[self.current_device_name]
        self.DID = DEFAULT_DID
        
        # Pines específicos
        self.bUP = Pin('D5', Pin.IN, Pin.PULL_UP)
        self.bOK = Pin('D9', Pin.IN, Pin.PULL_UP)
        self.bDN = Pin('D7', Pin.IN, Pin.PULL_UP)
        
        # LCD y menú
        self.i2c = None
        self.lcd = None
        self.menu_handler = None
        
        # Timers
        self.T_SLEEP = 900000
        self.T_RETRY = 100
        self.T_DEB = 20
    
    def init_hardware(self):
        """Inicializa hardware específico: LCD, menú, etc."""
        try:
            self.feed_watchdog()
            did = self.xbee_.atcmd('NI') or self.DID
            
            # Inicializar I2C
            self.i2c = I2C(1)
            time.sleep_ms(100)
            devs = self.i2c.scan()
            if not devs:
                raise Exception("No I2C devices found")
            
            # Inicializar LCD
            self.lcd = SSD1306_I2C(128, 64, self.i2c)
            self.lcd.write_cmd(0xAE)
            time.sleep_ms(100)
            self.lcd.write_cmd(0xAF)
            time.sleep_ms(100)
            self.lcd.contrast(255)
            self.lcd.invert(0)
            self.lcd.fill(0)
            self.lcd.show()
            
            # Inicializar menú
            self.menu_handler = MenuHandler(self.lcd, self.get_battery_status)
            self.menu_handler.set_device_info(self.current_device_name, self.current_coordinator_name)
            self.menu_handler.mact = True
            
            return did
        except Exception as e:
            print("Error initializing hardware: {}".format(e))
            return None
    
    def update_device(self, device_name):
        """Actualiza dispositivo seleccionado."""
        self.current_device_name = device_name
        self.D_ADDR = DEVICES[self.current_device_name]
    
    def net_ok(self):
        """Verifica conexión de red."""
        try:
            ai = self.xbee_.atcmd("AI")
            return ai == 0
        except Exception:
            return False
    
    def send_command(self, addr, message, wait=False, retry=1):
        """Envía comando usando métodos del padre."""
        self.menu_handler.extra_msg = ""
        if not self.net_ok():
            self.menu_handler.msg = "NO RED"
            return False
        
        try:
            self.feed_watchdog()
            print("Enviando: {} a {}".format(message, [hex(b) for b in addr]))
            if wait:
                return self.safe_send_and_wait_ack(addr, message.encode('utf-8'))
            else:
                return self.safe_send(addr, message.encode('utf-8'))
        except Exception as e:
                self.feed_watchdog()
                print("Error: {}".format(e))
                self.menu_handler.msg = "ERR"
        
        self.menu_handler.msg = "FALLO"
        return False
    
    def handle_buttons(self, now):
        """Maneja pulsaciones de botones."""
        if time.ticks_diff(now, self.last) > self.T_DEB:
            if self.bUP.value() == 0:
                self.last = now
                state_change, new_state = self.menu_handler.handle_button_press('UP', now, get_device_names, self.update_device)
                if state_change:
                    self.state = self.S_CMD if new_state == 'CMD' else self.S_IDLE
                    self.cmd = self.menu_handler.get_command()
                    return True
                time.sleep_ms(self.T_DEB)
            elif self.bDN.value() == 0:
                self.last = now
                state_change, new_state = self.menu_handler.handle_button_press('DOWN', now, get_device_names, self.update_device)
                if state_change:
                    self.state = self.S_CMD if new_state == 'CMD' else self.S_IDLE
                    self.cmd = self.menu_handler.get_command()
                    return True
                time.sleep_ms(self.T_DEB)
            elif self.bOK.value() == 0:
                self.last = now
                state_change, new_state = self.menu_handler.handle_button_press('OK', now, get_device_names, self.update_device)
                if state_change:
                    self.state = self.S_CMD if new_state == 'CMD' else self.S_IDLE
                    self.cmd = self.menu_handler.get_command()
                    return True
                time.sleep_ms(self.T_DEB)
        return False
    
    def run(self):
        """Bucle principal FSM."""
        self.setup()  # Inicializar padre
        did = self.init_hardware()
        if not did:
            return
        
        while True:
            try:
                self.feed_watchdog()
                
                if self.state == self.S_INIT:
                    if self.net_ok():
                        self.lcd.fill(0)
                        self.lcd.text("RED OK", 30, 16)
                        self.lcd.show()
                        time.sleep_ms(500)
                        self.send_command(self.C_ADDR, did + ":" + str(int(self.get_battery_status(False))) + ":INICIO", False)
                    else:
                        self.lcd.fill(0)
                        self.lcd.text("RED ERROR", 30, 16)
                        self.lcd.show()
                    self.state = self.S_IDLE
                    
                elif self.state == self.S_CMD:
                    self.menu_handler.msg = "ENVIANDO"
                    self.menu_handler.menu_display()
                    self.feed_watchdog()
                    self.menu_handler.last_act = time.ticks_ms()
                    self.send_command(self.D_ADDR, self.cmd, True)
                    self.menu_handler.menu_display()
                    self.state = self.S_IDLE
                    self.cmd = ""
                    time.sleep_ms(20)
                    
                elif self.state == self.S_IDLE:
                    if not self.menu_handler.mact:
                        self.menu_handler.standby_display()
                    else:
                        if self.menu_handler.selection_menu:
                            self.menu_handler.device_selection_menu(get_device_names())
                        else:
                            self.menu_handler.menu_display()
                    
                    t_start = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), t_start) < self.T_SLEEP:
                        self.feed_watchdog()
                        now = time.ticks_ms()
                        self.menu_handler.check_timeout(now)
                        
                        print("UP: {}, OK: {}, DN: {}".format(self.bUP.value(), self.bOK.value(), self.bDN.value()))
                        if self.handle_buttons(now):
                            break
                        
                        time.sleep_ms(50)
                        if time.ticks_diff(time.ticks_ms(), t_start) >= self.T_SLEEP:
                            break
                    
                    if self.state == self.S_IDLE and time.ticks_diff(time.ticks_ms(), t_start) >= self.T_SLEEP:
                        self.state = self.S_REP
                    
                elif self.state == self.S_REP:
                    self.feed_watchdog()
                    message = "{}:{:.1f}:REPORTE".format(did, self.get_battery_status(False))
                    
                    if self.menu_handler.mact:
                        self.menu_handler.msg = "REPORTE"
                        self.menu_handler.menu_display()
                    else:
                        self.menu_handler.standby_display()
                    
                    if not self.net_ok():
                        self.menu_handler.msg = "RED ERROR"
                        self.state = self.S_IDLE
                        continue
                    
                    self.send_command(self.C_ADDR, message, False)
                    self.state = self.S_IDLE
                    time.sleep_ms(20)
                    
                elif self.state == self.S_ERR:
                    self.feed_watchdog()
                    self.lcd.fill(0)
                    self.lcd.text("ERROR", 40, 8)
                    self.lcd.show()
                    time.sleep_ms(2000)
                    self.state = self.S_IDLE
                    
            except Exception as e:
                self.feed_watchdog()
                print("Err: {}".format(e))
                try:
                    self.lcd.fill(0)
                    self.lcd.text("ERROR SISTEMA", 0, 8)
                    self.lcd.show()
                except:
                    pass
                time.sleep_ms(1000)
                self.state = self.S_IDLE

# --- Lógica Principal ---
if __name__ == '__main__':
    telemand = Telemand()
    telemand.run()