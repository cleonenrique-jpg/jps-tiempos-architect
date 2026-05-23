# JPS Tiempos Architect — Code Audit Brief

## CONTEXT: What this project is

This is a **statistical edge tool** for the Costa Rican lottery game "Nuevos Tiempos Reventados" (JPS). 
The user plays this game regularly and built this toolchain to:

1. Fetch historical draw results from the JPS API
2. Run statistical analysis (chi-square, z-scores, frequency rankings)
3. Build optimized betting tickets under budget constraints
4. Simulate risk via Monte Carlo before betting
5. Audit actual results after each draw

**This is a real, actively used tool. Bugs here have direct financial consequences.**

---

## GAME MECHANICS (critical for understanding the math)

| Concept | Detail |
|---|---|
| Number range | 00–99 (100 numbers) |
| Exacto | Picks one number 00-99; pays **70× the base stake** if it matches |
| Reventada | 1 of 3 balls drawn → probability **1/3**; pays **200× the rev stake** |
| Reventados | Only pays out if BOTH: Exacto hits AND Reventada ball is drawn |
| P(Exacto) | 1/100 = 1% |
| P(Exacto + Rev) | 1/100 × 1/3 = 0.3333% |
| Min bet | ₡100 per modality |
| Increments | Multiples of ₡100 only |
| Constraint | `rev ≤ base` always |
| meganNumero | A separate Mega Reventados number (00-99), drawn independently from the Exacto |
| Combined weight | Exacto 75% + Mega 25% — used in ticket selection and Monte Carlo |
| Daily draws | Mañana (~10:55), Media tarde (~14:00), Tarde (~18:00) |
| Currency | Costa Rican Colones (₡) |

**Correct EV formula per ticket:**
```
EV = (1/100) × [70 × base + (1/3) × 200 × rev] - (base + rev)
```
Example: base=200, rev=200 → EV = 0.01 × [14000 + 13333.33] - 400 = 273.33 - 400 = **-₡126.67**

---

## PROJECT FILE MAP

```
JPS Tiempos Architect/
├── jps_edge_tool.py          ← MAIN TOOL (CLI, ~1078 lines) — PRIMARY AUDIT TARGET
├── jps_accumulate.py         ← Daily data accumulator (fetches from API + merges)
├── simulador.py              ← Original standalone Monte Carlo simulator
├── historical_data.json      ← Active working dataset (list of day-objects)
├── historical_accumulated.json ← Long-term accumulator (keyed dict by YYYY-MM-DD)
├── last_result.json          ← Latest API fetch result
├── analysis_report.json      ← Output of `analyze` command
├── input.json                ← Input config for Monte Carlo
├── output.json               ← Monte Carlo results
├── audit_result.json         ← Post-draw audit results
└── accumulate_log.txt        ← Daily accumulator run log
```

---

## THE MAIN TOOL: `jps_edge_tool.py` — Architecture

**CLI entry point:** `main()` → `argparse` → dispatches to one of these commands:

| Command | Function | Purpose |
|---|---|---|
| `fetch` | `cmd_fetch()` | Calls JPS API (requires internet — runs locally) |
| `analyze` | `cmd_analyze()` | Statistical analysis on `historical_data.json` |
| `session_analyze` | `cmd_session_analyze()` | Analysis isolated to one draw session |
| `bet` | `cmd_bet()` | Builds optimized tickets + runs Monte Carlo |
| `simulate` | `cmd_simulate()` | Re-runs Monte Carlo from existing `input.json` |
| `audit` | `cmd_audit()` | Compares tickets to official result |
| `run` | `cmd_run()` | Pipeline: analyze → bet (no separate simulate step) |

**Key data structures:**
- `Ticket` dataclass: `num_exacto`, `base`, `rev`, `tipo`
- `historical_data.json` format: list of day-objects `{dia, manana:{numero, meganNumero, in_reventado, colorBolita, hora}, mediaTarde:{…}, tarde:{…}}`
- `historical_accumulated.json` format: dict keyed by `"YYYY-MM-DD"` → same day-object structure

---

## AREAS TO AUDIT — SPECIFIC CONCERNS

### 1. `_build_tickets()` — Ticket construction logic (lines 587–635)

**High-priority.** This is the core of the bet engine. Known concerns:

- The `rev_ratio` → `base`/`rev` split logic is convoluted. There are multiple re-assignments of `base` and `rev` inside the loop that may produce inconsistent results.
- The `while rev > base` enforcement loop subtracts from `rev` and adds to `base`, but then `base = ticket_amount - rev` immediately recalculates and may undo the adjustment.
- Check: can `base` or `rev` end up **below ₡100** after the loop?
- Check: can `base + rev ≠ ticket_amount` after construction? This would mean budget leakage or overspend.
- Check: is `rev ≤ base` **always** enforced after the full logic, or only sometimes?
- Check: what happens when `budget` is not evenly divisible by `n_tickets`? The `remanente` is supposed to capture the leftover — verify it's correct.

### 2. `_simulate_once()` and `_run_monte_carlo()` — Monte Carlo simulation (lines 768–855)

**Critical for correctness.** The Monte Carlo is supposed to simulate the probability of winning given the ticket portfolio.

- `_simulate_once()` uses `random.choices(range(100), weights=weights_vec)` when weights are provided. But the weights are **historical frequency-based** (smoothed), not true probabilities. They should be normalized when passed to `random.choices`. Verify that the weights vector passed in is already normalized or whether `random.choices` handles unnormalized weights correctly (it does, but verify this is intentional).
- Check: is the random seed (`SEED_DEFAULT = 42`) reset at the start of every `_run_monte_carlo()` call? If yes, every simulation is deterministic and identical — potentially misleading.
- The `p_ganar` walrus operator block (lines 812–813) has dead code: `if p_ganar := wins / n: pass` followed immediately by `p_ganar = wins / n`. The walrus assignment is unused. This is a bug.
- Check if `_run_monte_carlo()` is called from both `cmd_bet()` and `cmd_simulate()` with the same semantics.

### 3. `cmd_session_analyze()` — Session-specific analysis (lines 525–568)

**Suspected bug:** `cmd_analyze()` is called with `_draws=draws` but the function also writes `analysis_report.json` at the end. When called from `cmd_session_analyze()`, it **overwrites the global analysis_report.json** with the session-filtered data. A subsequent `cmd_bet()` that loads `analysis_report.json` would then use **only the session-filtered weights** instead of the global analysis. This is likely unintentional.

### 4. `_extract_draws()` — Data normalization (lines 168–205)

This is the bridge between raw API data and analysis. It needs to handle two formats:
- Day-object format (the common one): `[{dia, manana:{…}, mediaTarde:{…}, tarde:{…}}]`
- Flat draw format: `[{numero, in_reventado, …}]`

Check:
- Does it correctly detect and handle both formats?
- The detection heuristic `any(k in data[0] for k in SESSION_KEYS)` — what if the first record is malformed or missing session keys?
- When `session_filter` is applied, it filters by `d.get("session")`. But flat-format records never get a `"session"` field assigned. This means `session_analyze` would return 0 draws for flat-format data.

### 5. `jps_accumulate.py` — Accumulator merge logic (lines 94–107)

The merge logic only updates slots (`manana`, `mediaTarde`, `tarde`) if the **new** record has data and the **existing** doesn't. But there's no logic to handle data corrections from the API (e.g., if JPS corrects a result after the fact). Check whether this is intentional or a potential data quality issue.

Also: the accumulator writes `historical_data.json` as a **list** (`list(accumulated.values())`), while `historical_accumulated.json` is a **dict**. If the user runs `fetch --mode history` directly (not via accumulator), `historical_data.json` is written from the raw API response which may be in a different format. Verify `_extract_draws()` handles both list-from-accumulator and direct-API-response formats consistently.

### 6. `cmd_analyze()` — Statistical calculations (lines 252–522)

- **Z-score formula:** `_z_score(freq, valid, P_EXACTO)` uses `P_EXACTO = 1/100 = 0.01` as the expected probability. This is correct for individual numbers. But when reporting Reventada, it uses `P_REV = 1/3`. Verify these are applied consistently and not swapped anywhere.
- **Chi-square approximation:** `_chi_square_uniform()` uses the Wilson-Hilferty approximation to avoid scipy. Verify the approximation is reasonably accurate for df=99 and typical sample sizes (250–1000 draws).
- **Bayesian smoothing of weights:** `smoothed = 0.80 * raw_w + 0.20 * 1.0`. This mixes observed frequency with a prior of 1.0 (uniform). Check whether `raw_w` can be 0 (a number that never appeared), and whether `smoothed = max(0.5, min(2.0, …))` is the right floor/ceiling for use in Monte Carlo selection.
- **Mega weights combined formula:** `0.75 * weights[k] + 0.25 * mega_weights.get(k, 1.0)`. If `mega_weights` has no entry for key `k`, it defaults to `1.0` (uniform). Is this the right fallback?

### 7. `cmd_audit()` — Audit engine (lines 884–968)

- `int(args.exacto.lstrip("0") or "0")` — This correctly handles "00" → 0. Verify edge cases: "0", "00", "01", "99".
- The audit loads from `output.json` first, falling back to `input.json`. But `input.json` doesn't have a `tickets` field in the same format — it has `numeros_exacto` and `ticket_structure`. If `output.json` is missing, `tickets_raw = []` and the audit exits with an error. This is correct behavior but the error message could be more helpful.
- Check: does the audit correctly handle the case where the player has multiple tickets with the same number?

### 8. `cmd_bet()` — Number selection (lines 649–748)

- When `numbers` is provided via `--numbers "04,69,91"`, the parsing `int(x.strip().lstrip("0") or "0")` could silently truncate invalid values. Check robustness.
- When `weights` exist, it selects the **top N by weight** without any diversification constraint. If the top 5 numbers are all adjacent (e.g., 11, 12, 13, 14, 15), is that the desired behavior?
- `input_payload["ticket_structure"]` always saves `tickets[0].base` and `tickets[0].rev` as if all tickets have the same structure. This is true for the current `_build_tickets()` implementation, but may cause issues if ticket structure is ever per-number.

---

## KNOWN RUNTIME ISSUES (observed in production)

1. **`accumulate_log.txt` shows `87 días` after a run that previously had `91 días`** — the counter regressed. This suggests `historical_accumulated.json` and `historical_data.json` are out of sync. The accumulator reads the accumulated count from the dict, but the working dataset may have been overwritten by a direct `fetch` command with fewer days of data.

2. **API `403 Forbidden` in sandbox** — The JPS API (`https://integration.jps.go.cr`) is blocked in the Claude sandbox environment. The accumulator (`jps_accumulate.py`) must be run manually on the user's local machine. This is expected and not a bug in the code.

3. **Null bytes in `historical_data.json`** — `load_json()` has a `raw.rstrip(b"\x00")` workaround. Investigate where these null bytes originate (likely from an incomplete write during a crash) and consider using atomic writes (write to `.tmp` then rename).

---

## WHAT TO PRODUCE

Please perform a full audit of `jps_edge_tool.py` and `jps_accumulate.py` and produce:

1. **Bug Report** — For each confirmed bug: file, line number, what the bug is, what the correct behavior should be, and a proposed fix.

2. **Logic Issues** — For each logic concern above: confirm whether it's a real bug or working as intended, with explanation.

3. **Fix Recommendations** — Priority-ordered list: P1 (financial impact), P2 (correctness), P3 (robustness/UX).

4. **Apply fixes directly** to the files if you're confident in the correction. If the fix is non-trivial or changes observable behavior, note it and propose a test case.

---

## HOW TO TEST

You can run the tool in the sandbox (no internet needed for non-fetch commands):

```bash
# Analyze existing historical_data.json
python "jps_edge_tool.py" analyze

# Build tickets
python "jps_edge_tool.py" bet --budget 5000 --n 5 --profile balanced

# Audit with known result
python "jps_edge_tool.py" audit --exacto 47 --reventada SI

# Session-specific analysis
python "jps_edge_tool.py" session_analyze --session manana
```

`historical_data.json` should already exist in the project folder with ~91+ days of data.

---

## IMPORTANT CONSTRAINT

**DISCLAIMER (mandatory in all output):**
> "Todos los números tienen exactamente la misma probabilidad en un sistema aleatorio. No se garantiza ningún resultado."

This disclaimer must remain in all code output and must not be removed from any modified files.
