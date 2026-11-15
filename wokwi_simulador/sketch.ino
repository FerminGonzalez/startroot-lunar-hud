/**
 * ============================================================================
 * FIRMWARE OFICIAL ESP32 - VISOR AR CASCO LUNAR (MODO PLACA SOLA + WOKWI)
 * Archivo: esp32_casco_hud.ino
 * ============================================================================
 * ¡FUNCIONA CON EL ESP32 SOLO (SIN SENSORES EXTERNOS) Y TAMBIÉN EN WOKWI!
 *
 * QUE HACE
 *   1. Genera telemetria sintetica cada 100 ms (LIDAR, proximidad, ultrasonico,
 *      temperatura, IR, BPM, rumbo). Si el ultrasonido no responde (placa sola)
 *      usa los canales TOUCH y un modelo simulado, igual que la v1.
 *   2. Recibe por el mismo puerto serie los comandos del PC (Clase C&W, giro,
 *      fail-safe) y los actua sobre el LED integrado (GPIO 2).
 *   3. Modo FAIL-SAFE de bajo consumo: ordenado por el PC o autodetectado por
 *      el sensor analogico (proxy de radiacion).
 *
 * ------------------------------ PROTOCOLO ----------------------------------
 * PC -> ESP32  (downlink, UNA linea JSON compacta terminada en '\n'):
 *
 *     {"alert":0|1|2,"turn":"L"|"R"|"C","failsafe":0|1}
 *
 *   - Las tres claves son INDEPENDIENTES: se acepta cualquier orden, se aceptan
 *     claves ausentes (se conserva el valor previo) y se aceptan espacios.
 *   - alert    0 = nominal (LED apagado)
 *              1 = Clase 1 C&W, emergencia -> estrobo 80 ms
 *              2 = Clase 2 C&W, desvio/obstaculo -> pulso 250 ms
 *   - turn     "R" = giro derecha  -> 2 pulsos cortos (90 ms) como prefijo
 *              "L" = giro izquierda -> 1 pulso largo (450 ms) como prefijo
 *              "C" = centrado       -> sin indicacion de giro
 *   - failsafe 1 = entra en bajo consumo
 *              0 = sale del modo (limpia tambien el fail-safe local = 2)
 *
 * ESP32 -> PC  (uplink, 10 Hz nominal / 2 Hz en fail-safe):
 *
 *     {"lidar":m,"prox":m,"ultra":m,"temp":C,"ir":C,"bpm":n,
 *      "heading":deg,"scan":0|1,"failsafe":0|1|2}
 *
 *   - "heading" solo se emite si analogRead(34) > 50 (igual que la v1).
 *   - "scan":1 solo en el ciclo en que se pulso el boton LIDAR (GPIO 0).
 *   - "failsafe": 0 = nominal | 1 = ordenado por el PC | 2 = local (sensor).
 *     Se emite SIEMPRE, para que el PC sepa que la placa acuso el modo.
 *
 * --------------------------- PRIORIDAD DEL LED ------------------------------
 * GPIO 2 tiene UN SOLO escritor: escribirLed(). Prioridad:
 *   1. Fail-safe activo -> latido 1 Hz (500 ms encendido / 500 ms apagado)
 *   2. Prefijo de giro  -> 2 pulsos cortos (R) / 1 pulso largo (L)
 *   3. Alerta C&W       -> Clase 1: 80 ms | Clase 2: 250 ms
 *   4. Sin alerta       -> LED apagado
 * En fail-safe la alerta C&W NO parpadea: el modo es de consumo minimo y el
 * HUD del PC es la superficie primaria de alarma.
 *
 * -------------------- POR QUE EL GIRO VA EN EL LED --------------------------
 * GPIO 4 y GPIO 15 son los pines TOUCH que se leen con touchRead() para
 * proximidad y temperatura: usarlos como salida digital inutiliza el canal
 * capacitivo (y GPIO 15 es pin de strapping). Se eligio por tanto la variante
 * aceptada de "modular la cadencia del LED": el giro se transmite como un
 * PREFIJO de pulsos antes del patron de alerta. No requiere hardware extra.
 *
 * ----------------------- UMBRAL DEL FAIL-SAFE LOCAL -------------------------
 * Se lee analogRead(GPIO 34) en cada ciclo de telemetria.
 *   UMBRAL_RADIACION_ADC = 3200  (escala 0..4095 con atenuacion 11 dB,
 *                                 aprox. 2.58 V) -> 78 % del fondo de escala.
 *   Se exigen 3 lecturas CONSECUTIVAS (una cada 100 ms = 300 ms) -> failsafe 2.
 *   Histeresis: el contador solo se reinicia por debajo de 3000, para que una
 *   senal ruidosa en el borde no rearme el detector.
 * ADVERTENCIA: en una placa sin nada conectado al GPIO 34 el pin queda FLOTANTE
 * y puede leer alto (disparando el modo). Puentea GPIO 34 a GND para probar en
 * banco, o pon FAILSAFE_LOCAL_ACTIVO = false para desactivar el detector.
 *
 * ------------------------------ QUE SE MANTIENE -----------------------------
 * - Pines, baudrate 115200, suavizado exponencial (0.7/0.3 y 0.8/0.2),
 *   telemetria de 100 ms, boton LIDAR en GPIO 0, campos JSON del uplink.
 * - Compatibilidad total con Wokwi y con el sketch de placa sola: no hay
 *   componentes externos obligatorios.
 *
 * ------------------------------ COMO PROBARLO -------------------------------
 * Arduino IDE: el archivo debe estar dentro de una carpeta con su mismo nombre
 *   (esp32_casco_hud/esp32_casco_hud.ino) o el IDE pedira moverlo.
 * Wokwi: usa sketch.ino + diagram.json con board "board-esp32-devkit-c-v4".
 * NOTA: este firmware se entrego SIN COMPILAR (no hay arduino-cli en el equipo
 *   de origen). Compilalo en Arduino IDE y usa el Monitor Serie a 115200.
 */

#include <Arduino.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

// ================================ PINES =====================================
constexpr uint8_t PIN_TRIG_ULTRASONICO = 5;
constexpr uint8_t PIN_ECHO_ULTRASONICO = 18;
constexpr uint8_t PIN_SENSOR_ANALOGICO = 34;
constexpr uint8_t PIN_BOTON_LIDAR      = 0;
constexpr uint8_t PIN_LED_INTEGRADO    = 2;
constexpr uint8_t PIN_TOUCH_PROXIMIDAD = 4;
constexpr uint8_t PIN_TOUCH_TERMICO    = 15;

// ============================== CADENCIAS ===================================
constexpr uint16_t PERIODO_TELEMETRIA_MS          = 100;
constexpr uint16_t PERIODO_TELEMETRIA_FAILSAFE_MS = 500;
constexpr uint16_t RETARDO_BUCLE_NORMAL_MS        = 2;
constexpr uint16_t RETARDO_BUCLE_FAILSAFE_MS      = 60;

// ============================ PATRON LED C&W ================================
constexpr uint16_t MS_PARPADEO_CLASE1 = 80;
constexpr uint16_t MS_PARPADEO_CLASE2 = 250;
constexpr uint16_t LATIDO_FAILSAFE_MS = 500;

// ========================= PREFIJO DE GIRO (TURN) ===========================
constexpr uint16_t PREFIJO_MS_PULSO_CORTO = 90;   // "R": 2 pulsos cortos
constexpr uint16_t PREFIJO_MS_PULSO_LARGO = 450;  // "L": 1 pulso largo
constexpr uint16_t PREFIJO_MS_APAGADO     = 140;  // separacion entre pulsos
constexpr uint16_t PREFIJO_REFRACTARIO_MS = 900;  // anti-parpadeo si R/L oscila

// ============================ ENTRADA SERIE =================================
constexpr uint16_t PRE_TIMEOUT_LINEA_MS = 200;  // guardia de linea parcial
constexpr uint8_t  CAPACIDAD_LINEA_RX   = 96;   // bytes por trama (compacta < 60)

// ========================= FAIL-SAFE LOCAL ==================================
constexpr bool     FAILSAFE_LOCAL_ACTIVO     = true;
constexpr uint16_t UMBRAL_RADIACION_ADC      = 3200;
constexpr uint16_t HISTERESIS_RADIACION_ADC  = 200;
constexpr uint8_t  LECTURAS_RADIACION_ALERTA = 3;

// ============================ REBOTE BOTON ==================================
constexpr uint16_t REBOTE_BOTON_MS = 30;

// ============================== ESTADO ======================================
unsigned long ultimoEnvio = 0;
bool estadoBotonAnterior = false;
unsigned long ultimoCambioBoton = 0;
float distSuavizada = 6.5f;
float tempSuavizada = -50.3f;

// Downlink (PC -> ESP32)
uint8_t nivelAlertaPC = 0;   // 0 nominal, 1 Clase 1, 2 Clase 2
char    turnoPC       = 'C'; // 'L', 'R', 'C'
uint8_t modoFailsafe  = 0;   // 0 nominal, 1 PC, 2 local

// Maquina de estados del LED (no bloqueante)
enum FaseLed : uint8_t { FASE_ALERTA = 0, FASE_PREFIJO = 1 };
FaseLed faseLed = FASE_ALERTA;
bool ledEncendido = false;
unsigned long ledProximoCambio = 0;

uint8_t  prefijoPulsosRestantes = 0;
uint16_t prefijoMsAlto = PREFIJO_MS_PULSO_CORTO;
bool     prefijoEnAlto = false;
bool     prefijoTurnoPendiente = false;
bool     prefijoJugado = false;
unsigned long ultimoPrefijo = 0;

// Acumulador de linea RX (sin String, sin bloquear)
char lineaRx[CAPACIDAD_LINEA_RX];
uint8_t longitudRx = 0;
bool lineaRxEnCurso = false;
bool descartarRx = false;
unsigned long inicioLineaRx = 0;

// Detector de radiacion local
uint8_t lecturasRadiacionAltas = 0;

// ============================== UTILIDADES ==================================
// Comparacion de tiempos segura frente al desbordamiento de millis() (~49 dias).
// Valida para intervalos menores a 24.8 dias.
static inline bool tiempoCumplido(unsigned long ahora, unsigned long objetivo) {
  return (int32_t)(ahora - objetivo) >= 0;
}

static inline float limitar(float valor, float minimo, float maximo) {
  if (valor < minimo) return minimo;
  if (valor > maximo) return maximo;
  return valor;
}

// Unico escritor del LED integrado: evita que dos rutinas peleen por GPIO 2.
void escribirLed(bool encender) {
  if (ledEncendido == encender) return;
  ledEncendido = encender;
  digitalWrite(PIN_LED_INTEGRADO, encender ? HIGH : LOW);
}

// ======================= MAQUINA DE ESTADOS DEL LED =========================
void iniciarPrefijoTurno(unsigned long ahora, char turno) {
  if (turno == 'R') {
    prefijoPulsosRestantes = 2;
    prefijoMsAlto = PREFIJO_MS_PULSO_CORTO;
  } else if (turno == 'L') {
    prefijoPulsosRestantes = 1;
    prefijoMsAlto = PREFIJO_MS_PULSO_LARGO;
  } else {
    return;  // 'C': sin indicacion de giro
  }

  faseLed = FASE_PREFIJO;
  prefijoEnAlto = true;
  prefijoTurnoPendiente = false;
  prefijoJugado = true;
  ultimoPrefijo = ahora;
  ledProximoCambio = ahora + prefijoMsAlto;
  escribirLed(true);
}

// Secuencia: R = ON90 OFF140 ON90 OFF140 -> alerta
//            L = ON450 OFF140 -> alerta
void avanzarPrefijo(unsigned long ahora) {
  if (!tiempoCumplido(ahora, ledProximoCambio)) return;

  if (prefijoEnAlto) {
    escribirLed(false);
    prefijoEnAlto = false;
    if (prefijoPulsosRestantes > 0) --prefijoPulsosRestantes;
    ledProximoCambio = ahora + PREFIJO_MS_APAGADO;
    return;
  }

  if (prefijoPulsosRestantes == 0) {
    faseLed = FASE_ALERTA;
    ledProximoCambio = ahora;  // el patron de alerta reevalua de inmediato
    return;
  }

  escribirLed(true);
  prefijoEnAlto = true;
  ledProximoCambio = ahora + prefijoMsAlto;
}

void avanzarAlerta(unsigned long ahora) {
  uint16_t periodo = 0;
  if (nivelAlertaPC == 1) {
    periodo = MS_PARPADEO_CLASE1;
  } else if (nivelAlertaPC == 2) {
    periodo = MS_PARPADEO_CLASE2;
  }

  if (periodo == 0) {
    escribirLed(false);  // alert 0 => LED apagado, estado terminal explicito
    return;
  }

  if (!tiempoCumplido(ahora, ledProximoCambio)) return;
  ledProximoCambio = ahora + periodo;
  escribirLed(!ledEncendido);
}

void latidoFailsafe(unsigned long ahora) {
  if (!tiempoCumplido(ahora, ledProximoCambio)) return;
  ledProximoCambio = ahora + LATIDO_FAILSAFE_MS;
  escribirLed(!ledEncendido);
}

void actualizarLedHud(unsigned long ahora) {
  if (modoFailsafe != 0) {
    latidoFailsafe(ahora);
    return;
  }

  if (faseLed == FASE_PREFIJO) {
    avanzarPrefijo(ahora);
    return;
  }

  // Prefijo pendiente: se emite cuando vence el refractario anti-parpadeo.
  if (prefijoTurnoPendiente &&
      (!prefijoJugado || (unsigned long)(ahora - ultimoPrefijo) >= PREFIJO_REFRACTARIO_MS)) {
    iniciarPrefijoTurno(ahora, turnoPC);
    if (faseLed == FASE_PREFIJO) return;
  }

  avanzarAlerta(ahora);
}

// ============================== FAIL-SAFE ===================================
void entrarFailsafe(uint8_t modo) {
  if (modoFailsafe == modo) return;
  modoFailsafe = modo;              // 1 = PC, 2 = local (nunca se degrada a 1)
  faseLed = FASE_ALERTA;
  prefijoTurnoPendiente = false;
  escribirLed(false);
  ledProximoCambio = millis() + LATIDO_FAILSAFE_MS;
}

void salirFailsafe() {
  if (modoFailsafe == 0) return;
  modoFailsafe = 0;
  lecturasRadiacionAltas = 0;       // rearma el detector local
  escribirLed(false);
  ledProximoCambio = millis();
}

void evaluarFailsafeLocal(int lecturaAdc) {
  if (!FAILSAFE_LOCAL_ACTIVO) return;

  if (lecturaAdc >= UMBRAL_RADIACION_ADC) {
    // Techo: el contador no pasa de LECTURAS_RADIACION_ALERTA + 1 (sin rebose).
    if (lecturasRadiacionAltas <= LECTURAS_RADIACION_ALERTA) ++lecturasRadiacionAltas;
  } else if (lecturaAdc < UMBRAL_RADIACION_ADC - HISTERESIS_RADIACION_ADC) {
    lecturasRadiacionAltas = 0;
  }

  // LATCHEO: una vez disparado el fail-safe local (2) NO se auto-libera, aunque
  // el ADC vuelva a la normalidad. Solo sale con {"failsafe":0} desde el PC
  // (que en ese momento siempre sale del modo, sea 1 o 2).
  if (lecturasRadiacionAltas >= LECTURAS_RADIACION_ALERTA && modoFailsafe != 2) {
    entrarFailsafe(2);
  }
}

// ============================== SENSORES ====================================
float obtenerDistanciaInteractiva() {
  digitalWrite(PIN_TRIG_ULTRASONICO, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG_ULTRASONICO, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG_ULTRASONICO, LOW);

  // Bloqueo maximo 15 ms: muy por debajo del limite de 200 ms del bucle.
  const unsigned long duracion = pulseIn(PIN_ECHO_ULTRASONICO, HIGH, 15000UL);

  if (duracion > 0) {
    // ida+vuelta en cm * 0.0343 / 2 / 100 = metros
    return limitar((float)duracion * 0.0343f / 200.0f, 0.02f, 4.0f);
  }

  const uint32_t lecturaTouch = touchRead(PIN_TOUCH_PROXIMIDAD);
  if (lecturaTouch < 45U && lecturaTouch > 0U) {
    return 0.35f + ((float)lecturaTouch / 100.0f);
  }
  return 4.2f + sinf((float)millis() * 0.002f) * 1.4f;
}

// ========================= PARSEO DEL DOWNLINK ==============================
// Devuelve un puntero al PRIMER caracter del valor de "clave", o nullptr.
// No usa String ni asignaciones: solo recorre el buffer en sitio.
const char* buscarValor(const char* trama, const char* clave) {
  const size_t largo = strlen(clave);

  for (const char* p = trama; *p != '\0'; ++p) {
    if (*p != '"') continue;
    if (strncmp(p + 1, clave, largo) != 0) continue;

    const char* q = p + 1 + largo;
    if (*q != '"') continue;           // evita que "alertX" cuente como "alert"
    ++q;
    while (*q == ' ' || *q == '\t') ++q;
    if (*q != ':') continue;
    ++q;
    while (*q == ' ' || *q == '\t') ++q;
    return q;
  }
  return nullptr;
}

bool extraerEntero(const char* trama, const char* clave, long& valor) {
  const char* p = buscarValor(trama, clave);
  if (p == nullptr) return false;

  char* fin = nullptr;
  const long v = strtol(p, &fin, 10);
  if (fin == p) return false;          // habia clave pero no numero
  valor = v;
  return true;
}

bool extraerCaracter(const char* trama, const char* clave, char& valor) {
  const char* p = buscarValor(trama, clave);
  if (p == nullptr) return false;

  if (*p == '"') ++p;                  // acepta "R" y R
  char c = *p;
  if (c >= 'a' && c <= 'z') c = (char)(c - 32);
  if (c != 'L' && c != 'R' && c != 'C') return false;
  valor = c;
  return true;
}

void fijarTurno(char nuevo) {
  if (nuevo == turnoPC) return;
  turnoPC = nuevo;

  if (nuevo == 'C') {
    prefijoTurnoPendiente = false;
    if (faseLed == FASE_PREFIJO) faseLed = FASE_ALERTA;
    return;
  }
  prefijoTurnoPendiente = true;
}

// Aplica una trama ya delimitada. Claves independientes: el orden es libre y
// una clave ausente conserva el estado anterior.
void interpretarTrama(const char* trama) {
  if (strchr(trama, '{') == nullptr) return;  // resincroniza: ignora basura

  long valor = 0;

  if (extraerEntero(trama, "alert", valor)) {
    if (valor < 0) valor = 0;
    if (valor > 2) valor = 2;
    nivelAlertaPC = (uint8_t)valor;
  }

  char giro = 'C';
  if (extraerCaracter(trama, "turn", giro)) {
    fijarTurno(giro);
  }

  if (extraerEntero(trama, "failsafe", valor)) {
    if (valor <= 0) {
      salirFailsafe();                 // tambien limpia el failsafe local (2)
    } else if (modoFailsafe == 0) {
      entrarFailsafe(1);               // 1 = ordenado por el PC
    }
    // valor >= 1 con modoFailsafe == 2: se mantiene el latcheo local.
  }
}

// Acumulador no bloqueante de lineas. Equivale a readStringUntil('\n') pero
// nunca espera: si una linea parcial lleva mas de 200 ms sin '\n' se descarta.
void procesarComandosEntrantesPC(unsigned long ahora) {
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();

    if (c == '\r') continue;

    if (c == '\n') {
      if (!descartarRx && longitudRx > 0) {
        lineaRx[longitudRx] = '\0';
        interpretarTrama(lineaRx);
      }
      longitudRx = 0;
      lineaRxEnCurso = false;
      descartarRx = false;
      continue;
    }

    if (descartarRx) continue;

    if (longitudRx >= CAPACIDAD_LINEA_RX - 1) {
      // Trama demasiado larga: se descarta entera hasta el proximo '\n'.
      descartarRx = true;
      longitudRx = 0;
      lineaRxEnCurso = false;
      continue;
    }

    if (!lineaRxEnCurso) {
      lineaRxEnCurso = true;
      inicioLineaRx = ahora;
    }
    lineaRx[longitudRx++] = c;
  }

  // Guardia de 200 ms: libera el buffer si el PC dejo una linea a medias.
  if (lineaRxEnCurso && (unsigned long)(ahora - inicioLineaRx) >= PRE_TIMEOUT_LINEA_MS) {
    longitudRx = 0;
    lineaRxEnCurso = false;
    descartarRx = false;
  }
}

// ========================== UPLINK DE TELEMETRIA ============================
void emitirTelemetria(unsigned long ahora, int dispararScan) {
  const float objetivoProx = obtenerDistanciaInteractiva();
  distSuavizada = limitar(distSuavizada * 0.7f + objetivoProx * 0.3f, 0.0f, 10.0f);

  const float distLidar = distSuavizada * 2.1f;
  const float distSuelo = 1.80f + cosf((float)ahora * 0.003f) * 0.12f;

  const uint32_t touchTermico = touchRead(PIN_TOUCH_TERMICO);
  const bool contactoTermico = (touchTermico < 45U && touchTermico > 0U);
  const float objetivoTemp = contactoTermico
                               ? 18.5f
                               : (-50.3f + sinf((float)ahora * 0.001f) * 2.5f);
  tempSuavizada = limitar(tempSuavizada * 0.8f + objetivoTemp * 0.2f, -90.0f, 60.0f);

  const int bpm = (distSuavizada < 0.8f || contactoTermico)
                    ? 118
                    : 76 + (int)((ahora / 1000UL) % 5UL);

  const int adcGiro = analogRead(PIN_SENSOR_ANALOGICO);
  const float headingSim = (adcGiro > 50) ? ((float)adcGiro / 4095.0f) * 360.0f : -1.0f;

  // Se evalua ANTES de imprimir para que el uplink de este mismo ciclo ya
  // informe "failsafe":2 cuando el pico de radiacion acaba de dispararse.
  evaluarFailsafeLocal(adcGiro);

  // Anti-bloqueo de TX: si el PC dejo de leer, el buffer del UART se llena y
  // Serial.print esperaria indefinidamente. La trama mas larga posible ocupa
  // 115 bytes, asi que sin 120 libres se descarta este ciclo (no se espera).
  if (Serial.availableForWrite() < 120) return;

  // Se usa Serial.print(float, decimales) en vez de snprintf("%f"): no depende
  // de la configuracion de newlib, no reserva memoria y es el camino ya
  // probado en placa y en Wokwi. Los valores estan acotados: nunca NaN/Inf.
  Serial.print("{\"lidar\":");
  Serial.print(distLidar, 2);
  Serial.print(",\"prox\":");
  Serial.print(distSuavizada, 2);
  Serial.print(",\"ultra\":");
  Serial.print(distSuelo, 2);
  Serial.print(",\"temp\":");
  Serial.print(tempSuavizada, 1);
  Serial.print(",\"ir\":");
  Serial.print(tempSuavizada + 3.4f, 1);
  Serial.print(",\"bpm\":");
  Serial.print(bpm);
  if (headingSim >= 0.0f) {
    Serial.print(",\"heading\":");
    Serial.print(headingSim, 1);
  }
  Serial.print(",\"scan\":");
  Serial.print(dispararScan);
  Serial.print(",\"failsafe\":");
  Serial.print((int)modoFailsafe);
  Serial.println("}");
}

// ================================= SETUP ====================================
void setup() {
  Serial.begin(115200);

  pinMode(PIN_TRIG_ULTRASONICO, OUTPUT);
  pinMode(PIN_ECHO_ULTRASONICO, INPUT);
  pinMode(PIN_BOTON_LIDAR, INPUT_PULLUP);
  pinMode(PIN_LED_INTEGRADO, OUTPUT);

  digitalWrite(PIN_LED_INTEGRADO, LOW);
  ledEncendido = false;

  delay(300);  // deja estabilizar el monitor serie / el USB-CDC

  // El boton BOOT (GPIO 0) suele estar pulsado durante el flasheo: se toma su
  // estado real como referencia para no emitir un "scan" espurio al arrancar.
  estadoBotonAnterior = (digitalRead(PIN_BOTON_LIDAR) == LOW);
  ultimoCambioBoton = millis();
}

// ================================= LOOP =====================================
void loop() {
  const unsigned long ahora = millis();

  procesarComandosEntrantesPC(ahora);
  actualizarLedHud(ahora);

  int dispararScan = 0;
  const bool botonActual = (digitalRead(PIN_BOTON_LIDAR) == LOW);
  if (botonActual != estadoBotonAnterior &&
      (unsigned long)(ahora - ultimoCambioBoton) >= REBOTE_BOTON_MS) {
    ultimoCambioBoton = ahora;
    estadoBotonAnterior = botonActual;
    if (botonActual) dispararScan = 1;  // flanco de pulsacion
  }

  const unsigned long periodo = (modoFailsafe != 0)
                                  ? PERIODO_TELEMETRIA_FAILSAFE_MS
                                  : PERIODO_TELEMETRIA_MS;

  if (dispararScan == 1 || (unsigned long)(ahora - ultimoEnvio) >= periodo) {
    ultimoEnvio = ahora;
    emitirTelemetria(ahora, dispararScan);
  }

  // En fail-safe el bucle baja de frecuencia (menos consumo y menos trafico).
  delay(modoFailsafe != 0 ? RETARDO_BUCLE_FAILSAFE_MS : RETARDO_BUCLE_NORMAL_MS);
}