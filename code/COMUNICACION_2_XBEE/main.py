import time
from sys import stdin, stdout
from machine import Pin

last_press = 0
debounce_time = 5000  # ms

while True:
    # Check for button press to send "hola"
    if time.ticks_diff(time.ticks_ms(), last_press) > debounce_time:
        stdout.write("hola desde xbee2\n")
        last_press = time.ticks_ms()
    
    try:
        serial_cmd = stdin.read()
        if serial_cmd:
            line = serial_cmd.strip()
            if line == "hola desde xbee1":
                stdout.write("hola recibido en xbee2\n")
                print("Mensaje recibido: ", line)
    except:
        pass  # Handle any read errors gracefully
    time.sleep(0.1)  # Small delay to avoid busy looping