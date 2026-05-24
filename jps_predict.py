#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║          JPS TIEMPOS LAB — PREDICT (pre-sorteo)                  ║
║  Genera tickets para un sorteo futuro y los registra en          ║
║  predictions_log.jsonl (append-only) para reconciliación posterior. ║
╚══════════════════════════════════════════════════════════════════╝

USO:
  python3 jps_predict.py --session manana
  python3 jps_predict.py --session mediaTarde --budget 10000 --n 5
  python3 jps_predict.py --session tarde --strategy set_a

Workflow esperado:
  1. python3 jps_edge_tool.py fetch --mode history --days 60   (idealmente reciente)
  2. python3 jps_predict.py --session <next>                   (1h antes del sorteo)
  3. (ocurre el sorteo)
  4. python3 jps_edge_tool.py fetch --mode last                (trae el resultado)
  5. python3 jps_reconcile.py                                  (cruza pending con real)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jps_edge_tool import (
    _extract_draws,
    _build_tickets,
    _profile_to_ratio,
    cmd_analyze,
    load_json,
    path as repo_path,
)
from jps_backtest import (
    select_architect,
    select_set_a,
    select_set_b,
    select_set_c,
    select_set_d,
    select_freq_only,
    select_top_mega,
)

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = "predictions_log.jsonl"
VALID_SESSIONS = ("manana", "mediaTarde", "tarde")
SESSION_HOUR = {"manana": 10, "mediaTarde": 14, "tarde": 18}

STRATEGY_SELECTORS = {
    "architect_balanced":     select_architect,
    "architect_conservative": select_architect,
    "architect_aggressive":   select_architect,
    "set_a":                  select_set_a,
    "set_b_freq_elite":       select_set_b,
    "set_c_reverso_edge":     select_set_c,
    "set_d_genie":            select_set_d,
    "freq_only":              select_freq_only,
    "top_mega_only":          select_top_mega,
}

STRATEGY_PROFILE_OVERRIDE = {
    "architect_conservative": "conservative",
    "architect_aggressive":   "aggressive",
}


def _next_draw_date(session: str, now: Optional[datetime] = None) -> str:
    """Devuelve YYYY-MM-DD del próximo sorteo de esa sesión.

    Si la hora ya pasó hoy, devuelve mañana; si no, devuelve hoy.
    """
    now = now or datetime.now()
    hour_cutoff = SESSION_HOUR.get(session, 12)
    target = now.replace(hour=hour_cutoff, minute=0, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return target.strftime("%Y-%m-%d")


def _load_existing_ids() -> set:
    """Lee predictions_log.jsonl y devuelve set de ids ya registrados."""
    p = repo_path(LOG_FILE)
    if not os.path.exists(p):
        return set()
    ids = set()
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "pending":
                    ids.add(rec.get("id"))
            except json.JSONDecodeError:
                pass
    return ids


def _append_jsonl(record: dict):
    p = repo_path(LOG_FILE)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="JPS Tiempos Lab — genera predicción pre-sorteo y la registra en predictions_log.jsonl",
    )
    parser.add_argument("--session", required=True, choices=VALID_SESSIONS,
                        help="Sesión del sorteo: manana | mediaTarde | tarde")
    parser.add_argument("--budget", type=int, default=5000, help="Budget total (₡)")
    parser.add_argument("--n", type=int, default=5, help="Número de tickets")
    parser.add_argument("--strategy", default="architect_balanced",
                        choices=list(STRATEGY_SELECTORS.keys()),
                        help="Estrategia de selección de números")
    parser.add_argument("--profile", default=None,
                        choices=["conservative", "balanced", "aggressive"],
                        help="Override del perfil de riesgo (default: derivado de la estrategia)")
    parser.add_argument("--force", action="store_true",
                        help="Permite registrar otra predicción para la misma sesión-fecha si ya existe una pending")
    args = parser.parse_args()

    # Determinar profile efectivo
    profile = args.profile or STRATEGY_PROFILE_OVERRIDE.get(args.strategy, "balanced")
    rev_ratio = _profile_to_ratio(profile)

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   JPS TIEMPOS LAB — PREDICT (pre-sorteo)             ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  Sesión        : {args.session}")
    print(f"  Estrategia    : {args.strategy}  (profile={profile}, rev_ratio={rev_ratio:.0%})")
    print(f"  Budget        : ₡{args.budget:,}  ·  Tickets: {args.n}")

    # Cargar histórico y verificar frescura
    try:
        data = load_json("historical_data.json")
    except FileNotFoundError:
        print("\n  ERROR: historical_data.json no existe.")
        print("  Corre primero: python3 jps_edge_tool.py fetch --mode history --days 60")
        sys.exit(1)

    draws = _extract_draws(data)
    if not draws:
        print("\n  ERROR: historical_data.json no tiene sorteos válidos.")
        sys.exit(1)
    print(f"  Histórico     : {len(draws)} sorteos en historical_data.json")

    # Generar fecha del próximo sorteo
    draw_date = _next_draw_date(args.session)
    pred_id = f"{draw_date}-{args.session}"

    # Verificar duplicados
    existing = _load_existing_ids()
    if pred_id in existing and not args.force:
        print(f"\n  ERROR: ya existe una predicción pending para {pred_id}.")
        print(f"  Usa --force si querés registrar otra, o corre jps_reconcile.py.")
        sys.exit(1)

    # Análisis (lo silenciamos para no spammar)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        class _A: pass
        report = cmd_analyze(_A(), _draws=draws, _no_save=True)
    if not report:
        print("\n  ERROR: análisis no produjo reporte.")
        sys.exit(1)

    # Seleccionar números
    selector = STRATEGY_SELECTORS[args.strategy]
    try:
        numbers = selector(report, args.n)
    except Exception as e:
        print(f"\n  ERROR: estrategia {args.strategy} falló: {e}")
        sys.exit(1)
    if not numbers or len(numbers) < args.n:
        print(f"\n  ERROR: estrategia devolvió {len(numbers) if numbers else 0} números (esperados {args.n}).")
        sys.exit(1)

    # Construir tickets
    try:
        tickets, remanente = _build_tickets(numbers, args.budget, rev_ratio=rev_ratio)
    except ValueError as e:
        print(f"\n  ERROR al construir tickets: {e}")
        sys.exit(1)

    print(f"\n  Sorteo objetivo: {draw_date} sesión {args.session}")
    print(f"  Predicción ID  : {pred_id}")
    print(f"\n  ┌─ TICKETS ──────────────────────────────────────────────┐")
    print(f"  │ {'#':<4} {'Núm':<6} {'Base':>8} {'Rev':>8} {'Total':>8}    │")
    print(f"  │ {'─'*4} {'─'*6} {'─'*8} {'─'*8} {'─'*8}    │")
    for i, t in enumerate(tickets, 1):
        print(f"  │ {i:<4} {str(t.num_exacto).zfill(2):<6} ₡{t.base:>7,} ₡{t.rev:>7,} ₡{t.base+t.rev:>7,}    │")
    print(f"  └────────────────────────────────────────────────────────┘")
    print(f"  Remanente: ₡{remanente:,}")

    # Top-10 weights snapshot (para auditoría: si en el futuro queremos revisar
    # qué pesos había en ese momento, no tenemos que recomputar)
    combined = report.get("combined_weights") or report.get("weights", {})
    top10_weights = dict(sorted(combined.items(), key=lambda x: x[1], reverse=True)[:10])

    record = {
        "id": pred_id,
        "predicted_at": datetime.now(timezone.utc).isoformat(),
        "draw_date": draw_date,
        "session": args.session,
        "strategy": args.strategy,
        "profile": profile,
        "budget": args.budget,
        "n_tickets": args.n,
        "tickets": [
            {"num": str(t.num_exacto).zfill(2), "base": t.base, "rev": t.rev}
            for t in tickets
        ],
        "weights_top10": top10_weights,
        "n_draws_used_for_analysis": len(draws),
        "status": "pending",
        "result": None,
    }
    _append_jsonl(record)
    print(f"\n  ✓ Registrado en {LOG_FILE}")
    print(f"  → Después del sorteo, corre: python3 jps_reconcile.py")
    print()


if __name__ == "__main__":
    main()
