import time
from ssd1306 import SSD1306_I2C

# --- Menu Configuration ---
M_OPT = ["", "CAMARA ON", "CAMARA OFF", "CAMARA REPORT"]
M_CMD = ["", "TEL:ON", "TEL:OFF", "TEL:REPORT"]

class MenuHandler:
    def __init__(self, lcd, bat_st_function):
        """Initialize the menu handler with required dependencies"""
        self.lcd = lcd
        self.bat_st = bat_st_function
        
        # Menu state variables
        self.mpos = 0              # Current menu position
        self.mact = False          # Menu active flag
        self.selection_menu = False  # Device selection menu active
        self.last_act = 0          # Last activity timestamp
        self.msg = ""              # Status message
        self.extra_msg = ""        # Additional status message
        
        # Current device tracking
        self.current_device_name = None
        self.current_coordinator_name = None
        
        # Timeouts
        self.T_MENU_TIMEOUT = 60000  # Menu timeout after inactivity (60s)

    def set_device_info(self, device_name, coordinator_name):
        """Set the current device and coordinator names"""
        self.current_device_name = device_name
        self.current_coordinator_name = coordinator_name

    def get_command(self):
        """Get the current command based on menu position"""
        return M_CMD[self.mpos] if 0 <= self.mpos < len(M_CMD) else ""

    def update_message(self, msg, extra=""):
        """Update status messages"""
        self.msg = msg
        if extra:
            self.extra_msg = extra
            
    def reset_messages(self):
        """Reset all messages"""
        self.msg = ""
        self.extra_msg = ""

    def menu_display(self, ops=None, sts=None):
        """Display main menu with options and selection indicator"""
        if ops is None:
            ops = M_OPT
        if sts is None:
            sts = self.msg
            
        self.lcd.fill(0)
        
        # Title
        self.lcd.text("TELEMANDO", 0, 0)
        battery_value = self.bat_st(False)
        battery_text = "{:.1f}V".format(battery_value)
        self.lcd.text(battery_text, self.lcd.width - 40, 0)

        # Separator line
        self.lcd.hline(0, 10, self.lcd.width, 1)
        
        # Menu options - maximum 4 options -> CAMARA_ID ,ON, OFF, REPORT
        for i, op in enumerate(ops):
            if i < 4:
                y = 16 + (i * 8)
                
                if op == "":
                    self.lcd.text("{}".format(self.current_device_name), 8, y)
                    
                # Show menu text
                self.lcd.text(op[:15], 8, y)
                
                # Show selection arrow on the right side
                if i == self.mpos:
                    self.lcd.text(">", self.lcd.width - 10, y)
        
        # Status text at the bottom (two lines)
        if self.extra_msg:
            self.lcd.text(sts[:32], 0, self.lcd.height - 16)
            self.lcd.text(self.extra_msg[:32], 0, self.lcd.height - 8)
        
        if sts and not self.extra_msg:
            self.lcd.text(sts[:32], 32, self.lcd.height - 16)
        
        self.lcd.show()
    
    def device_selection_menu(self, device_names):
        """Display device selection menu"""
        self.lcd.fill(0)
        
        # Title
        self.lcd.text("SELEC. CAMARA", 0, 0)
        # battery_value = self.bat_st(False)
        # battery_text = "{:.1f}V".format(battery_value)
        # self.lcd.text(battery_text, self.lcd.width - 40, 0)

        # Separator line
        self.lcd.hline(0, 10, self.lcd.width, 1)
        
        # Show available devices
        for i, name in enumerate(device_names):
            if i < 5:  # Maximum 5 devices visible at once
                y = 16 + (i * 8)
                self.lcd.text(name, 8, y)
                
                # Mark current selection
                if name == self.current_device_name:
                    self.lcd.text(">", self.lcd.width - 10, y)
        
        self.lcd.show()
    
    def standby_display(self):
        """Display standby screen with battery status"""
        self.lcd.fill(0)
        self.lcd.text("TELEMANDO", 20, 8)
        self.lcd.text(self.bat_st(), 20, 24)
        self.lcd.show()
    
    def handle_button_press(self, button, now, get_device_names, update_device_callback):
        """Handle button presses in the appropriate menu context
        
        Args:
            button: 'UP', 'DOWN', or 'OK' indicating which button was pressed
            now: current timestamp
            get_device_names: function to get list of device names
            update_device_callback: callback to update device selection
            
        Returns:
            tuple: (state_change, new_state) - if state_change is True, main loop 
                  should change to new_state
        """
        self.last_act = now
        
        # Device selection menu is active
        if self.selection_menu:
            device_names = get_device_names()
            current_idx = device_names.index(self.current_device_name)
            
            if button == 'UP':
                # Move selection up
                new_idx = (current_idx - 1) % len(device_names)
                self.current_device_name = device_names[new_idx]
                self.device_selection_menu(device_names)
                return False, None
                
            elif button == 'DOWN':
                # Move selection down
                new_idx = (current_idx + 1) % len(device_names)
                self.current_device_name = device_names[new_idx]
                self.device_selection_menu(device_names)
                return False, None
                
            elif button == 'OK':
                # Confirm selection
                update_device_callback(self.current_device_name)
                self.selection_menu = False
                self.menu_display()
                return False, None
                
        # Main menu is active
        else:
            if not self.mact:
                # If menu not active, activate it
                self.mact = True
                self.menu_display()
                return False, None
                
            if button == 'UP':
                # Move up in menu
                self.mpos = (self.mpos - 1) % len(M_OPT)
                self.menu_display()
                return False, None
                
            elif button == 'DOWN':
                # Move down in menu
                self.mpos = (self.mpos + 1) % len(M_OPT)
                self.menu_display()
                return False, None
                
            elif button == 'OK':
                # Select current option
                if self.mpos == 0:
                    # First option (device selection)
                    self.selection_menu = True
                    self.device_selection_menu(get_device_names())
                    return False, None
                else:
                    # Command option
                    cmd = self.get_command()
                    if cmd:
                        self.msg = "ENVIANDO"
                        self.menu_display()
                        return True, 'CMD'  # Change to command state
        
        return False, None
    
    def check_timeout(self, now):
        """Check if menu should timeout due to inactivity"""
        if self.mact and time.ticks_diff(now, self.last_act) > self.T_MENU_TIMEOUT:
            self.mact = False
            self.standby_display()
            return True
        return False