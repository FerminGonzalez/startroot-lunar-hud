#!/usr/bin/env python3
"""
procesar_dem.py
Convierte el GeoTIFF DEM real de la NASA (LRO LOLA Site04 - Shackleton rim)
en un binario ligero de 512x512 int16 + metadatos JSON para el visor web.
"""

import json
import os
import struct
import sys

import numpy as np
import tifffile

DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DIR_PROYECTO = os.path.dirname(DIR_SCRIPT)

TIF_PATH = os.path.join(DIR_SCRIPT, "Site04_final_adj_5mpp_surf.tif")
BIN_PATH = os.path.join(DIR_SCRIPT, "terreno_real_shackleton.bin")
META_PATH = os.path.join(DIR_SCRIPT, "terreno_meta.json")

TARGET_W = 512
TARGET_H = 512
REAL_SIZE_M = 20000.0  # el producto representa 20 km x 20 km


def _bin_edges(n_in: int, n_out: int) -> np.ndarray:
    """Divide n_in pixels en n_out bloques lo mas uniforme posible."""
    edges = np.round(np.linspace(0, n_in, n_out + 1)).astype(np.int64)
    edges[-1] = n_in
    return edges


def downsample_blockmean(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Reduce a target_h x target_w usando media por bloque, ignorando NaN."""
    h, w = arr.shape
    row_edges = _bin_edges(h, target_h)
    col_edges = _bin_edges(w, target_w)
    out = np.full((target_h, target_w), np.nan, dtype=np.float64)
    for i in range(target_h):
        r0, r1 = int(row_edges[i]), int(row_edges[i + 1])
        if r0 >= r1:
            continue
        for j in range(target_w):
            c0, c1 = int(col_edges[j]), int(col_edges[j + 1])
            if c0 >= c1:
                continue
            block = arr[r0:r1, c0:c1]
            if np.any(np.isfinite(block)):
                out[i, j] = np.nanmean(block)
    return out


def fill_empty_with_neighbor_min_or_zero(grid: np.ndarray) -> np.ndarray:
    """Rellena celdas NaN con el minimo de los 8 vecinos; si no hay, con 0."""
    h, w = grid.shape
    filled = grid.copy()
    # iteraciones simples para propagar (suelen ser muy pocas celdas vacias)
    for _ in range(10):
        mask = np.isnan(filled)
        if not np.any(mask):
            break
        new = filled.copy()
        for i in range(h):
            for j in range(w):
                if not mask[i, j]:
                    continue
                i0, i1 = max(0, i - 1), min(h, i + 2)
                j0, j1 = max(0, j - 1), min(w, j + 2)
                window = filled[i0:i1, j0:j1]
                vals = window[np.isfinite(window)]
                if vals.size:
                    new[i, j] = float(vals.min())
                else:
                    new[i, j] = 0.0
        filled = new
    # cualquier resto (aislado) a 0
    filled[np.isnan(filled)] = 0.0
    return filled


def main() -> int:
    if not os.path.isfile(TIF_PATH):
        print(f"ERROR: no se encuentra {TIF_PATH}", file=sys.stderr)
        return 1

    print(f"Leyendo {TIF_PATH} ...")
    with tifffile.TiffFile(TIF_PATH) as tif:
        page = tif.pages[0]
        print(f"  dimensiones originales: {page.shape}  dtype={page.dtype}")

        # --- lectura de tags de georreferencia ---
        try:
            pixel_scale = page.tags[33550].value
        except Exception as exc:
            print(f"ERROR: no se pudo leer ModelPixelScaleTag (33550): {exc}", file=sys.stderr)
            return 1
        try:
            tiepoint = page.tags[33922].value
        except Exception as exc:
            print(f"ERROR: no se pudo leer ModelTiepointTag (33922): {exc}", file=sys.stderr)
            return 1

        print(f"  ModelPixelScaleTag (33550): {pixel_scale}")
        print(f"  ModelTiepointTag   (33922): {tiepoint}")

        # --- lectura de pixeles ---
        dem = tif.asarray()

    if dem.ndim != 2:
        print(f"ERROR: se esperaba imagen 2D, se obtuvo {dem.ndim}D", file=sys.stderr)
        return 1

    h, w = dem.shape
    finite = np.isfinite(dem)
    print(f"  pixeles finitos: {finite.sum()} / {dem.size}")
    print(f"  pixeles NaN/NoData: {dem.size - finite.sum()}")
    print(f"  z original (m): min={np.nanmin(dem):.3f} max={np.nanmax(dem):.3f} mean={np.nanmean(dem):.3f}")

    # --- downsample a 512x512 ---
    print(f"\nDownsampleando a {TARGET_H}x{TARGET_W} (media por bloque) ...")
    down = downsample_blockmean(dem, TARGET_H, TARGET_W)
    down = fill_empty_with_neighbor_min_or_zero(down)

    z_min = float(down.min())
    z_max = float(down.max())
    z_range = z_max - z_min
    print(f"  z downsample (m): min={z_min:.3f} max={z_max:.3f} mean={down.mean():.3f} range={z_range:.3f}")

    if z_range > 32767:
        print(f"ERROR: rango z={z_range:.0f} m excede int16 (32767). Se requiere escalar.", file=sys.stderr)
        return 1

    # --- cuantizacion a int16 little-endian ---
    quantized = np.rint(down - z_min).astype(np.int16)
    print(f"  valores cuantizados: min={quantized.min()} max={quantized.max()}")

    bin_bytes = quantized.tobytes()
    expected_bytes = TARGET_W * TARGET_H * 2
    if len(bin_bytes) != expected_bytes:
        print(f"ERROR: tamano binario inesperado: {len(bin_bytes)} (esperado {expected_bytes})", file=sys.stderr)
        return 1

    with open(BIN_PATH, "wb") as fh:
        fh.write(bin_bytes)
    print(f"  escrito {BIN_PATH} ({len(bin_bytes)} bytes)")

    # --- metadatos ---
    meta = {
        "width": TARGET_W,
        "height": TARGET_H,
        "pixel_scale_m": REAL_SIZE_M / TARGET_W,
        "z_min": z_min,
        "z_max": z_max,
        "site": "Site04 - Shackleton rim (LRO LOLA 5 m/px)",
        "source_url": "https://pgda.gsfc.nasa.gov/products/78",
        "citation": "Barker et al., 2021, Planet. Space Sci. 203, 105119, doi:10.1016/j.pss.2020.105119",
        "honest_note": "Mosaico LOLA del polo sur; ~90% de pixeles interpolados por separacion de track (segun el producto original)",
        "original_shape": [int(h), int(w)],
        "original_pixel_scale_m": float(pixel_scale[0]) if len(pixel_scale) > 0 else None,
        "tiepoint_xy": [float(tiepoint[3]), float(tiepoint[4])] if len(tiepoint) >= 6 else None,
    }
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    print(f"  escrito {META_PATH}")

    # --- sanity check ---
    print("\n--- Sanity check ---")
    with open(BIN_PATH, "rb") as fh:
        raw = fh.read()
    print(f"  tamano .bin: {len(raw)} bytes (esperado {expected_bytes})")
    if len(raw) != expected_bytes:
        print("ERROR: tamano binario incorrecto", file=sys.stderr)
        return 1

    reconstructed = np.frombuffer(raw, dtype=np.int16).reshape(TARGET_H, TARGET_W) + z_min
    print(f"  reconstruido (m): min={reconstructed.min():.3f} max={reconstructed.max():.3f} mean={reconstructed.mean():.3f}")

    # verificar algunas muestras contra el promedio original de su bloque
    row_edges = _bin_edges(h, TARGET_H)
    col_edges = _bin_edges(w, TARGET_W)
    samples = [(0, 0), (TARGET_H // 4, TARGET_W // 4), (TARGET_H // 2, TARGET_W // 2),
               (3 * TARGET_H // 4, 3 * TARGET_W // 4), (TARGET_H - 1, TARGET_W - 1)]
    max_err = 0.0
    print("  muestras (fila,col) | original block mean | reconstruido | diff:")
    for i, j in samples:
        r0, r1 = int(row_edges[i]), int(row_edges[i + 1])
        c0, c1 = int(col_edges[j]), int(col_edges[j + 1])
        orig_mean = float(np.nanmean(dem[r0:r1, c0:c1]))
        rec_val = float(reconstructed[i, j])
        diff = abs(orig_mean - rec_val)
        max_err = max(max_err, diff)
        print(f"    ({i:3d},{j:3d})  {orig_mean:12.3f} m  {rec_val:12.3f} m  diff={diff:.3f} m")
    print(f"  maximo error de muestra: {max_err:.3f} m")
    if max_err > 0.5:
        print("ERROR: diferencia maxima > 0.5 m", file=sys.stderr)
        return 1

    print("\nPerfil de altura a lo largo de la columna central (fila, z_m):")
    mid = TARGET_W // 2
    for i in (0, TARGET_H // 4, TARGET_H // 2, 3 * TARGET_H // 4, TARGET_H - 1):
        print(f"  ({i:3d},{mid:3d}) -> {reconstructed[i, mid]:.2f} m")

    print("\nProcesamiento completado correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
