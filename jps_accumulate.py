#!/usr/bin/env python3
"""
JPS Tiempos Lab — Acumulador diario de datos históricos
Corre diariamente para bajar los últimos 90 días y fusionar con el
archivo acumulado, deduplicando por fecha de día.
Guarda en: historical_accumulated.json
"""
import json, os, urllib.request, urllib.error
from datetime import datetime, timedelta

HERE     = os.path.dirname(os.path.abspath(__file__))
ACCUM    = os.path.join(HERE, "historical_accumulated.json")
JPS_BASE = "https://integration.jps.go.cr"
LOG_FILE = os.path.join(HERE, "accumulate_log.txt")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def jps_get(endpoint):
    url = JPS_BASE + endpoint
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Origin": "https://juegosdeazar.jps.go.cr",
        "Referer": "https://juegosdeazar.jps.go.cr/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def load_accumulated():
    if not os.path.exists(ACCUM):
        return {}
    with open(ACCUM, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Devuelve dict keyed por fecha "YYYY-MM-DD"
    return data

def save_accumulated(records: dict):
    with open(ACCUM, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

def date_key(dia_str: str) -> str:
    """Normaliza fecha a YYYY-MM-DD"""
    try:
        return dia_str[:10]
    except Exception:
        return dia_str

def main():
    log("=== JPS Acumulador arrancando ===")

    # 1. Cargar datos acumulados existentes
    accumulated = load_accumulated()
    before = len(accumulated)
    log(f"  Registros acumulados existentes: {before} días")

    # 2. Fetch últimos 180 días del API
    end   = datetime.now()
    start = end - timedelta(days=180)
    fmt   = "%Y-%m-%dT%H:%M:%S"
    ep    = (f"/api/App/nuevostiempos/historical"
             f"?fechaInicio={start.strftime(fmt)}&fechaFin={end.strftime(fmt)}")
    try:
        raw = jps_get(ep)
    except Exception as e:
        log(f"  ERROR al llamar API: {e}")
        return

    # 3. Parsear respuesta
    if isinstance(raw, list):
        new_records = raw
    elif isinstance(raw, dict):
        new_records = raw.get("data", raw.get("results", raw.get("sorteos", [])))
        if not isinstance(new_records, list):
            new_records = []
    else:
        new_records = []

    log(f"  Registros recibidos del API: {len(new_records)}")

    # 4. Fusionar — deduplicar por fecha
    added = 0
    corrected = 0
    for rec in new_records:
        dia = rec.get("dia", "")
        key = date_key(dia)
        if not key:
            continue
        if key not in accumulated:
            accumulated[key] = rec
            added += 1
        else:
            # Agregar slots vacíos O aplicar correcciones del API
            existing = accumulated[key]
            for slot in ("manana", "mediaTarde", "tarde"):
                new_slot = rec.get(slot)
                if new_slot and isinstance(new_slot, dict) and new_slot.get("numero") is not None:
                    if not existing.get(slot):
                        existing[slot] = new_slot          # slot nuevo (ej: tarde ya cerró)
                    elif existing[slot] != new_slot:
                        existing[slot] = new_slot          # corrección del API
                        corrected += 1

    after = len(accumulated)
    log(f"  Días nuevos agregados: {added} | Correcciones aplicadas: {corrected} | Total acumulado: {after} días")

    # 5. Guardar
    save_accumulated(accumulated)
    log(f"  ✓ Guardado en historical_accumulated.json")

    # 6. También sobreescribir historical_data.json con todos los registros
    #    para que el resto de las herramientas lo usen automáticamente
    all_records = list(accumulated.values())
    with open(os.path.join(HERE, "historical_data.json"), "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2, default=str)
    log(f"  ✓ historical_data.json actualizado ({len(all_records)} días)")
    log("=== Acumulación completa ===\n")

if __name__ == "__main__":
    main()
