# Simulador Wokwi — Casco Lunar HUD (ESP32)

Proyecto listo para [wokwi.com](https://wokwi.com) — permite probar el firmware
`esp32_casco_hud.ino` **sin hardware físico** y demostrar la telemetría
bidireccional PC <-> ESP32 en el video demo de la presentación.

## Cómo abrirlo (2 opciones)

### Opción A — Copiar y pegar en la web (más rápido)
1. Entra a https://wokwi.com/projects/new/esp32
2. Borra el contenido de `sketch.ino` y pega el de este archivo `sketch.ino`
3. Abre la pestaña `diagram.json` (arriba a la derecha, junto a sketch.ino)
   y reemplaza TODO por el contenido de este `diagram.json`
4. El simulador arranca solo (botón ▶ verde)

### Opción B — VS Code
Instala la extensión "Wokwi for VS Code", abre esta carpeta (`wokwi_simulador/`)
y ejecuta el comando "Wokwi: Start Simulator".

## Partes del diagrama

| Parte | Conexión | Rol en el casco |
|---|---|---|
| ESP32 DevKit C V4 | — | La placa del casco (firmware completo) |
| HC-SR04 (ultrasónico) | TRIG→GPIO5, ECHO→GPIO18 | Sensor de distancia del LIDAR/proximidad |
| Potenciómetro | SIG→GPIO34 | **Proxy de radiación**: gíralo al máximo 3 lecturas seguidas → FAIL-SAFE LOCAL (`"failsafe":2`) |
| Botón azul | GPIO0↔GND | Botón LIDAR (emite 1 frame con `"scan":1`) |
| LED rojo + R 220Ω | GPIO2 → R → LED → GND | Actuador de alertas C&W y giros |
| Monitor serial | TX/RX | ¡Aquí está la telemetría bidireccional! |

## Cómo probar la telemetría bidireccional (¡la demo estrella!)

1. Inicia la simulación. El **monitor serial inferior** mostrará los frames de
   telemetría del ESP32 cada 100 ms (10 Hz):
   ```json
   {"lidar":6.50,"prox":4.10,"ultra":6.50,"temp":-50.30,"ir":-46.60,"bpm":72,"scan":0,"failsafe":0}
   ```
2. En el **campo de entrada del monitor serial**, escribe un comando del PC y Enter:
   ```json
   {"alert":2,"turn":"R"}
   ```
   → el LED hace 2 pulsos cortos (giro a la derecha) y luego el patrón de Clase 2.
3. Prueba la batería completa de comandos:

| Comando (Enter en el serial) | Resultado visible |
|---|---|
| `{"alert":1}` | Estroboscopio 80 ms (Clase 1 EMERGENCIA) |
| `{"alert":2}` | Pulso 250 ms (Clase 2 PRECAUCIÓN) |
| `{"alert":0}` | LED apagado |
| `{"alert":0,"turn":"R"}` | 2 pulsos cortos de giro |
| `{"alert":0,"turn":"L"}` | 1 pulso largo de giro |
| `{"failsafe":1}` | Modo bajo consumo: LED latido 1 Hz, telemetría baja a 2 Hz |
| `{"failsafe":0}` | Regresa a 10 Hz normal |

4. **Fail-safe local (sin comandos)**: sube el potenciómetro a más del 78% y
   espera ~1.5 s → el uplink cambia a `"failsafe":2` y se queda fijado hasta
   que envíes `{"failsafe":0}`.
5. **Pulso LIDAR**: clic en el botón azul → exactamente 1 frame con `"scan":1`.

## Cómo conectarlo al PC real (cuando tengas el ESP32 físico)

1. Conéctalo por USB (Chrome/Edge), flashea `sketch.ino` con Arduino IDE.
2. En el visor web: pantalla de muñeca (TAB) → pestaña ESP32/AR → clic en tu puerto COM.
3. El visor enviará `{"alert":N,"turn":X,"failsafe":0|1}` cada 250 ms y mostrará
   el uplink del ESP32 en el panel de sensores — bidireccional de verdad.

## Datos del firmware
- Fuente: `../esp32_casco_hud.ino` (565 líneas, protocolo completo en su cabecera)
- Compilación verificada con clang++ contra stub de Arduino: 0 warnings, 0 errores
- Nota del simulador: el HC-SR04 en Wokwi acepta 3.3 V directamente;
  en hardware real usa divisor de voltaje en ECHO (1kΩ/2kΩ).
