#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
VISOR AR PRIMERA PERSONA & TERMINAL DE MUÑECA - CASCO LUNAR HUD (PYTHON EDITION)
===============================================================================
Incluye:
  - Cámara física en vivo con OpenCV (cv2) o Terreno Lunar 3D proyectado en tiempo real
  - Corredor holográfico de 2 Flechas curvas con Chevrons guiadas al Waypoint
  - Telémetro láser en tiempo real (cálculo 3D hacia rocas, suelo y estructuras)
  - Pequeño recuadro de Cámara Trasera 180° en tiempo real
  - Pantalla Táctica en la Muñeca (Tecla TAB) con 4 pestañas interactivas
  - Conexión directa por USB con ESP32 mediante PySerial (115200 baudios)
  - 6 Escenarios simulados (Despegue SLS, TLI, Alunizaje PDI, EVA, PSR, Tormenta Solar)
  - Ruta A* real sobre cost grid topográfico con ahorro metabólico O2 y kcal
  - Efemérides reales NASA JPL HORIZONS para el Polo Sur Lunar (89.9°S)
  - Fail-safe automático por batería / radiación / clase 1 sostenida

INSTALACIÓN RÁPIDA:
  pip install pygame numpy opencv-python pyserial

EJECUCIÓN:
  python visor_lunar_hud.py
===============================================================================
"""

import math
import json
import time
import random
import threading
import sys
import heapq
import urllib.request
import urllib.parse

import pygame
import numpy as np

# Dependencias opcionales (Cámara OpenCV y Puerto Serie ESP32)
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


# =============================================================================
# CONFIGURACIÓN Y ESTADO DEL TRAJE ESPACIAL xEMU
# =============================================================================
WIDTH, HEIGHT = 1280, 720
FPS = 60

SCENARIOS = [
    ("eva", "4. CAMINATA LUNAR EVA (NOMINAL)"),
    ("launch", "1. DESPEGUE ORBITAL SLS (MAX-Q)"),
    ("tli", "2. TRAYECTO TRANSLUNAR (TLI)"),
    ("descent", "3. ALUNIZAJE MOTORIZADO (PDI)"),
    ("psr_dark", "5. SOMBRA CRIOGÉNICA PSR (-210°C)"),
    ("solar_storm", "6. TORMENTA RADIACIÓN SOLAR (SPE)")
]


class SuitState:
    def __init__(self):
        self.scenario_idx = 0
        self.scenario = "eva"
        self.wrist_raised = False
        self.wrist_anim = 0.0  # 0.0 = abajo, 1.0 = arriba
        self.wrist_tab = 0     # 0: Sensores, 1: Navegación, 2: Ambiente, 3: ESP32/AR

        # Posición y orientación 3D del astronauta
        self.pos_x = 0.0
        self.pos_y = 1.65
        self.pos_z = 0.0
        self.heading = 0.0     # Grados (0 = Norte / -Z)
        self.pitch = -5.0      # Grados
        self.walk_cycle = 0.0
        self.descent_alt = 38.0
        self.course_anomaly = 0.0

        # Waypoints Lunares
        self.active_wp_idx = 0
        self.waypoints = [
            {"name": "Módulo Lander Base", "x": 0.0, "z": -16.0, "color": (250, 204, 21)},
            {"name": "Depósito Hielo PSR", "x": 14.0, "z": -22.0, "color": (56, 189, 248)},
            {"name": "Torre Solar Pico Luz", "x": -15.0, "z": -18.0, "color": (0, 240, 255)},
            {"name": "Rover VIPER Geología", "x": 12.0, "z": 10.0, "color": (16, 185, 129)}
        ]

        # Sensores del traje
        self.sensors = [
            {"id": "lidar", "name": "LIDAR Frontal", "val": 12.0, "unit": "m", "min": 0.0, "max": 25.0},
            {"id": "prox", "name": "Proximidad Roca", "val": 4.1, "unit": "m", "min": 0.0, "max": 10.0},
            {"id": "ultra", "name": "Ultrasónico Bota", "val": 1.8, "unit": "m", "min": 0.0, "max": 5.0},
            {"id": "temp", "name": "Térmica Traje", "val": -50.3, "unit": "°C", "min": -200.0, "max": 50.0},
            {"id": "ir", "name": "Infrarrojo Suelo", "val": -46.6, "unit": "°C", "min": -200.0, "max": 50.0}
        ]

        self.o2 = 94
        self.bpm = 76
        self.solar_deg = 0.1
        self.dust_opacity = 10
        self.optical_filter = "normal"  # normal | thermal | nvg | lidar
        self.lidar_wave_r = -1.0
        self.spectro_last = "Listo (ESPACIO)"
        self.samples_count = 0

        # Telémetro y Peligros
        self.rangefinder_dist = 4.8
        self.rangefinder_target = "REGOLITO LUNAR"
        self.nearest_rock_dist = 9.9

        # NUEVOS SISTEMAS DE INGENIERÍA NASA (A*, C&W, Efemérides, Fail-Safe, OpenCV)
        self.failsafe_mode = False          # Modo monocromático de emergencia (Tecla M)
        self.astar_active = True            # Ruta inteligente con ahorro metabólico O2
        self.o2_saved_pct = 14.2            # % de O2 ahorrado al rodear pendientes/rocas
        self.avoidance_offset = 0.0         # Desvío lateral automático A* para esquivar rocas
        self.cw_class = 3                   # 1: Emergency, 2: Warning, 3: Caution/Nominal
        self.cw_message = "CLASE 3 ADVS: RELÉ LUNAR GATEWAY ACTIVO"
        self.solar_azimuth = 180.0          # Efemérides reales Polo Sur 89.9°S
        self.solar_elevation = 0.0          # Elevación solar real desde HORIZONS
        self.earth_los = False              # Línea de vista directa Tierra (DTE)
        self.comm_mode = "GATEWAY" if not self.earth_los else "DTE TIERRA"  # 'DTE TIERRA' o 'GATEWAY'
        self.cv_obstacles = []              # Obstáculos reales detectados por OpenCV en webcam
        self.last_esp_tx = 0.0

        # Metabolismo y energía del traje
        self.kcal_burned = 0.0              # kcal acumuladas durante la EVA
        self.speed_m_s = 0.0                # Velocidad de marcha actual

        # Fail-safe y ambiente
        self.battery_pct = 100.0            # Nivel de batería del traje
        self.radiation_uSv = 0.0            # Dosis acumulada de radiación
        self.cw_class_1_since = 0.0         # Timestamp de entrada a clase 1

        # A* pathfinding local
        self.astar_waypoints = []           # Waypoints de celdas de la última ruta A*

        # Hardware (Cámara y ESP32)
        self.use_webcam = False
        self.esp32_connected = False
        self.esp32_port = "SIMULADO"
        self.sys_logs = ["[SYS] Motor Python xEMU iniciado correctamente."]

        # Generar rocas 3D y estrellas
        random.seed(42)
        self.rocks = []
        for _ in range(32):
            rx = (random.random() - 0.5) * 48.0
            rz = (random.random() - 0.5) * 48.0
            if abs(rx) < 2.8 and abs(rz) < 3.5:
                continue
            rad = 0.35 + random.random() * 0.55
            self.rocks.append({"x": rx, "z": rz, "r": rad})

        self.stars = [
            ((random.random() - 0.5) * 180.0, 6.0 + random.random() * 65.0, (random.random() - 0.5) * 180.0)
            for _ in range(280)
        ]

    def log(self, msg):
        t = time.strftime("%H:%M:%S")
        self.sys_logs.insert(0, f"[{t}] {msg}")
        self.sys_logs = self.sys_logs[:8]


# =============================================================================
# MATEMÁTICAS 3D, TOPOGRAFÍA LUNAR Y PROYECCIÓN EN CÁMARA
# =============================================================================
def get_terrain_height(x, z):
    crater_dist = math.hypot(x - 2.0, z + 11.0)
    rim = math.exp(-((crater_dist - 5.2) ** 2) / 4.0) * 0.65
    bowl = -0.45 * (1.0 - crater_dist / 5.2) if crater_dist < 5.2 else 0.0
    return math.sin(x * 0.22) * 0.25 + math.cos(z * 0.22) * 0.25 + rim + bowl


def project_point_3d(px, py, pz, cam_x, cam_y, cam_z, heading_deg, pitch_deg, scr_w, scr_h, fov_deg=62.0):
    """Proyecta un punto 3D del mundo lunar a coordenadas 2D de la pantalla."""
    dx = px - cam_x
    dy = py - cam_y
    dz = pz - cam_z

    yaw = math.radians(heading_deg)
    pitch = math.radians(pitch_deg)

    # Rotación Yaw (Rumbo)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    rx = dx * cos_y + dz * sin_y
    rz = -dx * sin_y + dz * cos_y

    # Rotación Pitch (Cabeceo)
    cos_p, sin_p = math.cos(pitch), math.sin(pitch)
    ry = dy * cos_p - rz * sin_p
    cz = dy * sin_p + rz * cos_p

    # En nuestra convención, hacia adelante es -Z (por lo que profundidad frontal = -cz)
    depth = -cz
    if depth <= 0.15:
        return None

    f = (scr_h * 0.5) / math.tan(math.radians(fov_deg * 0.5))
    sx = int(scr_w * 0.5 + (rx * f) / depth)
    sy = int(scr_h * 0.5 - (ry * f) / depth)
    return sx, sy, depth


# =============================================================================
# LECTOR HARDWARE ESP32 EN SEGUNDO PLANO (PYSERIAL)
# =============================================================================
class ESP32SerialReader(threading.Thread):
    def __init__(self, state: SuitState):
        super().__init__(daemon=True)
        self.state = state
        self.ser = None
        self.running = True

    def try_connect(self, manual_port=None):
        if not PYSERIAL_AVAILABLE:
            self.state.log("Instala pyserial: pip install pyserial")
            return False

        if manual_port:
            try:
                self.ser = serial.Serial(manual_port, 115200, timeout=1)
                self.ser.readline()
                self.state.esp32_connected = True
                self.state.esp32_port = manual_port
                self.state.log(f"ESP32 conectado manualmente en {manual_port}")
                return True
            except Exception as e:
                self.state.log(f"No se pudo abrir {manual_port}: {e}")
                return False

        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            vid = getattr(p, "vid", None)
            pid = getattr(p, "pid", None)
            # Identificadores comunes CP210x / CH340 / UART
            is_esp = (
                "cp210" in desc or "ch340" in desc or "uart" in desc or "com" in desc
                or vid in (0x10C4, 0x1A86, 0x0483, 0x239A)
                or (vid == 0x10C4 and pid in (0xEA60,))
                or (vid == 0x1A86 and pid in (0x7523, 0x5523))
            )
            if is_esp:
                try:
                    self.ser = serial.Serial(p.device, 115200, timeout=1)
                    self.ser.readline()
                    self.state.esp32_connected = True
                    self.state.esp32_port = p.device
                    self.state.log(f"ESP32 detectado y conectado en {p.device}")
                    return True
                except Exception as e:
                    self.state.log(f"Fallo al abrir {p.device}: {e}")
                    continue

        self.state.log("No se detectó ESP32 por USB (Usando Simulador).")
        self.state.esp32_connected = False
        self.state.esp32_port = "SIMULADO"
        return False

    def send_haptic_command(self, alert_level: int, turn_dir: str):
        """Telemetría Bidireccional PC -> ESP32 para activar LED/Vibrador físico."""
        if self.ser and self.ser.is_open:
            try:
                payload = json.dumps({
                    "alert": alert_level,
                    "turn": turn_dir,
                    "failsafe": 1 if self.state.failsafe_mode else 0
                }) + "\n"
                self.ser.write(payload.encode("utf-8"))
            except Exception:
                pass

    def run(self):
        while self.running:
            if self.ser and self.ser.is_open:
                try:
                    line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("{") and line.endswith("}"):
                        data = json.loads(line)
                        if "lidar" in data:
                            self.state.sensors[0]["val"] = float(data["lidar"])
                        if "prox" in data:
                            self.state.sensors[1]["val"] = float(data["prox"])
                        if "ultra" in data:
                            self.state.sensors[2]["val"] = float(data["ultra"])
                        if "temp" in data:
                            self.state.sensors[3]["val"] = float(data["temp"])
                        if "ir" in data:
                            self.state.sensors[4]["val"] = float(data["ir"])
                        if "bpm" in data:
                            self.state.bpm = int(data["bpm"])
                        if data.get("scan") == 1:
                            self.state.lidar_wave_r = 0.8
                except Exception:
                    pass
            time.sleep(0.03)


# =============================================================================
# AUXILIARES DE RUTA A* SOBRE COST GRID TOPOGRÁFICO (21x15 celdas de 1.2 m)
# =============================================================================
def get_slope_deg(x, z):
    """Pendiente local del terreno lunar en grados usando diferencias finitas."""
    h = 0.05
    y0 = get_terrain_height(x, z)
    dx = get_terrain_height(x + h, z) - y0
    dz = get_terrain_height(x, z + h) - y0
    return math.degrees(math.atan2(math.hypot(dx, dz), h))


def world_to_grid(wx, wz, origin_x, origin_z, cell_size):
    """Convierte coordenadas mundo a índices de celda del cost grid."""
    gx = int(round((wx - origin_x) / cell_size))
    gz = int(round((wz - origin_z) / cell_size))
    return gx, gz


def grid_to_world(gx, gz, origin_x, origin_z, cell_size):
    """Convierte índices de celda a coordenadas mundo."""
    return origin_x + gx * cell_size, origin_z + gz * cell_size


def build_cost_grid(state: SuitState):
    """Construye grid 21x15 (1.2 m/celda) centrado frente al astronauta."""
    cols, rows = 21, 15
    cell_size = 1.2
    look_rad = math.radians(state.heading)
    # Centro del grid a ~7.2 m frente al astronauta
    center_x = state.pos_x + math.sin(look_rad) * 7.2
    center_z = state.pos_z - math.cos(look_rad) * 7.2
    origin_x = center_x - (cols - 1) * cell_size * 0.5
    origin_z = center_z - (rows - 1) * cell_size * 0.5

    grid = [[1.0 for _ in range(rows)] for _ in range(cols)]
    for gx in range(cols):
        for gz in range(rows):
            wx, wz = grid_to_world(gx, gz, origin_x, origin_z, cell_size)
            slope = get_slope_deg(wx, wz)
            rock_penalty = 0.0
            for rock in state.rocks:
                if math.hypot(rock["x"] - wx, rock["z"] - wz) < rock["r"] + cell_size * 0.5:
                    rock_penalty = 8.0
                    break
            cost = 1.0 + 0.35 * max(0.0, slope) + rock_penalty
            if slope > 25.0:
                cost += 0.35 * (slope - 25.0)
            grid[gx][gz] = cost
    return grid, origin_x, origin_z, cell_size


def astar_path(start, goal, cost_grid):
    """A* 8-conectado con coste diagonal sqrt(2) y heurística Manhattan."""
    cols = len(cost_grid)
    rows = len(cost_grid[0])

    def in_bounds(n):
        return 0 <= n[0] < cols and 0 <= n[1] < rows

    # Asegurar puntos dentro de límites
    start = (max(0, min(cols - 1, start[0])), max(0, min(rows - 1, start[1])))
    goal = (max(0, min(cols - 1, goal[0])), max(0, min(rows - 1, goal[1])))

    open_set = [(0, start)]
    came_from = {}
    g_score = {start: 0.0}
    f_score = {start: abs(start[0] - goal[0]) + abs(start[1] - goal[1])}
    visited = set()

    while open_set:
        _, current = heapq.heappop(open_set)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]

        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            neighbor = (current[0] + dx, current[1] + dy)
            if not in_bounds(neighbor):
                continue
            move_cost = math.sqrt(2.0) if dx != 0 and dy != 0 else 1.0
            tentative = g_score[current] + move_cost * cost_grid[neighbor[0]][neighbor[1]]
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                f_score[neighbor] = tentative + abs(neighbor[0] - goal[0]) + abs(neighbor[1] - goal[1])
                heapq.heappush(open_set, (f_score[neighbor], neighbor))

    # Fallback: línea recta
    return [start, goal]


# =============================================================================
# RENDERIZADO DEL CORREDOR HOLOGRÁFICO DE 2 FLECHAS CON CHEVRONS
# =============================================================================
def draw_dual_ribbon_corridor(surface, state: SuitState, dt=0.0):
    wp = state.waypoints[state.active_wp_idx]
    dx = wp["x"] - state.pos_x
    dz = wp["z"] - state.pos_z
    dist_goal = math.hypot(dx, dz)

    look_rad = math.radians(state.heading)
    target_rad = math.atan2(dx, -dz) + state.course_anomaly

    heading_err = target_rad - look_rad
    while heading_err > math.pi:
        heading_err -= math.pi * 2.0
    while heading_err < -math.pi:
        heading_err += math.pi * 2.0

    abs_err_deg = abs(math.degrees(heading_err))
    is_hazard = state.nearest_rock_dist < 2.6
    is_warning = abs_err_deg > 14.0 or is_hazard
    is_critical = abs_err_deg > 32.0 or abs(state.course_anomaly) > 0.2 or is_hazard

    # =========================================================================
    # ALGORITMO DE EVASIÓN TOPOGRÁFICA A* Y AHORRO METABÓLICO DE O2 / KCAL
    # =========================================================================
    corridor_len = min(max(dist_goal, 4.5), 12.0)
    avoid_shift = 0.0
    kcal_per_min = 6.0
    if state.astar_active:
        grid, origin_x, origin_z, cell_size = build_cost_grid(state)
        start_g = world_to_grid(state.pos_x, state.pos_z, origin_x, origin_z, cell_size)
        goal_g = world_to_grid(wp["x"], wp["z"], origin_x, origin_z, cell_size)
        path = astar_path(start_g, goal_g, grid)
        state.astar_waypoints = [
            grid_to_world(gx, gz, origin_x, origin_z, cell_size) for gx, gz in path
        ]

        # Punto de control Bézier P1 sigue los primeros ~2 waypoints de A*
        if len(state.astar_waypoints) >= 3:
            wx1, wz1 = state.astar_waypoints[1]
            wx2, wz2 = state.astar_waypoints[2]
            mid_ax = (wx1 + wx2) * 0.5
            mid_az = (wz1 + wz2) * 0.5
            # Proyección del desplazamiento lateral respecto al rumbo actual
            avoid_shift = (mid_ax - state.pos_x) * math.cos(look_rad) + (mid_az - state.pos_z) * math.sin(look_rad)
            avoid_shift = max(-3.0, min(3.0, avoid_shift))
        else:
            avoid_shift = 0.0

        # Coste directo vs coste A* para estimar ahorro de O2
        cost_direct = 0.0
        sx, sz = state.pos_x, state.pos_z
        steps_direct = max(1, int(dist_goal / cell_size))
        for i in range(1, steps_direct + 1):
            t = i / steps_direct
            cx = sx + (wp["x"] - sx) * t
            cz = sz + (wp["z"] - sz) * t
            gx, gz = world_to_grid(cx, cz, origin_x, origin_z, cell_size)
            if 0 <= gx < len(grid) and 0 <= gz < len(grid[0]):
                cost_direct += grid[gx][gz]
            else:
                cost_direct += 1.0

        cost_astar = sum(grid[gx][gz] for gx, gz in path if 0 <= gx < len(grid) and 0 <= gz < len(grid[0]))
        if cost_direct > 0.0:
            saved = (cost_direct - cost_astar) / cost_direct * 100.0
        else:
            saved = 0.0
        target_o2_saved = max(0.0, min(25.0, saved))
    else:
        target_o2_saved = 11.4 + abs(math.sin(state.pos_x * 0.2)) * 4.5
        state.astar_waypoints = []

    state.o2_saved_pct += (target_o2_saved - state.o2_saved_pct) * 0.15

    # Modelo metabólico NASA EVA: kcal/min = 6.0 + 0.9*|pendiente| + 2.0*velocidad
    slope_now = get_slope_deg(state.pos_x, state.pos_z)
    kcal_per_min = 6.0 + 0.9 * abs(slope_now) + 2.0 * state.speed_m_s
    state.kcal_burned += kcal_per_min * (dt / 60.0)

    state.avoidance_offset += (avoid_shift - state.avoidance_offset) * 0.15

    p0 = (
        state.pos_x + math.sin(look_rad) * 1.3,
        state.pos_z - math.cos(look_rad) * 1.3
    )
    perp_look = look_rad + math.pi * 0.5
    p1 = (
        state.pos_x + math.sin(look_rad) * (corridor_len * 0.42) + math.sin(perp_look) * state.avoidance_offset,
        state.pos_z - math.cos(look_rad) * (corridor_len * 0.42) - math.cos(perp_look) * state.avoidance_offset
    )
    clamped_turn = max(-1.15, min(1.15, heading_err))
    goal_dir_rad = look_rad + clamped_turn
    p2 = (
        state.pos_x + math.sin(goal_dir_rad) * corridor_len,
        state.pos_z - math.cos(goal_dir_rad) * corridor_len
    )

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    steps = 22
    anim_phase = (time.time() * 1.8) % 1.0

    for lane_offset in (-0.52, 0.52):
        left_pts = []
        right_pts = []
        spine_pts = []

        for i in range(steps + 1):
            t = i / steps
            inv_t = 1.0 - t

            bx = (inv_t ** 2) * p0[0] + 2 * inv_t * t * p1[0] + (t ** 2) * p2[0]
            bz = (inv_t ** 2) * p0[1] + 2 * inv_t * t * p1[1] + (t ** 2) * p2[1]

            tx = 2 * inv_t * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
            tz = 2 * inv_t * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
            tangent = math.atan2(tx, -tz)
            perp = tangent + math.pi * 0.5

            cur_lane = lane_offset * (1.0 - t * 0.26)
            half_w = 0.22 * (1.0 - t * 0.40)

            cx = bx + math.sin(perp) * cur_lane
            cz = bz - math.cos(perp) * cur_lane
            base_y = (state.pos_y - 1.5) if state.scenario in ("launch", "tli") else get_terrain_height(cx, cz)
            cy = base_y + 0.07

            lx = cx - math.sin(perp) * half_w
            lz = cz + math.cos(perp) * half_w
            rx = cx + math.sin(perp) * half_w
            rz = cz - math.cos(perp) * half_w

            pL = project_point_3d(lx, cy, lz, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
            pR = project_point_3d(rx, cy, rz, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
            pC = project_point_3d(cx, cy, cz, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)

            if pL and pR and pC:
                left_pts.append((pL[0], pL[1]))
                right_pts.append((pR[0], pR[1]))
                spine_pts.append({
                    "sx": pC[0], "sy": pC[1],
                    "cx": cx, "cy": cy, "cz": cz,
                    "tangent": tangent, "perp": perp, "half_w": half_w
                })

        # Dibujar segmentos con degradado de color (Ámbar -> Rojo en alerta / Ámbar -> Cian en ruta / Verde en Fail-Safe)
        for i in range(len(left_pts) - 1):
            t = i / max(1, len(left_pts) - 1)
            if state.failsafe_mode:
                r, g, b = 20, int(180 + t * 70), 40
                alpha = int(110 + t * 80)
            elif is_critical or is_warning:
                r = int(255)
                g = int(190 * (1.0 - t * 0.78))
                b = int(60 * (1.0 - t))
                alpha = int(115 + t * 95)
            else:
                r = int(255 * (1.0 - t * 0.85))
                g = int(185 + t * 55)
                b = int(75 + t * 180)
                alpha = int(105 + t * 95)

            quad = [left_pts[i], left_pts[i + 1], right_pts[i + 1], right_pts[i]]
            pygame.draw.polygon(overlay, (r, g, b, alpha), quad)
            pygame.draw.line(overlay, (255, 230, 150, 190), left_pts[i], left_pts[i + 1], 2)
            pygame.draw.line(overlay, (255, 230, 150, 190), right_pts[i], right_pts[i + 1], 2)

        # Punta triangular de la flecha
        last = spine_pts[-1]
        tip_dist = 1.05
        wing_w = last["half_w"] * 2.15
        p_tip = project_point_3d(
            last["cx"] + math.sin(last["tangent"]) * tip_dist,
            last["cy"],
            last["cz"] - math.cos(last["tangent"]) * tip_dist,
            state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT
        )
        p_wl = project_point_3d(
            last["cx"] - math.sin(last["perp"]) * wing_w,
            last["cy"],
            last["cz"] + math.cos(last["perp"]) * wing_w,
            state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT
        )
        p_wr = project_point_3d(
            last["cx"] + math.sin(last["perp"]) * wing_w,
            last["cy"],
            last["cz"] - math.cos(last["perp"]) * wing_w,
            state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT
        )
        if p_tip and p_wl and p_wr:
            head_col = (255, 48, 30, 225) if (is_critical or is_warning) else (0, 238, 255, 225)
            head_poly = [(p_wl[0], p_wl[1]), (p_tip[0], p_tip[1]), (p_wr[0], p_wr[1])]
            pygame.draw.polygon(overlay, head_col, head_poly)
            pygame.draw.polygon(overlay, (255, 235, 170, 220), head_poly, 2)

        # Chevrons oscuros animados dentro de cada flecha
        for base_t in (0.10, 0.24, 0.38):
            ct = (base_t + anim_phase * 0.14) % 0.48
            idx = min(len(spine_pts) - 4, max(1, int(ct * len(spine_pts))))
            tip_c = spine_pts[idx + 2]
            next_tip = spine_pts[idx + 3]
            chev_poly = [
                left_pts[idx],
                (tip_c["sx"], tip_c["sy"]),
                right_pts[idx],
                right_pts[idx + 1],
                (next_tip["sx"], next_tip["sy"]),
                left_pts[idx + 1]
            ]
            pygame.draw.polygon(overlay, (14, 10, 6, 155), chev_poly)

    surface.blit(overlay, (0, 0))
    return abs_err_deg, heading_err, dist_goal, is_warning, is_critical


# =============================================================================
# RENDERIZADO DE LA ESCENA 3D PRINCIPAL Y CÁMARA TRASERA 180°
# =============================================================================
def render_3d_world(surface, state: SuitState, font_sm):
    # Color de cielo según escenario
    if state.scenario == "launch":
        surface.fill((8, 24, 58))
    elif state.scenario == "solar_storm":
        surface.fill((36, 8, 10))
    else:
        surface.fill((3, 6, 12))

    # Estrellas
    for sx, sy, sz in state.stars:
        proj = project_point_3d(
            state.pos_x + sx, sy, state.pos_z + sz,
            state.pos_x, state.pos_y, state.pos_z,
            state.heading, state.pitch, WIDTH, HEIGHT
        )
        if proj:
            pygame.draw.circle(surface, (210, 235, 255), (proj[0], proj[1]), 1)

    # Planeta Tierra en el horizonte
    earth_p = project_point_3d(32.0, 26.0, -110.0, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
    if earth_p:
        er = max(8, int(2200 / earth_p[2]))
        pygame.draw.circle(surface, (35, 115, 245), (earth_p[0], earth_p[1]), er)
        pygame.draw.circle(surface, (130, 200, 255), (earth_p[0], earth_p[1]), er, 2)

    # Malla de Terreno Lunar 3D (si no estamos en TLI espacial)
    if state.scenario != "tli":
        grid_step = 2.5
        base_gx = int(state.pos_x // grid_step) * grid_step
        base_gz = int(state.pos_z // grid_step) * grid_step

        for gz_i in range(14, -6, -1):
            for gx_i in range(-10, 10):
                x0 = base_gx + gx_i * grid_step
                z0 = base_gz - gz_i * grid_step
                x1 = x0 + grid_step
                z1 = z0 - grid_step

                y00 = get_terrain_height(x0, z0)
                y10 = get_terrain_height(x1, z0)
                y11 = get_terrain_height(x1, z1)
                y01 = get_terrain_height(x0, z1)

                p00 = project_point_3d(x0, y00, z0, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
                p10 = project_point_3d(x1, y10, z0, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
                p11 = project_point_3d(x1, y11, z1, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
                p01 = project_point_3d(x0, y01, z1, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)

                if p00 and p10 and p11 and p01:
                    dist_fade = max(0.15, min(1.0, 1.0 - p00[2] / 42.0))
                    if state.scenario == "psr_dark":
                        dist_fade *= 0.35
                    shade = int((52 + (y00 + 0.5) * 24) * dist_fade)
                    shade = max(12, min(115, shade))
                    poly = [(p00[0], p00[1]), (p10[0], p10[1]), (p11[0], p11[1]), (p01[0], p01[1])]
                    pygame.draw.polygon(surface, (shade, shade + 2, shade + 6), poly)

                    line_col = (0, 190, 220) if state.optical_filter == "lidar" else (shade + 18, shade + 22, shade + 28)
                    pygame.draw.polygon(surface, line_col, poly, 1)

    # Onda de Escaneo LIDAR 3D
    if state.lidar_wave_r > 0:
        pts_lidar = []
        for a in range(0, 360, 10):
            rad = math.radians(a)
            lx = state.pos_x + math.sin(rad) * state.lidar_wave_r
            lz = state.pos_z - math.cos(rad) * state.lidar_wave_r
            ly = get_terrain_height(lx, lz) + 0.12
            lp = project_point_3d(lx, ly, lz, state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
            if lp:
                pts_lidar.append((lp[0], lp[1]))
        if len(pts_lidar) > 3:
            pygame.draw.lines(surface, (16, 245, 150), False, pts_lidar, 3)

    # Rocas 3D y cálculo de obstáculo más cercano + Telémetro Láser
    min_rock_d = 99.9
    best_reticle_hit = (4.8 / max(0.15, math.sin(math.radians(abs(state.pitch) + 6))), "REGOLITO LUNAR")

    for rock in state.rocks:
        d = math.hypot(rock["x"] - state.pos_x, rock["z"] - state.pos_z)
        if d < min_rock_d:
            min_rock_d = d
        ry = get_terrain_height(rock["x"], rock["z"]) + rock["r"] * 0.4
        rp = project_point_3d(rock["x"], ry, rock["z"], state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
        if rp and rp[2] < 38.0:
            r_px = max(5, int((rock["r"] * 480) / rp[2]))
            pygame.draw.circle(surface, (82, 88, 98), (rp[0], rp[1]), r_px)
            pygame.draw.circle(surface, (125, 135, 148), (rp[0], rp[1]), r_px, 1)

            # Si está en la retícula central, actualizar Telémetro Láser
            if math.hypot(rp[0] - WIDTH // 2, rp[1] - HEIGHT // 2) < r_px + 18:
                best_reticle_hit = (rp[2], "ROCA BASÁLTICA")

            # Caja AR de advertencia para rocas cercanas
            if d < 6.5:
                box_col = (255, 50, 50) if d < 2.8 else (255, 185, 40)
                rect = pygame.Rect(rp[0] - r_px - 4, rp[1] - r_px - 4, (r_px + 4) * 2, (r_px + 4) * 2)
                pygame.draw.rect(surface, box_col, rect, 1)
                lbl = font_sm.render(f"! {d:.1f}m", True, box_col)
                surface.blit(lbl, (rect.x, rect.y - 14))

    state.nearest_rock_dist = min_rock_d

    # Estructuras 3D de los Waypoints
    for idx, wp in enumerate(state.waypoints):
        wy = get_terrain_height(wp["x"], wp["z"]) + 1.1
        wproj = project_point_3d(wp["x"], wy, wp["z"], state.pos_x, state.pos_y, state.pos_z, state.heading, state.pitch, WIDTH, HEIGHT)
        if wproj:
            sz = max(8, int(650 / wproj[2]))
            pygame.draw.rect(surface, wp["color"], (wproj[0] - sz // 2, wproj[1] - sz, sz, sz * 1.4), 2)
            if math.hypot(wproj[0] - WIDTH // 2, wproj[1] - HEIGHT // 2) < sz + 20:
                best_reticle_hit = (wproj[2], wp["name"].upper())

            if idx == state.active_wp_idx:
                diamond = [
                    (wproj[0], wproj[1] - sz - 18),
                    (wproj[0] + 9, wproj[1] - sz - 9),
                    (wproj[0], wproj[1] - sz),
                    (wproj[0] - 9, wproj[1] - sz - 9)
                ]
                pygame.draw.polygon(surface, (0, 240, 255), diamond, 2)

    state.rangefinder_dist = min(99.9, best_reticle_hit[0])
    state.rangefinder_target = best_reticle_hit[1]
    state.sensors[0]["val"] = min(25.0, state.rangefinder_dist)
    state.sensors[1]["val"] = min(10.0, state.nearest_rock_dist)


def render_rear_pip_camera(surface, state: SuitState, font_sm):
    """Renderiza el recuadro de Cámara Trasera 180° en la esquina superior derecha."""
    pip_w, pip_h = 164, 102
    pip_x, pip_y = WIDTH - pip_w - 24, 18

    pip_surf = pygame.Surface((pip_w, pip_h))
    pip_surf.fill((4, 10, 18))

    rear_heading = (state.heading + 180.0) % 360.0
    # Horizonte trasero
    pygame.draw.rect(pip_surf, (28, 34, 42), (0, pip_h // 2, pip_w, pip_h // 2))
    pygame.draw.line(pip_surf, (0, 240, 255), (0, pip_h // 2), (pip_w, pip_h // 2), 1)

    # Proyectar rocas y waypoints detrás del astronauta
    for rock in state.rocks:
        ry = get_terrain_height(rock["x"], rock["z"]) + rock["r"] * 0.4
        rp = project_point_3d(rock["x"], ry, rock["z"], state.pos_x, state.pos_y, state.pos_z, rear_heading, -4.0, pip_w, pip_h, 75.0)
        if rp and rp[2] < 25.0:
            r_px = max(3, int((rock["r"] * 120) / rp[2]))
            col = (255, 70, 70) if rp[2] < 3.5 else (130, 145, 160)
            pygame.draw.circle(pip_surf, col, (rp[0], rp[1]), r_px)

    # Arco de radar trasero
    pygame.draw.arc(pip_surf, (0, 240, 255), (pip_w // 2 - 34, pip_h - 38, 68, 52), 0, math.pi, 1)
    lbl = font_sm.render(f"CÁM. TRASERA 180° [{int(rear_heading):03d}°]", True, (0, 240, 255))
    pip_surf.blit(lbl, (6, 5))

    surface.blit(pip_surf, (pip_x, pip_y))
    pygame.draw.rect(surface, (0, 240, 255), (pip_x, pip_y, pip_w, pip_h), 2, border_radius=6)


# =============================================================================
# PANTALLA TÁCTICA EN LA MUÑECA (WRIST TERMINAL INTERACTIVA)
# =============================================================================
def render_wrist_display(surface, state: SuitState, fonts, ui_buttons):
    target_anim = 1.0 if state.wrist_raised else 0.0
    state.wrist_anim += (target_anim - state.wrist_anim) * 0.18

    panel_w, panel_h = 420, 285
    base_x = 24
    # Desplazamiento vertical suave al levantar o bajar la muñeca
    base_y = int(HEIGHT - 54 - (panel_h * state.wrist_anim))

    # Botón superior del brazalete (Siempre visible para levantar/bajar con clic o TAB)
    toggle_rect = pygame.Rect(base_x, base_y - 32, 248, 30)
    ui_buttons["toggle_wrist"] = toggle_rect
    pygame.draw.rect(surface, (0, 225, 255), toggle_rect, border_radius=6)
    arrow_txt = "▼ BAJAR (TAB)" if state.wrist_raised else "▲ PANTALLA DE MUÑECA (TAB)"
    surface.blit(fonts["bold"].render(arrow_txt, True, (5, 12, 22)), (toggle_rect.x + 10, toggle_rect.y + 6))

    if state.wrist_anim < 0.05:
        return

    # Manga del traje espacial + Pantalla OLED de Muñeca
    wrist_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    pygame.draw.rect(wrist_surf, (18, 26, 38, 245), (0, 0, panel_w, panel_h), border_radius=14)
    pygame.draw.rect(wrist_surf, (6, 18, 32, 250), (8, 8, panel_w - 16, panel_h - 16), border_radius=10)
    pygame.draw.rect(wrist_surf, (0, 240, 255, 200), (8, 8, panel_w - 16, panel_h - 16), 2, border_radius=10)

    # Cabecera del terminal de muñeca
    wrist_surf.blit(fonts["bold"].render("xEMU WRIST TERMINAL v4.2", True, (0, 240, 255)), (20, 16))
    hw_col = (16, 235, 140) if state.esp32_connected else (160, 175, 195)
    wrist_surf.blit(fonts["sm"].render(f"ESP32: {state.esp32_port}", True, hw_col), (panel_w - 145, 18))

    # 4 Pestañas interactivas
    tab_names = ["SENSORES", "NAVEGACIÓN", "AMBIENTE", "ESP32 / AR"]
    for i, tname in enumerate(tab_names):
        tx = 18 + i * 96
        ty = 42
        trect = pygame.Rect(base_x + tx, base_y + ty, 90, 24)
        ui_buttons[f"wtab_{i}"] = trect

        active = (state.wrist_tab == i)
        bg = (0, 190, 220, 95) if active else (15, 30, 48, 200)
        border = (0, 240, 255) if active else (0, 140, 170)
        pygame.draw.rect(wrist_surf, bg, (tx, ty, 90, 24), border_radius=4)
        pygame.draw.rect(wrist_surf, border, (tx, ty, 90, 24), 1, border_radius=4)
        wrist_surf.blit(fonts["sm"].render(tname, True, (255, 255, 255) if active else (150, 215, 235)), (tx + 10, ty + 5))

    # Contenido según pestaña activa
    if state.wrist_tab == 0:
        # PESTAÑA 1: SENSORES Y ESPECTRÓMETRO
        y_off = 76
        for s in state.sensors[:5]:
            wrist_surf.blit(fonts["sm"].render(s["name"], True, (110, 240, 190)), (22, y_off))
            val_txt = f"{s['val']:.1f} {s['unit']}"
            wrist_surf.blit(fonts["sm"].render(val_txt, True, (220, 245, 255)), (170, y_off))

            pct = max(0.05, min(1.0, (s["val"] - s["min"]) / max(1.0, s["max"] - s["min"])))
            pygame.draw.rect(wrist_surf, (20, 40, 60), (245, y_off + 3, 145, 9), border_radius=3)
            pygame.draw.rect(wrist_surf, (16, 225, 140), (245, y_off + 3, int(145 * pct), 9), border_radius=3)
            y_off += 28

        # Botón Añadir Sensor y Espectrómetro
        btn_add = pygame.Rect(base_x + 22, base_y + 225, 170, 26)
        ui_buttons["add_sensor"] = btn_add
        pygame.draw.rect(wrist_surf, (0, 160, 200, 90), (22, 225, 170, 26), border_radius=4)
        pygame.draw.rect(wrist_surf, (0, 240, 255), (22, 225, 170, 26), 1, border_radius=4)
        wrist_surf.blit(fonts["sm"].render("+ INSTALAR SENSOR AUX.", True, (220, 250, 255)), (32, 231))

        wrist_surf.blit(fonts["sm"].render(f"Espectro: {state.spectro_last[:22]}", True, (250, 204, 21)), (204, 231))

    elif state.wrist_tab == 1:
        # PESTAÑA 2: NAVEGACIÓN Y WAYPOINTS
        wrist_surf.blit(fonts["sm"].render("SELECCIONAR DESTINO DEL CORREDOR:", True, (250, 204, 21)), (22, 76))
        # Mostrar metabolismo acumulado
        slope_now = get_slope_deg(state.pos_x, state.pos_z)
        kcal_per_min = 6.0 + 0.9 * abs(slope_now) + 2.0 * state.speed_m_s
        wrist_surf.blit(fonts["sm"].render(f"KCAL ACUM: {state.kcal_burned:.1f}  ({kcal_per_min:.1f} kcal/min)", True, (16, 235, 150)), (22, 58))
        for idx, wp in enumerate(state.waypoints):
            wy = 98 + idx * 28
            wrect = pygame.Rect(base_x + 22, base_y + wy, 250, 24)
            ui_buttons[f"wp_{idx}"] = wrect
            sel = (idx == state.active_wp_idx)
            pygame.draw.rect(wrist_surf, (245, 158, 11, 85) if sel else (15, 28, 44), (22, wy, 250, 24), border_radius=4)
            pygame.draw.rect(wrist_surf, (250, 204, 21) if sel else (60, 90, 120), (22, wy, 250, 24), 1, border_radius=4)
            wrist_surf.blit(fonts["sm"].render(f"WP-0{idx+1}: {wp['name']}", True, (255, 255, 255)), (30, wy + 5))

        # Globo Holográfico 3D giratorio en la muñeca
        gx, gy, gr = 340, 145, 44
        pygame.draw.circle(wrist_surf, (0, 220, 255, 40), (gx, gy), gr)
        pygame.draw.circle(wrist_surf, (0, 240, 255), (gx, gy), gr, 1)
        rot = time.time() * 1.2
        for a in range(0, 180, 45):
            ew = max(4, int(abs(math.cos(rot + math.radians(a))) * gr))
            pygame.draw.ellipse(wrist_surf, (0, 200, 240), (gx - ew, gy - gr, ew * 2, gr * 2), 1)

        # Botones Centrar Ruta y Simular Desvío
        btn_center = pygame.Rect(base_x + 22, base_y + 222, 180, 26)
        btn_anom = pygame.Rect(base_x + 214, base_y + 222, 180, 26)
        ui_buttons["center_route"] = btn_center
        ui_buttons["toggle_anomaly"] = btn_anom
        pygame.draw.rect(wrist_surf, (16, 185, 129, 90), (22, 222, 180, 26), border_radius=4)
        pygame.draw.rect(wrist_surf, (244, 63, 94, 90), (214, 222, 180, 26), border_radius=4)
        wrist_surf.blit(fonts["sm"].render("CENTRAR RUTA AL OBJETIVO", True, (220, 255, 240)), (30, 228))
        wrist_surf.blit(fonts["sm"].render("SIMULAR DESVÍO DE RUMBO", True, (255, 220, 225)), (224, 228))

    elif state.wrist_tab == 2:
        # PESTAÑA 3: TELEMETRÍA AMBIENTAL Y ESCENARIOS
        temp_amb = -210.4 if state.scenario == "psr_dark" else -170.0
        slope = abs(math.sin(state.pos_x * 0.25) * 6.5)
        wrist_surf.blit(fonts["sm"].render(f"TEMP. SUPERFICIE: {temp_amb:.1f} °C", True, (0, 240, 255)), (22, 82))
        wrist_surf.blit(fonts["sm"].render(f"INCLINACIÓN TERRENO: {slope:.1f}° ESTABLE", True, (16, 235, 150)), (22, 108))
        wrist_surf.blit(fonts["sm"].render(f"POLVO EN VISOR: {state.dust_opacity}% OPACIDAD", True, (250, 204, 21)), (22, 134))
        wrist_surf.blit(fonts["sm"].render(f"ELEVACIÓN SOLAR: {state.solar_deg:.1f}° SOBRE HORIZ.", True, (255, 255, 255)), (22, 160))

        btn_purge = pygame.Rect(base_x + 22, base_y + 195, 180, 26)
        btn_scen = pygame.Rect(base_x + 214, base_y + 195, 180, 26)
        ui_buttons["purge_dust"] = btn_purge
        ui_buttons["next_scenario"] = btn_scen
        pygame.draw.rect(wrist_surf, (14, 165, 233, 90), (22, 195, 180, 26), border_radius=4)
        pygame.draw.rect(wrist_surf, (245, 158, 11, 90), (214, 195, 180, 26), border_radius=4)
        wrist_surf.blit(fonts["sm"].render("PURGAR POLVO DEL VISOR", True, (225, 245, 255)), (32, 201))
        wrist_surf.blit(fonts["sm"].render("CAMBIAR ESCENARIO (F)", True, (255, 245, 215)), (226, 201))

    else:
        # PESTAÑA 4: CONEXIÓN ESP32 USB, CÁMARA OPENCV Y FILTROS
        btn_esp = pygame.Rect(base_x + 22, base_y + 78, 180, 28)
        btn_cam = pygame.Rect(base_x + 214, base_y + 78, 180, 28)
        ui_buttons["connect_esp32"] = btn_esp
        ui_buttons["toggle_webcam"] = btn_cam
        pygame.draw.rect(wrist_surf, (0, 180, 215, 95), (22, 78, 180, 28), border_radius=4)
        pygame.draw.rect(wrist_surf, (16, 185, 129, 95), (214, 78, 180, 28), border_radius=4)
        wrist_surf.blit(fonts["sm"].render("CONECTAR ESP32 USB", True, (255, 255, 255)), (40, 85))
        wrist_surf.blit(fonts["sm"].render("ACTIVAR CÁMARA OPENCV", True, (255, 255, 255)), (225, 85))

        # Lista de puertos COM disponibles como botones pulsables
        wrist_surf.blit(fonts["sm"].render("PUERTOS DISPONIBLES:", True, (250, 204, 21)), (22, 118))
        ports = []
        if PYSERIAL_AVAILABLE:
            try:
                ports = list(serial.tools.list_ports.comports())
            except Exception:
                ports = []
        for idx, p in enumerate(ports[:6]):
            px = 22 + (idx % 3) * 130
            py = 138 + (idx // 3) * 24
            port_name = p.device
            prect = pygame.Rect(base_x + px, base_y + py, 120, 20)
            ui_buttons[f"com_port_{port_name}"] = prect
            sel = (state.esp32_port == port_name and state.esp32_connected)
            pygame.draw.rect(wrist_surf, (0, 160, 200, 130) if sel else (15, 30, 48), (px, py, 120, 20), border_radius=3)
            pygame.draw.rect(wrist_surf, (0, 240, 255) if sel else (60, 90, 120), (px, py, 120, 20), 1, border_radius=3)
            wrist_surf.blit(fonts["sm"].render(port_name, True, (255, 255, 255)), (px + 8, py + 4))

        wrist_surf.blit(fonts["sm"].render("LOG DEL SISTEMA PYTHON:", True, (0, 240, 255)), (22, 192))
        for idx, log_line in enumerate(state.sys_logs[:4]):
            wrist_surf.blit(fonts["sm"].render(log_line[:48], True, (140, 235, 190)), (22, 212 + idx * 18))

    surface.blit(wrist_surf, (base_x, base_y))


def detect_real_obstacles_opencv(frame_bgr, state: SuitState):
    """Visión Artificial Real con OpenCV (Canny + Contornos) sobre la cámara web."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blur, 55, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected = []
    h_img, w_img = gray.shape[:2]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 1400 < area < (w_img * h_img * 0.45):
            x, y, w, h = cv2.boundingRect(cnt)
            # Estimar distancia inversa al tamaño aparente del obstáculo real
            est_dist = max(0.6, min(12.0, 260.0 / max(20, math.hypot(w, h))))
            detected.append((x, y, w, h, est_dist))

    detected.sort(key=lambda item: item[4])
    state.cv_obstacles = detected[:5]
    if state.cv_obstacles:
        state.nearest_rock_dist = min(state.nearest_rock_dist, state.cv_obstacles[0][4])


# =============================================================================
# EFEMÉRIDES REALES NASA JPL HORIZONS (Polo Sur Lunar 89.9°S)
# =============================================================================
def consultar_horizons(body):
    """
    Consulta azimut/elevación para el Sol ('sun') o la Tierra ('earth')
    desde el Polo Sur Lunar (89.9°S, 0°E) usando urllib de la stdlib.
    Devuelve (azimuth, elevation) o (None, None) si falla.
    """
    command = {"sun": "10", "earth": "399"}.get(body.lower())
    if command is None:
        return None, None

    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    end = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 3600))
    params = urllib.parse.urlencode({
        "format": "text",
        "COMMAND": f"'{command}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": "'-89.9,0.0,0'",
        "START_TIME": f"'{now}'",
        "STOP_TIME": f"'{end}'",
        "STEP_SIZE": "'30m'",
        "QUANTITIES": "'4'"
    })
    url = f"https://ssd.jpl.nasa.gov/api/horizons.api?{params}"
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            text = response.read().decode("utf-8", errors="ignore")
        soe = text.find("$$SOE")
        eoe = text.find("$$EOE")
        if soe == -1 or eoe == -1 or eoe <= soe:
            return None, None
        block = text[soe + 5:eoe].strip()
        for line in block.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                try:
                    az = float(parts[-2])
                    el = float(parts[-1])
                    if 0.0 <= az <= 360.0 and -90.0 <= el <= 90.0:
                        return az, el
                except ValueError:
                    continue
        return None, None
    except Exception:
        return None, None


class HorizonsPoller(threading.Thread):
    """Hilo en segundo plano que actualiza efemérides cada 60 s sin bloquear pygame."""
    def __init__(self, state: SuitState):
        super().__init__(daemon=True)
        self.state = state
        self.running = True
        self.last_sun_az, self.last_sun_el = 180.0, 0.0
        self.last_earth_az, self.last_earth_el = 0.0, 0.0

    def run(self):
        while self.running:
            az_s, el_s = consultar_horizons("sun")
            if az_s is not None:
                self.last_sun_az, self.last_sun_el = az_s, el_s
            else:
                self.state.log("HORIZONS sin conexion, usando ultimo valor")

            az_e, el_e = consultar_horizons("earth")
            if az_e is not None:
                self.last_earth_az, self.last_earth_el = az_e, el_e
            else:
                self.state.log("HORIZONS sin conexion, usando ultimo valor")

            self.state.solar_azimuth = self.last_sun_az
            self.state.solar_elevation = self.last_sun_el
            self.state.earth_los = (self.last_earth_el >= 0.0)
            time.sleep(60.0)


# =============================================================================
# BUCLE PRINCIPAL DE EJECUCIÓN EN PYTHON
# =============================================================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Visor AR Primera Persona & Pantalla de Muñeca - Casco Lunar HUD (Python)")
    clock = pygame.time.Clock()

    fonts = {
        "sm": pygame.font.SysFont("consolas", 13),
        "bold": pygame.font.SysFont("consolas", 15, bold=True),
        "lg": pygame.font.SysFont("consolas", 19, bold=True)
    }

    state = SuitState()
    serial_worker = ESP32SerialReader(state)
    serial_worker.start()
    horizons_poller = HorizonsPoller(state)
    horizons_poller.start()

    cap = None
    dragging_mouse = False
    prev_comm_mode = state.comm_mode

    running = True
    while running:
        dt = clock.tick(20 if state.failsafe_mode else FPS) / 1000.0
        ui_buttons = {}

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    state.wrist_raised = not state.wrist_raised
                elif event.key == pygame.K_e:
                    state.lidar_wave_r = 0.8
                    state.log("Pulso LIDAR 3D emitido.")
                elif event.key == pygame.K_SPACE:
                    state.samples_count += 1
                    state.spectro_last = random.choice(["Basalto + 14% Ilmenita", "Regolito + 8.6% Hielo H2O", "Brecha Helio-3"])
                    state.log(f"Muestra #{state.samples_count}: {state.spectro_last}")
                elif event.key == pygame.K_f:
                    state.scenario_idx = (state.scenario_idx + 1) % len(SCENARIOS)
                    state.scenario = SCENARIOS[state.scenario_idx][0]
                    state.descent_alt = 38.0
                    state.log(f"Escenario activo: {SCENARIOS[state.scenario_idx][1]}")
                elif event.key == pygame.K_c:
                    wp = state.waypoints[state.active_wp_idx]
                    state.heading = (math.degrees(math.atan2(wp["x"] - state.pos_x, -(wp["z"] - state.pos_z))) + 360.0) % 360.0
                    state.course_anomaly = 0.0
                elif event.key == pygame.K_m:
                    state.failsafe_mode = not state.failsafe_mode
                    state.log("MODO FAIL-SAFE MONOCROMÁTICO ACTIVO" if state.failsafe_mode else "Modo nominal restaurado.")

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    clicked_ui = False
                    # Revisar clics sobre la pantalla de muñeca
                    render_wrist_display(screen, state, fonts, ui_buttons)
                    for btn_id, rect in ui_buttons.items():
                        if rect.collidepoint(event.pos):
                            clicked_ui = True
                            if btn_id == "toggle_wrist":
                                state.wrist_raised = not state.wrist_raised
                            elif btn_id.startswith("wtab_"):
                                state.wrist_tab = int(btn_id.split("_")[1])
                                state.wrist_raised = True
                            elif btn_id.startswith("wp_"):
                                state.active_wp_idx = int(btn_id.split("_")[1])
                                state.log(f"Destino fijado: {state.waypoints[state.active_wp_idx]['name']}")
                            elif btn_id == "center_route":
                                wp = state.waypoints[state.active_wp_idx]
                                state.heading = (math.degrees(math.atan2(wp["x"] - state.pos_x, -(wp["z"] - state.pos_z))) + 360.0) % 360.0
                                state.course_anomaly = 0.0
                            elif btn_id == "toggle_anomaly":
                                state.course_anomaly = 0.65 if state.course_anomaly == 0.0 else 0.0
                            elif btn_id == "purge_dust":
                                state.dust_opacity = 0
                                state.log("Purga electrostática del visor completada.")
                            elif btn_id == "next_scenario":
                                state.scenario_idx = (state.scenario_idx + 1) % len(SCENARIOS)
                                state.scenario = SCENARIOS[state.scenario_idx][0]
                                state.descent_alt = 38.0
                            elif btn_id == "add_sensor":
                                state.sensors.append({"id": "aux", "name": "Telémetro Aux.", "val": 6.2, "unit": "m", "min": 0.0, "max": 20.0})
                                state.log("Nuevo sensor instalado en el traje.")
                            elif btn_id == "connect_esp32":
                                serial_worker.try_connect()
                            elif btn_id.startswith("com_port_"):
                                port_name = btn_id.split("_", 2)[2]
                                serial_worker.try_connect(manual_port=port_name)
                            elif btn_id == "toggle_webcam":
                                if OPENCV_AVAILABLE:
                                    if not state.use_webcam:
                                        cap = cv2.VideoCapture(0)
                                        state.use_webcam = cap.isOpened()
                                        state.log("Cámara física OpenCV activada." if state.use_webcam else "No se detectó webcam.")
                                    else:
                                        if cap:
                                            cap.release()
                                        state.use_webcam = False
                                        state.log("Cámara desactivada; usando terreno 3D.")
                                else:
                                    state.log("Instala opencv-python para usar la cámara.")
                            break
                    if not clicked_ui:
                        dragging_mouse = True

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    dragging_mouse = False

            elif event.type == pygame.MOUSEMOTION and dragging_mouse:
                rel_x, rel_y = event.rel
                state.heading = (state.heading - rel_x * 0.25 + 360.0) % 360.0
                state.pitch = max(-42.0, min(32.0, state.pitch - rel_y * 0.20))

        # Movimiento en primera persona con WASD o Flechas
        keys = pygame.key.get_pressed()
        rad = math.radians(state.heading)
        moved = False
        state.speed_m_s = 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            state.pos_x += math.sin(rad) * 3.8 * dt
            state.pos_z -= math.cos(rad) * 3.8 * dt
            state.speed_m_s = 3.8
            moved = True
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            state.pos_x -= math.sin(rad) * 2.0 * dt
            state.pos_z += math.cos(rad) * 2.0 * dt
            state.speed_m_s = 2.0
            moved = True
        # 1. Renderizar Fondo (Webcam OpenCV con Visión Artificial o Escena Lunar 3D)
        if state.use_webcam and cap and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (WIDTH, HEIGHT))
                detect_real_obstacles_opencv(frame, state)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                cam_surf = pygame.surfarray.make_surface(np.rot90(np.fliplr(frame_rgb)))
                screen.blit(cam_surf, (0, 0))

                # Dibujar cajas AR rojas/ámbar sobre los objetos físicos reales detectados por OpenCV
                for (ox, oy, ow, oh, odist) in state.cv_obstacles:
                    col = (255, 45, 45) if odist < 2.5 else (255, 190, 40)
                    pygame.draw.rect(screen, col, (ox, oy, ow, oh), 2)
                    lbl = fonts["sm"].render(f"OBJETO REAL OpenCV: {odist:.1f}m", True, col)
                    screen.blit(lbl, (ox, max(10, oy - 16)))
            else:
                render_3d_world(screen, state, fonts["sm"])
        else:
            render_3d_world(screen, state, fonts["sm"])

        # 2. Dibujar Corredor Holográfico de 2 Flechas con Chevrons + Ruta Inteligente A*
        abs_err_deg, heading_err, dist_goal, is_warning, is_critical = draw_dual_ribbon_corridor(screen, state, dt)

        # Efemérides Astronómicas Reales del Polo Sur Lunar (89.9°S) y Sistema C&W
        # (actualizadas por HorizonsPoller en segundo plano)
        # Cambio de modo de comunicación según línea de vista Tierra
        new_comm_mode = "DTE TIERRA" if state.earth_los else "GATEWAY"
        if new_comm_mode != state.comm_mode:
            state.comm_mode = new_comm_mode
            if state.comm_mode == "GATEWAY":
                state.log("COM: conmutado a RELÉ LUNAR GATEWAY (Tierra oculta)")
            else:
                state.log("COM: restablecido DTE TIERRA")

        # Drenaje de batería y acumulación de radiación
        state.battery_pct = max(0.0, state.battery_pct - 0.05 * (dt / 60.0))
        if state.scenario == "solar_storm":
            state.radiation_uSv += random.uniform(8.0, 22.0) * dt

        # Fail-safe automático
        class1_sustained = (state.cw_class == 1 and state.cw_class_1_since > 0.0 and (time.time() - state.cw_class_1_since) >= 5.0)
        if not state.failsafe_mode and (state.battery_pct < 15.0 or state.radiation_uSv > 250.0 or class1_sustained):
            state.failsafe_mode = True
            state.log("FAIL-SAFE AUTOMATICO ACTIVADO (bateria/radiacion)")
        if state.cw_class == 1 and state.cw_class_1_since == 0.0:
            state.cw_class_1_since = time.time()
        elif state.cw_class != 1:
            state.cw_class_1_since = 0.0

        # Consumo metabólico instantáneo para mensajes
        slope_now = get_slope_deg(state.pos_x, state.pos_z)
        kcal_per_min = 6.0 + 0.9 * abs(slope_now) + 2.0 * state.speed_m_s

        if state.scenario == "solar_storm" or state.nearest_rock_dist < 2.2:
            state.cw_class = 1
            state.cw_message = "CLASE 1 EMERGENCIA: IMPACTO INMINENTE / RADIACION SPE"
        elif is_critical or is_warning:
            state.cw_class = 2
            state.cw_message = f"CLASE 2 WARNING: DESVIO {abs_err_deg:.0f}° (RUTA A*: ahorro O2 {state.o2_saved_pct:.1f}% / {kcal_per_min:.1f} kcal por minuto)"
        else:
            state.cw_class = 3
            relay_str = "DTE TIERRA" if state.earth_los else "GATEWAY"
            state.cw_message = f"CLASE 3 NOMINAL: A* OPTIMO (-{state.o2_saved_pct:.1f}% O2 / {kcal_per_min:.1f} kcal/min) · AZIMUT SOL {state.solar_azimuth:.1f}° · COM: {relay_str}"

        # Telemetría Bidireccional PC -> ESP32 cada 250ms
        if time.time() - state.last_esp_tx > 0.25:
            state.last_esp_tx = time.time()
            turn_cmd = "R" if heading_err > 0.25 else ("L" if heading_err < -0.25 else "C")
            serial_worker.send_haptic_command(1 if state.cw_class == 1 else (2 if state.cw_class == 2 else 0), turn_cmd)

        # 3. Dibujar Cámara Trasera 180° en la esquina superior derecha
        if not state.failsafe_mode:
            render_rear_pip_camera(screen, state, fonts["sm"])

        # 4. Barra Superior Minimalista: Rumbo + Distancia al Destino + Estado
        top_bar = pygame.Surface((650, 36), pygame.SRCALPHA)
        pygame.draw.rect(top_bar, (4, 14, 26, 185), (0, 0, 650, 36), border_radius=18)
        pygame.draw.rect(top_bar, (0, 240, 255, 160), (0, 0, 650, 36), 1, border_radius=18)

        wp_name = state.waypoints[state.active_wp_idx]["name"]
        status_txt = "EN RUMBO" if not (is_warning or is_critical) else f"DESVÍO {abs_err_deg:.0f}°"
        status_col = (16, 240, 150) if not (is_warning or is_critical) else ((255, 70, 70) if is_critical else (250, 190, 40))

        bar_str = f"RUMBO: {int(state.heading):03d}°  |  DESTINO: {wp_name} ({dist_goal:.1f}m)  |  {status_txt}"
        top_bar.blit(fonts["bold"].render(bar_str, True, status_col), (18, 9))
        screen.blit(top_bar, (WIDTH // 2 - 325, 18))

        # Indicador de Escenario Arriba a la Izquierda
        scen_lbl = SCENARIOS[state.scenario_idx][1]
        pygame.draw.rect(screen, (4, 14, 26), (22, 18, 305, 34), border_radius=6)
        pygame.draw.rect(screen, (0, 240, 255), (22, 18, 305, 34), 1, border_radius=6)
        screen.blit(fonts["sm"].render(f"{scen_lbl} [Tecla F]", True, (0, 240, 255)), (30, 28))

        # Indicador de modo de comunicación arriba a la derecha
        com_col = (16, 240, 150) if state.comm_mode == "DTE TIERRA" else (250, 190, 40)
        com_txt = f"COM: {state.comm_mode}"
        com_surf = fonts["sm"].render(com_txt, True, com_col)
        com_x = WIDTH - com_surf.get_width() - 22
        pygame.draw.rect(screen, (4, 14, 26), (com_x - 8, 18, com_surf.get_width() + 16, 24), border_radius=4)
        pygame.draw.rect(screen, com_col, (com_x - 8, 18, com_surf.get_width() + 16, 24), 1, border_radius=4)
        screen.blit(com_surf, (com_x, 23))

        # 5. Retícula Óptica Central + Telémetro Láser en Tiempo Real + Alerta de Peligro
        cx, cy = WIDTH // 2, HEIGHT // 2
        ret_col = (255, 60, 60) if state.nearest_rock_dist < 2.6 else (0, 240, 255)
        pygame.draw.circle(screen, ret_col, (cx, cy), 3)
        for dx_s, dy_s in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            pygame.draw.line(screen, ret_col, (cx + dx_s * 24, cy + dy_s * 24), (cx + dx_s * 14, cy + dy_s * 24), 2)
            pygame.draw.line(screen, ret_col, (cx + dx_s * 24, cy + dy_s * 24), (cx + dx_s * 24, cy + dy_s * 14), 2)

        rf_str = f"TELÉMETRO: {state.rangefinder_dist:.1f}m · {state.rangefinder_target}"
        rf_surf = fonts["bold"].render(rf_str, True, (180, 245, 255))
        pygame.draw.rect(screen, (3, 10, 18), (cx - rf_surf.get_width() // 2 - 8, cy + 32, rf_surf.get_width() + 16, 24), border_radius=4)
        screen.blit(rf_surf, (cx - rf_surf.get_width() // 2, cy + 36))

        if is_critical or state.nearest_rock_dist < 2.8:
            warn_msg = f"⚠ PELIGRO ROCA A {state.nearest_rock_dist:.1f}m" if state.nearest_rock_dist < 2.8 else "⚠ DESVÍO DE RUMBO - SEGUIR LAS 2 FLECHAS"
            w_surf = fonts["bold"].render(warn_msg, True, (255, 220, 220))
            pygame.draw.rect(screen, (140, 18, 30), (cx - w_surf.get_width() // 2 - 12, cy - 110, w_surf.get_width() + 24, 28), border_radius=6)
            pygame.draw.rect(screen, (255, 70, 70), (cx - w_surf.get_width() // 2 - 12, cy - 110, w_surf.get_width() + 24, 28), 2, border_radius=6)
            screen.blit(w_surf, (cx - w_surf.get_width() // 2, cy - 104))

        # 6. Pantalla Táctica en la Muñeca (Esquina inferior izquierda)
        if not state.failsafe_mode:
            render_wrist_display(screen, state, fonts, ui_buttons)

        # Banner de Telemetría + Efemérides + A* Ahorro Metabólico
        cw_col = (255, 65, 65) if state.cw_class == 1 else ((255, 195, 45) if state.cw_class == 2 else (16, 240, 155))
        cw_surf = fonts["sm"].render(state.cw_message, True, cw_col)
        screen.blit(cw_surf, (WIDTH // 2 - cw_surf.get_width() // 2, 58))

        # Ayuda rápida de controles en esquina inferior derecha
        help_txt = "WASD: Caminar | TAB: Muñeca | E: LIDAR | F: Escenario | M: Fail-Safe  | C: Centrar Ruta"
        screen.blit(fonts["sm"].render(help_txt, True, (130, 195, 220)), (WIDTH - 690, HEIGHT - 24))

        # Post-proceso monocromático en modo fail-safe
        if state.failsafe_mode:
            gray = pygame.transform.grayscale(screen)
            screen.blit(gray, (0, 0))
            fs_surf = fonts["lg"].render("MODO FAIL-SAFE — CONSUMO MINIMO", True, (255, 255, 255))
            screen.blit(fs_surf, (WIDTH // 2 - fs_surf.get_width() // 2, HEIGHT // 2 - fs_surf.get_height() // 2))

        pygame.display.flip()

    if cap:
        cap.release()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()