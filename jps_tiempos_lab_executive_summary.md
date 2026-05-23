# Executive Summary: How JPS Tiempos Lab Works

**JPS Tiempos Lab** is a specialized GPT designed for technical, statistical, and entertainment-oriented analysis of **Nuevos Tiempos Reventados** from JPS Costa Rica. It does **not** claim to predict winning numbers or identify a real betting edge. Its operating assumption is that the game is random: every number from **00 to 99** has the same probability, and the Reventada outcome follows the official three-ball mechanism described in the regulation.

At a high level, the GPT performs four main functions:

1. **Explains the game mechanics**  
   It can summarize how Nuevos Tiempos works, including Exacto, Reversible, Primero, Terminación, Reventados, and Mega Reventados. It uses the official payout structure: Exacto pays **70x**, Reventados pays **200x** on the Reventados stake, and Mega Reventados has several conditional payout scenarios.

2. **Runs statistical analysis**  
   For historical analysis, it evaluates observed frequencies of numbers and Reventada outcomes against the expected random model. It checks whether deviations are statistically meaningful or just normal random variation.

3. **Builds technical betting configurations**  
   It can generate ticket structures under constraints such as budget, number of bets, Reventados exposure, minimum ₡100 increments, and the rule that the Reventados amount must be less than or equal to the Exacto amount. It treats these as **risk-engineering exercises**, not as guaranteed strategies.

4. **Audits results**  
   Given a ticket table and the official result, it calculates whether each ticket won, the amount recovered, net profit or loss, ROI, and session status.

---

## Core Probability Model

The GPT uses a simple and transparent probabilistic model:

| Component | Probability assumption |
|---|---:|
| Exacto number | 1 / 100 = 1.00% |
| Reventada | 1 / 3 = 33.33% |
| Exacto + Reventada | 1 / 100 × 1 / 3 = 0.3333% |

The Reventados rule is especially important: the Reventados prize only matters if the player also hits the Exacto number and the Reventada ball is drawn. The regulation states that Reventados is played in combination with Exacto and that the player must have played and hit Exacto to qualify for the Reventados prize.

---

## Technical Architecture of Responses

The GPT behaves differently depending on the user’s request.

### 1. Latest Result Requests

For prompts such as:

> “último resultado”  
> “resultado de hoy”  
> “qué salió hoy”

It calls the live endpoint:

```text
getNuevosTiemposLast
```

That endpoint returns the latest available Nuevos Tiempos results, including the available draw periods such as mañana, media tarde, and tarde.

---

### 2. Historical Analysis Requests

For prompts involving:

> “análisis”  
> “tendencias”  
> “estadísticas”  
> “histórico”  
> “frecuencias”

It calls:

```text
getNuevosTiemposHistorical
```

Then it performs a statistical report including:

| Area | Analysis performed |
|---|---|
| Reventada | Observed frequency vs expected 33.33% |
| Reventada deviation | Percentage deviation from theoretical probability |
| Confidence interval | 99% binomial interval |
| Dispersion | Variance and standard deviation |
| Hypothesis testing | Chi-square or proportion test |
| Rachas | Streak analysis under independence |
| Monte Carlo | 20,000 simulations with p = 1/3 |
| Numbers 00–99 | Observed vs expected frequency |
| Decenas/unidades | Digit-level simulation and comparison |
| Percentiles | 2.5%–97.5% simulation bands |

Its interpretation is conservative: deviations inside expected simulation bands are treated as normal randomness, not as predictive patterns.

---

### 3. Prediction-Style Requests

When the user asks for a “prediction,” the GPT does not claim actual foresight. It generates simulated combinations using a uniform random model.

It will usually say, in effect:

> These are simulated combinations for entertainment. They do not improve the mathematical probability of winning.

This is central to the GPT’s design: it can produce combinations, but it must not imply that any number is “due,” “hot,” or more likely in a truly random system.

---

### 4. Bet Engine

The Bet Engine constructs ticket tables under official-style constraints.

It uses these rules:

| Rule | Constraint |
|---|---|
| Exacto payout | 70x base |
| Reventados payout | 200x Reventados stake |
| Minimum modality amount | ₡100 |
| Increment | Multiples of ₡100 |
| Reventados stake | Must be ≤ Exacto base |
| Ticket exposure | Ticket ≤ 25% of total budget |
| Reventados prize | Pays only if Exacto hits and Reventada = SI |

A typical output includes:

| # | num_exacto | ticket_total | base | rev | tipo | EV_est |
|---:|---|---:|---:|---:|---|---:|

Then it summarizes total budget, total staked, remnant, Reventados exposure, and risk level.

---

### 5. Audit Engine

The Audit Engine checks actual outcomes against submitted tickets.

Required inputs:

| Field | Meaning |
|---|---|
| Ticket table | Number, base, rev, total |
| resultado_exacto | Winning number 00–99 |
| resultado_reventada | SI or NO |

It computes:

```text
hit_exacto = num_exacto == resultado_exacto

exacto_win = base × 70 if hit_exacto else 0

rev_win = rev × 200 if hit_exacto and resultado_reventada == SI else 0

recuperado = exacto_win + rev_win

neto = recuperado - ticket_total

roi_ticket = neto / ticket_total
```

The audit output is intentionally direct and does not re-explain theory unless asked. It reports total staked, total recovered, net result, ROI, and session status: **WIN** or **LOSS**.

---

## Regulatory Grounding

The GPT’s rules are aligned with the uploaded JPS regulation and “Cómo jugar” reference. These documents establish that Nuevos Tiempos involves selecting numbers from **00 to 99**, that Exacto pays **70 times**, Reventados pays **200 times**, and that the Reventados draw uses one winning “Reventada” ball among three balls.

They also establish operational constraints such as minimum wagers of **₡100**, wagers in multiples of **₡100**, and the rule that the Reventados amount must be equal to or less than the Exacto stake.

### Source Materials

- `REGLAMENTO_JUEGO_NUEVOS_TIEMPOS_modificado_JD_157_2025_y_JD_217_del_24_de_abril_2025_dd4b9d4668.pdf`
- `Cómo jugar Nuevos Tiempos Reventados.docx`

---

## Practical Purpose

This GPT is best understood as a **statistical lab and ticket-risk assistant**, not a prediction engine.

It helps users:

- Understand game mechanics.
- Compare observed results against a random model.
- Simulate expected risk and volatility.
- Structure entertainment tickets within constraints.
- Audit actual tickets after a draw.

Its most important principle is:

> **Todos los números tienen exactamente la misma probabilidad en un sistema aleatorio. No se garantiza ningún resultado.**
