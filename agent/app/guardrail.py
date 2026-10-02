import os
import re
import unicodedata

# Deterministic guardrail tables. These are policy, not prompts: no LLM can
# talk its way past them. See .kilo plan and spec/WORKFLOW_DECISION.md.

FRAUD_KEYWORDS = [
    "fraude",
    "fraudulenta",
    "fraudulento",
    "robo",
    "robaron",
    "me robaron",
    "hurto",
    "no fui yo",
    "no soy yo",
    "clon",
    "clonaron",
    "estaf",
    "phishing",
    "suplant",
    "roubo",
    "roubaram",
    "furto",
    "nao fui eu",
    "nao sou eu",
    "golpe",
]

DEFAULT_MAX_USD = 500.0

GUARDRAIL_LIMITATIONS = {
    "fraud_suspected": "fraud or theft mentioned — always human review",
    "amount_threshold": "effective amount >= GUARDRAIL_MAX_USD",
    "ambiguity_unresolved": "no single candidate after the clarification rounds",
    "out_of_scope": "intent outside the transaction-dispute workflow",
    "verify_failed": "could not re-verify the case after acting",
    "amount_unknown": "effective USD amount is unknown (no conversion), so the threshold cannot be checked",
    "posted_charge_disputed": "the disputed charge is Approved or Pending: money may have moved, so a person decides",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def max_usd() -> float:
    try:
        return float(os.environ.get("GUARDRAIL_MAX_USD", DEFAULT_MAX_USD))
    except ValueError:
        return DEFAULT_MAX_USD


def mentions_fraud(message: str) -> bool:
    msg = normalize(message)
    return any(keyword in msg for keyword in FRAUD_KEYWORDS)


def effective_usd(transaction: dict) -> float:
    value = transaction.get("amount_usd_effective")
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def amount_known(transaction: dict) -> bool:
    """False when the USD amount is missing or not a number. An unknown amount is never
    treated as zero: the threshold cannot be checked, so the case escalates."""
    value = transaction.get("amount_usd_effective")
    if value is None:
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def exceeds_threshold(transaction: dict) -> bool:
    return effective_usd(transaction) >= max_usd()


AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d+)?")
DAYS_RE = re.compile(r"hace\s+(\d+)\s+d[ií]as?|ha\s+(\d+)\s+dias?|last\s+(\d+)\s+days?")


def parse_number(raw: str) -> float:
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        head, _, tail = raw.rpartition(",")
        raw = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else raw.replace(",", "")
    elif "." in raw:
        head, _, tail = raw.rpartition(".")
        raw = raw if len(tail) == 2 else raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def extract_entities(message: str) -> dict:
    entities: dict = {}
    numbers = [parse_number(m.group(0)) for m in AMOUNT_RE.finditer(message)]
    if numbers:
        entities["amount"] = max(numbers)
    days = DAYS_RE.search(message)
    if days:
        entities["days"] = int(next(g for g in days.groups() if g))
    elif "ayer" in message.lower() or "ontem" in message.lower():
        entities["days"] = 2
    return entities


def matches_amount(transaction: dict, amount: float) -> bool:
    def close(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        return abs(value - amount) <= max(0.01 * value, 0.01)

    return close(transaction.get("amount_usd_effective")) or close(transaction.get("amount"))


def narrow_candidates(candidates: list, message: str, entities: dict) -> list:
    """Order-preserving narrowing. Returns:
    - the candidates corroborated by merchant and/or amount mentions,
    - [] when the message names specifics that match nothing (never fall back
      to auto-resolving an unrelated transaction),
    - the full candidate list when the message carries no specifics at all
      (ambiguity resolved by asking, not by guessing)."""
    msg = normalize(message)
    merchant_hits = [
        tx
        for tx in candidates
        if tx.get("merchant_name") and normalize(tx["merchant_name"]) in msg
    ]
    amount = entities.get("amount")
    amount_hits = (
        [tx for tx in candidates if matches_amount(tx, amount)] if amount else None
    )

    if amount_hits is not None:
        pool = merchant_hits or candidates
        combined = [tx for tx in pool if tx in amount_hits]
        if combined:
            return combined
    if merchant_hits:
        return merchant_hits
    if amount_hits:
        return amount_hits
    if entities or mentions_unknown_merchant(message, candidates):
        return []
    return candidates


CAPITALIZED_RE = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÑ']+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÑ']+)+)"
)


def mentions_unknown_merchant(message: str, candidates: list) -> bool:
    """True when the message names a capitalized multi-word place/merchant that
    matches none of the candidates — a strong signal we must not guess."""
    known = {normalize(tx.get("merchant_name") or "") for tx in candidates}
    for match in CAPITALIZED_RE.finditer(message):
        if normalize(match.group(1)) not in known:
            return True
    return False


def guardrail_intent(message: str, intent: str) -> str:
    """Deterministic intent-level override: fraud mention always escalates,
    whatever the classifier said."""
    if mentions_fraud(message):
        return "fraud_report"
    return intent


NEGATIONS = {"no", "nao", "nunca", "ni", "tampoco", "nope", "jamas", "nem"}

AFFIRMATIONS = {
    "si", "sip", "esa", "ese", "esa es", "ese es", "correcto", "exacto", "asi es", "claro",
    "sim", "isso", "essa", "essa mesma", "e essa", "certo", "isso mesmo",
}


def is_corroborated(transaction: dict, message: str, entities: dict) -> bool:
    """True when the customer's own words identify this transaction: its merchant is named or
    the amount they mention matches. A time window alone does not identify a transaction, and a
    vague report must never be closed against whatever single candidate happens to exist."""
    msg = normalize(message)
    merchant = transaction.get("merchant_name")
    if merchant and normalize(merchant) in msg:
        return True
    amount = entities.get("amount")
    return bool(amount) and matches_amount(transaction, amount)


def is_affirmation(message: str) -> bool:
    """A short yes: used to confirm the one candidate the agent just proposed."""
    words = normalize(message).replace(",", " ").replace(".", " ").replace("!", " ").split()
    if not words or len(words) > 5:
        return False
    # Any negation wins: "no fue esa" must never confirm a transaction.
    if any(w in NEGATIONS for w in words):
        return False
    text = " ".join(words)
    return text in AFFIRMATIONS or any(w in AFFIRMATIONS for w in words)
