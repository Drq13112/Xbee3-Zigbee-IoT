# Sistema de Comunicación Zigbee con XBee3 y ESP32

![Interfaz del Telemando LCD](assets/lcd_2.png)

## Descripción

Este proyecto implementa un sistema avanzado de comunicación inalámbrica utilizando módulos XBee3 con MicroPython, integrado con un ESP32 para conectividad celular y MQTT remoto. El sistema permite el control remoto de dispositivos IoT (como cámaras) a través de una red Zigbee, con un telemando físico equipado con pantalla OLED y botones para navegación intuitiva.

## Funcionalidades Principales

### 1. Telemando con Pantalla LCD (TELEMANDO_LCD)
- **Interfaz física**: Pantalla OLED SSD1306 de 128x64 píxeles con navegación por menú.
- **Controles**: Tres botones (UP, OK, DOWN) para navegación y ejecución de comandos.
- **Funciones**:
  - Selección de dispositivos remotos (cámaras).
  - Envío de comandos: Encender/Apagar cámara, solicitar reportes.
  - Visualización de estado de batería, mensajes de confirmación y errores.
- **Optimización**: Respuesta ultra-rápida a botones (1ms polling) con actualización asíncrona del LCD para evitar bloqueos.

### 2. Coordinador Zigbee (COORD)
- **Rol central**: Gestiona la red Zigbee como coordinador.
- **Comunicación asíncrona**: Recibe reportes de dispositivos remotos y los reenvía al ESP32 via TTL.
- **Solicitudes del ESP32**: Procesa comandos para reportes o control de cámaras, enviándolos a dispositivos remotos y devolviendo respuestas.
- **Base de datos**: Mantiene registro de dispositivos conectados con información de batería y actividad.

### 3. Dispositivos Remotos
- **END_DEVICE**: Dispositivo final que responde a comandos del telemando (e.g., activar/desactivar GPIO para control de cámara).
- **SENSOR_REMOTO**: Sensor que envía reportes periódicos de estado y batería al coordinador.
- **ROUTER**: Extiende el alcance de la red Zigbee.

### 4. Integración con ESP32 (ESP32_CELULLAR)
- **Comunicación TTL**: Interfaz serial asíncrona con el XBee coordinador.
- **MQTT Remoto**: Conexión segura a un broker MQTT en otra red local, usando TLS con certificados cliente.
- **Funciones**:
  - Publica reportes de XBee en tópicos MQTT.
  - Recibe comandos MQTT para enviar al XBee (opcional).
- **Conectividad**: WiFi para acceso a internet y comunicación con broker remoto.

### 5. Comunicación Segura y Eficiente
- **Protocolo TTL**: Mensajes line-based (terminados en \n) para comunicación XBee-ESP32.
- **MQTT con TLS**: Autenticación cliente-servidor para acceso seguro al broker remoto.
- **Watchdog y Gestión de Energía**: WDT en todos los dispositivos para estabilidad, con modos de bajo consumo.

## Arquitectura del Sistema

```
[Telemando LCD] -- Zigbee -- [Coordinador] -- TTL -- [ESP32] -- WiFi -- [Broker MQTT Remoto]
                                      |
                                      |-- Zigbee -- [Dispositivos Remotos (Cámaras/Sensores)]
```

- **Red Zigbee**: Mesh network con XBee3 para comunicación inalámbrica fiable.
- **ESP32 como Puente**: Conecta la red Zigbee a internet/MQTT.
- **Telemando**: Interfaz de usuario físico para control local.

## Lo Interesante y Novedoso

### 1. **Optimización Extrema de Respuesta en MicroPython**
- **Polling ultra-rápido**: 1ms para detección de botones, logrando respuesta casi instantánea en un entorno limitado como XBee3.
- **Separación de lógica**: Detección de botones independiente de actualización LCD para evitar bloqueos I2C.
- **Debounce inteligente**: Timestamp-based sin sleeps bloqueantes, permitiendo polling continuo.

### 2. **Comunicación Asíncrona Híbrida**
- **TTL + MQTT**: Combinación de comunicación serial asíncrona con protocolo MQTT remoto, permitiendo control desde cualquier lugar con internet.
- **Certificados TLS**: Implementación de seguridad avanzada en MQTT para acceso remoto seguro sin exponer puertos públicos.

### 3. **Arquitectura Modular y Reutilizable**
- **Clase Base XBeeDevice**: Herencia para dispositivos comunes, con subclases específicas (e.g., Telemand hereda de XBeeDeviceMinimal para optimizar memoria).
- **Gestión de Memoria**: Técnicas avanzadas para MicroPython (lazy imports, GC forzado, __slots__) en entornos con heap limitado.

### 4. **Integración IoT Completa**
- **Control Remoto de Cámaras**: Desde telemando físico hasta MQTT remoto, con confirmaciones bidireccionales.
- **Monitoreo en Tiempo Real**: Reportes de batería y estado enviados automáticamente al broker MQTT.

### 5. **Optimizaciones de Hardware**
- **I2C a 200kHz**: Balance óptimo entre velocidad y estabilidad para pantalla OLED.
- **Watchdog Inteligente**: Alimentación automática en operaciones críticas para prevenir hangs.

## Instalación

### Hardware Necesario:

- Módulos XBee3 Zigbee (coordinador, router, end devices).
- ESP32 con módulo WiFi.
- Pantalla OLED SSD1306, botones y batería para telemando.

### Software:

- Instala MicroPython en XBee3 via XCTU.
- Para ESP32: Usa PlatformIO con las librerías PubSubClient y WiFiClientSecure.

### Configuración:

- Configura direcciones Zigbee en `xbee_devices.py`.
- Ajusta credenciales WiFi/MQTT en `ESP32_CELULLAR/src/main.cpp`.
- Sube los códigos a cada dispositivo.

## Uso

1. **Configura la Red**: Enciende el coordinador y dispositivos remotos.
2. **Telemando**: Navega el menú con botones para seleccionar dispositivo y enviar comandos.
3. **Monitoreo**: Los reportes aparecen en el broker MQTT remoto.
4. **Control Remoto**: Envía comandos MQTT al ESP32 para controlar dispositivos via XBee.

Este sistema demuestra una integración avanzada de tecnologías IoT, optimizada para rendimiento y seguridad en entornos embebidos.