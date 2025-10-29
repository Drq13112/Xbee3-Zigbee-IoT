#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <WiFiClientSecure.h>

// WiFi settings
const char* WIFI_SSID = "Your_WiFi_SSID";
const char* WIFI_PASSWORD = "Your_WiFi_Password";

// MQTT Broker settings (remote public IP and exposed port)
const char* MQTT_BROKER_IP = "broker_public_ip";  // e.g., "203.0.113.1"
const int MQTT_PORT = 8883;  // TLS port
const char* MQTT_USER = "your_mqtt_username";  // Optional
const char* MQTT_PASSWORD = "your_mqtt_password";  // Optional
const char* MQTT_CLIENT_ID = "ESP32_Client";

// MQTT Topics
const char* TOPIC_REPORTS = "xbee/reports";  // Publish reports here
const char* TOPIC_COMMANDS = "esp32/commands";  // Subscribe for commands (optional)

// TLS Certificates (replace with your actual certificates)
const char* CA_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
# Your CA Certificate here
-----END CERTIFICATE-----
)EOF";

const char* CLIENT_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
# Your Client Certificate here
-----END CERTIFICATE-----
)EOF";

const char* CLIENT_KEY = R"EOF(
-----BEGIN PRIVATE KEY-----
# Your Client Private Key here
-----END PRIVATE KEY-----
)EOF";

// Serial communication settings
#define SERIAL_BAUD 9600
#define COMMAND_INTERVAL 10000

// Buffer for incoming serial data
String serialBuffer = "";
unsigned long lastCommandTime = 0;

// MQTT and WiFi clients
WiFiClientSecure wifiClient;
PubSubClient mqttClient(wifiClient);

// Function to connect to WiFi
void connectWiFi() {
  Serial.print("Connecting to WiFi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println(" Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

// Function to connect to MQTT broker
void connectMQTT() {
  wifiClient.setCACert(CA_CERT);
  wifiClient.setCertificate(CLIENT_CERT);
  wifiClient.setPrivateKey(CLIENT_KEY);
  
  mqttClient.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);  // For incoming MQTT messages
  
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT...");
    if (mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASSWORD)) {
      Serial.println(" Connected!");
      mqttClient.subscribe(TOPIC_COMMANDS);  // Subscribe to commands topic
    } else {
      Serial.print(" Failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" Retrying in 5 seconds...");
      delay(5000);
    }
  }
}

// MQTT callback for incoming messages (optional: handle commands)
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.print("MQTT Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);
  // TODO: Parse and send to XBee if it's a command (e.g., "REPORT:SENSOR_1")
}

// Function to send a command to XBee
void sendCommandToXBee(String command) {
  Serial.println(command);
  Serial.print("Sent to XBee: ");
  Serial.println(command);
}

// Function to parse and handle incoming message from XBee
void handleXBeeMessage(String message) {
  message.trim();
  if (message.length() == 0) return;
  
  Serial.print("Received from XBee: ");
  Serial.println(message);
  
  // Parse message (split by ':')
  int firstColon = message.indexOf(':');
  if (firstColon == -1) {
    Serial.println("Invalid message format");
    return;
  }
  
  String msgType = message.substring(0, firstColon);
  String payload = message.substring(firstColon + 1);
  
  if (msgType == "REPORT") {
    // Publish report to MQTT
    if (mqttClient.publish(TOPIC_REPORTS, message.c_str())) {
      Serial.println("Report published to MQTT");
    } else {
      Serial.println("Failed to publish report");
    }
    
    // Also handle locally (as before)
    int secondColon = payload.indexOf(':');
    if (secondColon != -1) {
      String nodeId = payload.substring(0, secondColon);
      String rest = payload.substring(secondColon + 1);
      int thirdColon = rest.indexOf(':');
      if (thirdColon != -1) {
        String battery = rest.substring(0, thirdColon);
        String data = rest.substring(thirdColon + 1);
        Serial.print("Report from ");
        Serial.print(nodeId);
        Serial.print(" - Battery: ");
        Serial.print(battery);
        Serial.print(" - Data: ");
        Serial.println(data);
        // TODO: Send to cellular network if needed
      }
    }
  } else if (msgType == "REPORT_RESPONSE") {
    Serial.print("Report Response: ");
    Serial.println(payload);
  } else if (msgType == "CAMERA_RESPONSE") {
    Serial.print("Camera Response: ");
    Serial.println(payload);
  } else if (msgType.startsWith("ERROR")) {
    Serial.print("Error from XBee: ");
    Serial.println(payload);
  } else {
    Serial.println("Unknown message type");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial) {
    delay(10);
  }
  Serial.println("ESP32 ready...");
  
  connectWiFi();
  connectMQTT();
}

void loop() {
  // Maintain MQTT connection
  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();
  
  // Read incoming serial data from XBee
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      handleXBeeMessage(serialBuffer);
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }
  
  // Periodically send test commands to XBee
  if (millis() - lastCommandTime > COMMAND_INTERVAL) {
    sendCommandToXBee("REPORT:SENSOR_1");
    delay(1000);
    sendCommandToXBee("CAMERA:SENSOR_1:ON");
    lastCommandTime = millis();
  }
  
  delay(100);
}