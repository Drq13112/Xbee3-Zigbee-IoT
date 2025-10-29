// filepath: c:\Users\david\Documents\PlatformIO\Projects\ESP32CAM_XBEE\src\main.cpp
#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  Serial.println("Hello from ESP32-CAM!");
}

void loop() {
  Serial.println("Loop running...");
  delay(1000);
}