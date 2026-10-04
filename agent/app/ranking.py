"""Ranking de candidatas de la disputa (componente B, variante weighted).

Interfaz del contrato DISPUTE_WORKFLOW §5: rank_candidates(claim,
transactions) -> lista ordenada. El ranker SOLO ORDENA: la decisión de
cuántas candidatas hay (0, 1, 2+) y qué se puede auto-resolver sigue siendo
la política determinista de guardrail.narrow_candidates; `is_corroborated`
sigue exigiendo las palabras del cliente para cerrar.

Score interpretable (suma ponderada, sin modelo):
- similitud del comercio nombrado (difflib sobre tokens normalizados),
- cercanía relativa del monto (contra `amount` y `amount_usd_effective`),
- cercanía de la fecha mencionada (días, "ayer/ontem", "semana pasada"),
- canal mencionado (cajero/ATM, online/app).

Evaluado contra el baseline en ml/eval/reports/ranker_eval.md: en los pools
con 2+ candidatas acierta la primera opción propuesta en 60% de los casos
contra 4% del orden por fecha, sin tocar la política de narrowing ni el
"no encuentra".
"""

import difflib
from datetime import date

from app.guardrail import AMOUNT_RE, DAYS_RE, NOT_AMOUNT_RE, normalize, parse_number

# Pesos fijos a priori (no ajustados sobre el test; ver ML_FINDINGS §7B).
WEIGHTS = {"merchant": 0.40, "amount": 0.35, "date": 0.15, "channel": 0.10}
CHANNEL_HINTS = {
    "atm": ("cajero", "caixa", "atm", "extracc", "saque"),
    "online": ("online", "internet", "web", "app"),
}
DATA_CUTOFF = date(2026, 6, 18)  # corte del set de evaluación


def claim_amount(claim: str) -> float | None:
    """Extract the largest numeric amount mentioned in a claim."""
    stripped = NOT_AMOUNT_RE.sub(" ", claim.lower())
    numbers = [parse_number(m.group(0)) for m in AMOUNT_RE.finditer(stripped)]
    return max(numbers) if numbers else None


def claim_days(claim: str) -> int | None:
    """Return the approximate number of days mentioned in a claim."""
    match = DAYS_RE.search(claim)
    if match:
        return int(next(g for g in match.groups() if g))
    low = normalize(claim)
    if "ayer" in low or "ontem" in low or "anteontem" in low:
        return 2
    if "semana passada" in low or "la semana pasada" in low:
        return 7
    if "começo do mês" in low or "principios de mes" in low:
        return 15
    return None


def claim_channel(claim: str) -> str | None:
    """Infer an ATM or online channel from explicit claim wording."""
    low = normalize(claim)
    for channel, hints in CHANNEL_HINTS.items():
        if any(h in low for h in hints):
            return channel
    return None


def merchant_similarity(claim: str, merchant: str | None) -> float:
    """Score exact or fuzzy overlap between a claim and merchant name."""
    if not merchant:
        return 0.0
    target = normalize(merchant)
    low = normalize(claim)
    if target in low:
        return 1.0
    best = 0.0
    words = low.replace(",", " ").replace(".", " ").split()
    for token in target.split():
        if len(token) >= 4:
            for word in words:
                best = max(best, difflib.SequenceMatcher(None, token, word).ratio())
    return best


def amount_closeness(claim_amt: float | None, transaction: dict) -> float:
    """Score relative distance between a claim amount and transaction amounts."""
    if claim_amt is None or claim_amt <= 0:
        return 0.5  # neutro: sin monto no hay evidencia
    best = None
    for value in (transaction.get("amount"), transaction.get("amount_usd_effective")):
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        rel = abs(value - claim_amt) / max(claim_amt, 1.0)
        best = rel if best is None else min(best, rel)
    if best is None:
        return 0.2
    return max(0.0, 1.0 - min(1.0, best))


def date_closeness(claim_days_value: int | None, transaction: dict) -> float:
    """Score distance between a claim's relative date and the transaction date."""
    if claim_days_value is None:
        return 0.5
    try:
        tx_day = date.fromisoformat(str(transaction.get("transaction_date") or "")[:10])
    except ValueError:
        return 0.5
    tx_days = (DATA_CUTOFF - tx_day).days
    return max(0.0, 1.0 - min(1.0, abs(tx_days - claim_days_value) / 30.0))


def channel_closeness(claim_ch: str | None, transaction: dict) -> float:
    """Score agreement between a mentioned channel and transaction channel."""
    if claim_ch is None or not transaction.get("channel"):
        return 0.5
    return 1.0 if normalize(str(transaction["channel"])) == claim_ch else 0.2


def score_candidate(claim: str, transaction: dict) -> float:
    """Combine available merchant, amount, date, and channel signals."""
    signals = {
        "merchant": merchant_similarity(claim, transaction.get("merchant_name")),
        "amount": amount_closeness(claim_amount(claim), transaction),
        "date": date_closeness(claim_days(claim), transaction),
        "channel": channel_closeness(claim_channel(claim), transaction),
    }
    active = {k: v for k, v in signals.items() if v != 0.5}
    weights = {k: WEIGHTS[k] for k in active}
    total = sum(weights.values()) or 1.0
    return sum(active[k] * weights[k] for k in active) / total


def rank_candidates(claim: str, transactions: list) -> list:
    """Return the same transactions ordered by descending claim score.

    Ties preserve input order; this function never adds, removes, or decides.
    """
    indexed = list(enumerate(transactions))
    indexed.sort(key=lambda pair: (-score_candidate(claim, pair[1]), pair[0]))
    return [tx for _, tx in indexed]
