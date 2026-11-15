# ============================================================
# SERVIDOR LUNAR — Backend Python
# NASA Space Apps Challenge 2026 — Polo Sur Lunar (CLPS)
#
# Responsabilidades:
#   1. Servir el visor 3D (y resolver el problema de CORS de
#      la NASA JPL Horizons API PERMANENTEMENTE).
#   2. /api/horizons      -> proxy real a NASA JPL Horizons
#                           (Sol o Tierra segun parametro ?body=)
#   3. /api/breadcrumbs   -> GET: ruta global generada por el
#                             simulador C++ (datos_caminata.json)
#                             POST: guardar la caminata del usuario
#   4. /api/status        -> diagnostico del backend
#   5. /api/esp32         -> puente serie bidireccional con el
#                             rover/traje ESP32 (opcional)
#
# Solo biblioteca estandar (sin dependencias externas).
# pyserial 3.5 es OPCIONAL: si falla la importacion, el puente
# reporta "connected": false en lugar de detener el servidor.
#
# Ejecutar:  python servidor_lunar.py  [puerto=8123]
# ============================================================

import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_RUTA_CPLUS = os.path.join(DIR_BASE, "datos_caminata.json")
ARCHIVO_CAMINATA_USUARIO = os.path.join(DIR_BASE, "caminata_usuario.json")
ARCHIVO_DEM_BIN = os.path.join(DIR_BASE, "datos_reales", "terreno_real_shackleton.bin")
ARCHIVO_DEM_META = os.path.join(DIR_BASE, "datos_reales", "terreno_meta.json")
JPL_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# Coordenadas de los sitios del visor (lat, lon)
SITIOS = {
    "shackleton": (-89.9, 0.0),
    "malapert": (-85.9, 0.9),
    "cabeus": (-84.9, -35.5),
    "tranquillity": (8.5, 31.4),
}

# --- puente ESP32 (estado global protegido) ---
# pyserial es opcional; si no esta instalado, el servidor sigue funcionando.
SERIAL_DISPONIBLE = False
try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except Exception:  # pragma: no cover - entorno sin pyserial
    serial = None  # type: ignore

_esp32_lock = threading.Lock()
_esp32_state = {
    "connected": False,
    "port": None,
    "last_uplink": None,
    "uplink_ts": None,
}
_esp32_downlink = []  # lista de dicts pendientes de enviar al ESP32

_lock = threading.Lock()


def _body_a_comando(body: str) -> str:
    """Mapea el cuerpo celeste al ID de JPL Horizons."""
    body = (body or "sun").lower().strip()
    if body == "earth":
        return "399"   # Geocentric Earth (visto desde la superficie lunar)
    return "10"        # Sol (default, backwards compatible)


def consultar_jpl_horizons(lat: float, lon: float, body: str = "sun", timeout: int = 20):
    """Ejecuta la consulta REAL a NASA JPL Horizons (la red la hace
    Python, no el navegador -> sin problema de CORS).

    body='sun'   -> Sol  (COMMAND '10')
    body='earth' -> Tierra vista desde la superficie lunar (COMMAND '399')
    """
    import datetime

    ahora = datetime.datetime.now(datetime.timezone.utc)
    ini = ahora.strftime("%Y-%m-%d %H:%M")
    fin = (ahora + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    comando = _body_a_comando(body)

    params = {
        "format": "text",
        "COMMAND": f"'{comando}'",      # Sol o Tierra
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",        # centro: superficie de la Luna
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lat},{lon},0'",
        "START_TIME": f"'{ini}'",
        "STOP_TIME": f"'{fin}'",
        "STEP_SIZE": "'30m'",
        "QUANTITIES": "'4'",            # azimut / elevacion aparentes
    }
    url = JPL_URL + "?" + urllib.parse.urlencode(params, safe="'@,:-")
    req = urllib.request.Request(url, headers={"User-Agent": "LunarEVA-HUD/2.0 (SpaceApps2026)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        texto = resp.read().decode("utf-8", "replace")

    s, e = texto.find("$$SOE"), texto.find("$$EOE")
    if s == -1 or e == -1 or e <= s:
        raise ValueError("Respuesta JPL sin bloque $$SOE")
    linea = texto[s + 5:e].strip().splitlines()[0]
    nums = [float(p) for p in linea.split() if _es_numero(p)]
    if len(nums) < 2:
        raise ValueError("Linea efemeride sin azimut/elevacion")
    az, el = nums[-2], nums[-1]
    if not (0 <= az <= 360 and -90 <= el <= 90):
        raise ValueError(f"AZ/EL fuera de rango fisico: {az}, {el}")
    return {
        "az": az,
        "el": el,
        "source": "NASA JPL HORIZONS REAL",
        "utc": ini,
        "body": "sun" if comando == "10" else "earth",
    }


def _es_numero(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False


def _encontrar_puerto_esp32():
    """Devuelve el primer puerto serie que parezca un ESP32, o None."""
    if not SERIAL_DISPONIBLE:
        return None
    vids_utiles = {0x10C4, 0x1A86}
    keywords = ("CP210", "CH340", "UART", "JTAG")
    for p in serial.tools.list_ports.comports():  # type: ignore[attr-defined]
        desc = f"{p.description} {p.hwid}".upper()
        if any(k.upper() in desc for k in keywords) or (p.vid in vids_utiles):
            return p.device
    return None


def _abrir_puerto_esp32(puerto: str):
    """Abre el puerto serie. Lanza excepcion si no es posible."""
    if not SERIAL_DISPONIBLE:
        raise RuntimeError("pyserial no esta instalado")
    return serial.Serial(puerto, 115200, timeout=0.5)  # type: ignore[attr-defined]


def puente_esp32():
    """Hilo daemon: busca un ESP32, mantiene conexion serie,
    lee telemetria uplink y envia comandos downlink."""
    while True:
        puerto = None
        ser = None
        try:
            if not SERIAL_DISPONIBLE:
                raise RuntimeError("pyserial no disponible")
            puerto = _encontrar_puerto_esp32()
            if puerto is None:
                raise RuntimeError("ningun puerto ESP32 detectado")
            ser = _abrir_puerto_esp32(puerto)
            with _esp32_lock:
                _esp32_state["connected"] = True
                _esp32_state["port"] = puerto
                _esp32_state["last_uplink"] = None
                _esp32_state["uplink_ts"] = None
            print(f"[ESP32] Conectado en {puerto}")

            while True:
                # --- lectura de uplink (no bloqueante por timeout=0.5) ---
                try:
                    linea = ser.readline()
                    if linea:
                        texto = linea.decode("utf-8", "replace").strip()
                        if texto:
                            try:
                                uplink = json.loads(texto)
                                with _esp32_lock:
                                    _esp32_state["last_uplink"] = uplink
                                    _esp32_state["uplink_ts"] = time.time()
                            except json.JSONDecodeError:
                                # telemetria no JSON: se ignora pero no se corta
                                pass
                except Exception:
                    break

                # --- escritura de downlink (maximo cada 100 ms) ---
                paquete = None
                with _esp32_lock:
                    if _esp32_downlink:
                        paquete = _esp32_downlink.pop(0)
                if paquete is not None:
                    try:
                        ser.write((json.dumps(paquete, ensure_ascii=False) + "\n").encode("utf-8"))
                        ser.flush()
                    except Exception:
                        # si falla la escritura, se desconectara en la siguiente iteracion
                        pass
                time.sleep(0.1)

        except Exception as exc:
            with _esp32_lock:
                _esp32_state["connected"] = False
                _esp32_state["port"] = None
            razon = str(exc) or "desconectado"
            print(f"[ESP32] {razon}; reintentando en 5 s...")

        finally:
            if ser is not None and getattr(ser, "is_open", False):
                try:
                    ser.close()
                except Exception:
                    pass
            with _esp32_lock:
                _esp32_state["connected"] = False
                _esp32_state["port"] = None

        time.sleep(5)


class Manejador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------- utilidades ----------
    def _enviar(self, code: int, cuerpo: bytes, tipo: str):
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, obj, code: int = 200):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._enviar(code, cuerpo, "application/json; charset=utf-8")

    def _enviar_archivo(self, code: int, cuerpo: bytes, tipo: str, cache_control: str = "no-store"):
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, fmt, *args):
        sys.stdout.write("[SERVIDOR] %s\n" % (fmt % args))

    def _leer_body_json(self, max_bytes: int = 8192):
        n = int(self.headers.get("Content-Length", "0"))
        if n <= 0 or n > max_bytes:
            return None
        return json.loads(self.rfile.read(n).decode("utf-8"))

    # ---------- HTTP ----------
    def do_GET(self):
        ruta = urllib.parse.urlparse(self.path).path
        if ruta == "/api/status":
            with _esp32_lock:
                estado_esp32 = _esp32_state["connected"]
            estado = {
                "servidor": "Python 3 — Servidor Lunar",
                "nasa_jpl": "activo (proxy sin CORS)",
                "simulador_cpp": os.path.exists(ARCHIVO_RUTA_CPLUS),
                "caminata_usuario_guardada": os.path.exists(ARCHIVO_CAMINATA_USUARIO),
                "dem_real": os.path.exists(ARCHIVO_DEM_BIN),
                "dir": DIR_BASE,
                "esp32": estado_esp32,
                "pyserial": SERIAL_DISPONIBLE,
            }
            return self._json(estado)

        if ruta == "/api/horizons":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            sitio = (q.get("site", ["shackleton"])[0])
            body = (q.get("body", ["sun"])[0]).lower().strip()
            lat, lon = SITIOS.get(sitio, SITIOS["shackleton"])
            try:
                datos = consultar_jpl_horizons(lat, lon, body=body)
                datos["site"] = sitio
                return self._json(datos)
            except Exception as exc:  # respuesta honesta si NASA falla
                return self._json({"source": "SIMULADO", "error": str(exc), "body": body}, 502)

        if ruta == "/api/breadcrumbs":
            # Ruta global generada por el simulador C++
            if not os.path.exists(ARCHIVO_RUTA_CPLUS):
                return self._json({"error": "Ejecuta primero simulador_caminata.exe"}, 404)
            with open(ARCHIVO_RUTA_CPLUS, "rb") as fh:
                return self._enviar(200, fh.read(), "application/json; charset=utf-8")

        if ruta == "/api/mi_caminata":
            if os.path.exists(ARCHIVO_CAMINATA_USUARIO):
                with open(ARCHIVO_CAMINATA_USUARIO, "rb") as fh:
                    return self._enviar(200, fh.read(), "application/json; charset=utf-8")
            return self._json({"trail": []}, 200)

        if ruta == "/api/esp32":
            with _esp32_lock:
                respuesta = dict(_esp32_state)
            return self._json(respuesta)

        if ruta == "/api/dem":
            if not os.path.isfile(ARCHIVO_DEM_BIN):
                return self._json({"error": "Ejecuta datos_reales/procesar_dem.py"}, 404)
            with open(ARCHIVO_DEM_BIN, "rb") as fh:
                return self._enviar_archivo(200, fh.read(), "application/octet-stream", "max-age=86400")

        if ruta == "/api/dem_meta":
            if not os.path.isfile(ARCHIVO_DEM_META):
                return self._json({"error": "Ejecuta datos_reales/procesar_dem.py"}, 404)
            with open(ARCHIVO_DEM_META, "rb") as fh:
                return self._enviar_archivo(200, fh.read(), "application/json; charset=utf-8", "max-age=86400")

        # ---- archivos estaticos (el visor HTML, three.js, etc.)
        ruta_rel = ruta.lstrip("/") or "index.html"
        ruta_rel = urllib.parse.unquote(ruta_rel)
        ruta_rel = ruta_rel.replace("..", "")  # sanitizacion basica anti path-traversal
        archivo = os.path.join(DIR_BASE, ruta_rel)
        if os.path.isfile(archivo):
            tipos = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".png": "image/png", ".jpg": "image/jpeg",
                ".css": "text/css", ".svg": "image/svg+xml", ".pdf": "application/pdf",
            }
            tipo = tipos.get(os.path.splitext(archivo)[1].lower(), "application/octet-stream")
            with open(archivo, "rb") as fh:
                return self._enviar(200, fh.read(), tipo)
        return self._json({"error": "no encontrado"}, 404)

    def do_POST(self):
        if self.path == "/api/esp32":
            try:
                datos = self._leer_body_json()
                if not isinstance(datos, dict):
                    raise ValueError("JSON invalido")
            except Exception as exc:
                return self._json({"ok": False, "connected": False, "error": str(exc)}, 400)

            with _esp32_lock:
                conectado = _esp32_state["connected"]

            if not conectado:
                razon = "pyserial no disponible" if not SERIAL_DISPONIBLE else "ESP32 no conectado"
                return self._json({"ok": False, "connected": False, "reason": razon}, 200)

            # Sanitizacion estricta del comando
            alert_raw = datos.get("alert", 0)
            turn_raw = datos.get("turn", "C")
            failsafe_raw = datos.get("failsafe", 0)
            try:
                alert = max(0, min(2, int(alert_raw)))
            except (TypeError, ValueError):
                alert = 0
            turn = str(turn_raw).upper()
            if turn not in ("L", "R", "C"):
                turn = "C"
            try:
                failsafe = 1 if int(failsafe_raw) else 0
            except (TypeError, ValueError):
                failsafe = 0

            paquete = {"alert": alert, "turn": turn, "failsafe": failsafe}
            with _esp32_lock:
                _esp32_downlink.append(paquete)
                _esp32_state["connected"] = True  # confirmamos que sigue operativo
            return self._json({"ok": True, "connected": True, "enqueued": True})

        if self.path != "/api/mi_caminata":
            return self._json({"error": "endpoint desconocido"}, 404)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            datos = json.loads(self.rfile.read(n).decode("utf-8"))
            trail = datos.get("trail", [])
            # Sanitizacion: solo numeros finitos acotados
            limpio = []
            for p in trail:
                try:
                    x = float(p["x"]); z = float(p["z"])
                    if abs(x) < 1e6 and abs(z) < 1e6:
                        limpio.append({"x": round(x, 2), "z": round(z, 2),
                                       "y": round(float(p.get("y", 0)), 2),
                                       "t": int(p.get("t", 0))})
                except (KeyError, TypeError, ValueError):
                    continue
            limpio = limpio[-2000:]  # tope de memoria
            with _lock:
                with open(ARCHIVO_CAMINATA_USUARIO, "w", encoding="utf-8") as fh:
                    json.dump({"guardado": time.time(), "puntos": len(limpio), "trail": limpio},
                              fh, ensure_ascii=False)
            return self._json({"ok": True, "guardados": len(limpio)})
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, 400)


def main():
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8123

    # Arrancar puente serie ESP32 en segundo plano (daemon)
    hilo_esp32 = threading.Thread(target=puente_esp32, daemon=True, name="esp32-bridge")
    hilo_esp32.start()

    srv = ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)
    print("=" * 60)
    print("SERVIDOR LUNAR (Python) — NASA Space Apps 2026")
    print(f"  Visor:  http://localhost:{puerto}/")
    print(f"  API:    http://localhost:{puerto}/api/status")
    print("  NASA JPL Horizons: proxy activo (sin problema de CORS)")
    print(f"  pyserial: {'disponible' if SERIAL_DISPONIBLE else 'NO disponible'}")
    print("  Ctrl+C para detener")
    print("=" * 60)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
