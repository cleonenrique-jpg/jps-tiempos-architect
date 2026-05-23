import random
import math
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict, Optional

print("INICIANDO SIMULADOR...")

# ============================================================
# SIMULADOR NUEVOS TIEMPOS (Modo A / Modo B)
# - Soporta rev_ratio en [0.0, 1.0] (incluye 0 y 1)
# - Lee correctamente weights (promedios ponderados) desde input.json
# - Permite 2 modos de construcción de tickets:
#    1) FIXED: respeta ticket_structure (base_por_ticket + rev_por_ticket_reventado)
#    2) BUDGET-SPLIT: reparte presupuesto entre n_apuestas usando rev_ratio
#
# Si ticket_structure viene en input.json -> usa FIXED por defecto
# Si no viene -> usa BUDGET-SPLIT (compatibilidad)
# ============================================================

@dataclass
class Ticket:
    num_exacto: int
    base: int
    rev: int
    tipo: str = "REVENTADO"


def round_down_to_100(x: int) -> int:
    return (x // 100) * 100


def validate_ticket(t: Ticket):
    if not (0 <= t.num_exacto <= 99):
        raise ValueError("num_exacto fuera de rango (0-99)")

    # Permitimos base/rev 0 si el usuario quiere ratio=0 (solo base) o ratio=1 (solo rev),
    # PERO mantenemos regla de montos mínimos cuando corresponda al tipo de juego.
    # Para mantener tu lógica original de FULL REVENTADO (ambos >=100), deja estas validaciones.
    # Aquí las hacemos más flexibles para que "cualquier rev_ratio" funcione:
    if t.base < 0 or t.rev < 0:
        raise ValueError("Montos no pueden ser negativos")

    if t.base % 100 != 0 or t.rev % 100 != 0:
        raise ValueError("Montos deben ser múltiplos de ₡100")

    if t.rev > t.base and t.base > 0:
        # Si base==0 (ratio=1), esta regla no tiene sentido; si base>0, aplicamos rev<=base.
        raise ValueError("Rev no puede ser mayor que Base (cuando Base>0)")


# ============================================================
# CONSTRUCCIÓN DE TICKETS
# ============================================================

def build_tickets_fixed(
    numeros_exacto: List[int],
    budget_total: int,
    base_por_ticket: int,
    rev_por_ticket: int
) -> Tuple[List[Ticket], int]:
    """
    Respeta ticket_structure: asigna base/rev fijos por número.
    Valida que el total no exceda el budget_total.
    """
    base_por_ticket = round_down_to_100(int(base_por_ticket))
    rev_por_ticket = round_down_to_100(int(rev_por_ticket))

    if base_por_ticket < 0 or rev_por_ticket < 0:
        raise ValueError("base_por_ticket y rev_por_ticket no pueden ser negativos")

    if base_por_ticket == 0 and rev_por_ticket == 0:
        raise ValueError("No se puede apostar 0 en ambos (base y rev)")

    tickets: List[Ticket] = []
    for num in numeros_exacto:
        t = Ticket(num_exacto=int(num), base=base_por_ticket, rev=rev_por_ticket, tipo="REVENTADO")
        validate_ticket(t)
        tickets.append(t)

    total_apostado = sum(t.base + t.rev for t in tickets)
    if total_apostado > budget_total:
        raise ValueError(f"Presupuesto insuficiente: total_apostado={total_apostado} > budget_total={budget_total}")

    remanente = budget_total - total_apostado
    return tickets, remanente


def build_tickets_budget_split(
    numeros_exacto: List[int],
    budget_total: int,
    rev_ratio: float
) -> Tuple[List[Ticket], int]:
    """
    Reparte el budget_total en partes iguales entre n_apuestas y calcula base/rev según rev_ratio.
    rev_ratio permitido en [0.0, 1.0] (incluye extremos).
    Ajusta montos a múltiplos de 100.
    """
    if not (0.0 <= rev_ratio <= 1.0):
        raise ValueError("rev_ratio debe estar entre 0 y 1 (incluye 0 y 1)")

    n_apuestas = len(numeros_exacto)
    if n_apuestas <= 0:
        raise ValueError("numeros_exacto no puede estar vacío")

    raw = budget_total // n_apuestas
    ticket_amount = round_down_to_100(int(raw))

    if ticket_amount < 100:
        raise ValueError("Se requieren al menos ₡100 por ticket (budget_total muy bajo para n_apuestas)")

    tickets: List[Ticket] = []

    for num in numeros_exacto:
        rev = round_down_to_100(int(ticket_amount * rev_ratio))
        base = ticket_amount - rev

        # Ajustes para asegurar múltiplos de 100 y no negativos
        base = round_down_to_100(base)
        rev = ticket_amount - base  # asegura suma = ticket_amount

        # Si ambos quedaron en 0 por rounding extremo, fuerza mínimo a base 100 si se puede
        if base == 0 and rev == 0:
            base = min(100, ticket_amount)
            rev = ticket_amount - base

        # Regla rev<=base solo aplica cuando base>0
        while base > 0 and rev > base:
            rev -= 100
            base += 100
            if rev < 0:
                break

        # Recalcular por consistencia suma
        base = ticket_amount - rev
        base = round_down_to_100(base)
        rev = ticket_amount - base

        t = Ticket(num_exacto=int(num), base=int(base), rev=int(rev), tipo="REVENTADO")
        validate_ticket(t)
        tickets.append(t)

    total_apostado = sum(t.base + t.rev for t in tickets)
    remanente = budget_total - total_apostado
    return tickets, remanente


# ============================================================
# PAYOUT
# ============================================================

def payout_ticket(ticket: Ticket, exacto_draw: int, reventada: bool) -> int:
    total = 0
    hit = (ticket.num_exacto == exacto_draw)

    if hit and ticket.base > 0:
        total += 70 * ticket.base

    if hit and reventada and ticket.rev > 0:
        total += 200 * ticket.rev

    return total


# ============================================================
# SIMULACIÓN (Uniforme o Ponderada)
# ============================================================

def simulate_once(tickets: List[Ticket]) -> int:
    cost = sum(t.base + t.rev for t in tickets)

    # --- EXACTO ---
    weights = getattr(simulate_once, "weights", None)
    if weights:
        exacto_draw = random.choices(
            population=list(range(100)),
            weights=weights,
            k=1
        )[0]
    else:
        exacto_draw = random.randint(0, 99)

    # --- REVENTADA ---
    reventada = (random.randint(1, 3) == 1)

    recovered = sum(payout_ticket(t, exacto_draw, reventada) for t in tickets)
    return recovered - cost


# ============================================================
# MONTE CARLO
# ============================================================

def monte_carlo(tickets: List[Ticket], n: int, seed: int) -> dict:
    random.seed(seed)

    nets: List[int] = []
    wins = 0

    for _ in range(n):
        net = simulate_once(tickets)
        nets.append(net)
        if net > 0:
            wins += 1

    avg_net = sum(nets) / n
    variance = sum((x - avg_net) ** 2 for x in nets) / (n - 1) if n > 1 else 0.0
    std_dev = math.sqrt(variance)

    nets_sorted = sorted(nets)
    p5 = nets_sorted[int(0.05 * n)]
    med = nets_sorted[int(0.50 * n)]
    p95 = nets_sorted[int(0.95 * n)]

    return {
        "Simulaciones": n,
        "Promedio Neto": round(avg_net, 2),
        "Desviacion Std": round(std_dev, 2),
        "Probabilidad Ganar": round(wins / n, 4),
        "P5 Neto": p5,
        "Mediana Neto": med,
        "P95 Neto": p95
    }


# ============================================================
# LECTURA DE WEIGHTS (PROMEDIOS PONDERADOS) - Modo B
# ============================================================

def parse_weights(weights_input: Dict) -> List[float]:
    """
    Acepta weights con llaves "00".."99" o también "0".."99" o enteros 0..99.
    Lo normaliza a un vector de 100 floats, default=1.0.
    """
    weights_vector: List[float] = [1.0] * 100

    for i in range(100):
        k2 = str(i).zfill(2)     # "04"
        k1 = str(i)             # "4"
        w = None

        if isinstance(weights_input, dict):
            if k2 in weights_input:
                w = weights_input.get(k2)
            elif k1 in weights_input:
                w = weights_input.get(k1)
            elif i in weights_input:
                w = weights_input.get(i)

        try:
            w = float(w) if w is not None else 1.0
        except Exception:
            w = 1.0

        if w <= 0:
            w = 1.0

        weights_vector[i] = w

    return weights_vector


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))

    input_path = os.path.join(here, "input.json")
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"No existe input.json en: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    budget_total = int(payload["budget_total"])
    rev_ratio = float(payload.get("rev_ratio", 0.6))
    numeros_exacto = [int(x) for x in payload["numeros_exacto"]]

    n_sim = int(payload.get("n_simulaciones", 20000))
    seed = int(payload.get("seed", 42))

    # ----------- WEIGHTS (Modo B) -----------
    weights_input = payload.get("weights", None)
    if weights_input:
        simulate_once.weights = parse_weights(weights_input)
        print("Modo B: Monte Carlo ponderado activado (weights detectados)")
    else:
        simulate_once.weights = None
        print("Modo A: Monte Carlo uniforme")

    # ----------- BUILD TICKETS -----------
    ts = payload.get("ticket_structure", None)

    # Si ticket_structure viene, respetamos base/rev fijos (lo que el usuario pidió en JSON)
    if isinstance(ts, dict) and ("base_por_ticket" in ts or "rev_por_ticket_reventado" in ts):
        base_fixed = int(ts.get("base_por_ticket", 200))
        rev_fixed = int(ts.get("rev_por_ticket_reventado", 200))

        tickets, remanente = build_tickets_fixed(
            numeros_exacto=numeros_exacto,
            budget_total=budget_total,
            base_por_ticket=base_fixed,
            rev_por_ticket=rev_fixed
        )
        print(f"Tickets: modo FIXED (base={base_fixed}, rev={rev_fixed})")
    else:
        # Compatibilidad: reparto de budget + rev_ratio
        tickets, remanente = build_tickets_budget_split(
            numeros_exacto=numeros_exacto,
            budget_total=budget_total,
            rev_ratio=rev_ratio
        )
        print(f"Tickets: modo BUDGET-SPLIT (rev_ratio={rev_ratio})")

    report = monte_carlo(tickets=tickets, n=n_sim, seed=seed)

    output = {
        "budget_total": budget_total,
        "total_apostado": sum(t.base + t.rev for t in tickets),
        "remanente": remanente,
        "tickets": [asdict(t) for t in tickets],
        "monte_carlo_result": report
    }

    out_path = os.path.join(here, "output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    print("\nSimulación completada.")
    print(f"Archivo generado: {out_path}")