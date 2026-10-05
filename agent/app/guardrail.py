"""Deterministic parsing and policy checks for transaction disputes."""

import os
import re
import unicodedata

# Deterministic guardrail tables. These are policy, not prompts: no LLM can
# talk its way past them. See .kilo plan and docs/WORKFLOW.md.

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
    # Added after the held-out evaluation: customers describe fraud without the words above.
    "sin permiso",
    "sin mi permiso",
    "sin autorizacion",
    "sin mi autorizacion",
    "sin consentimiento",
    "sin mi consentimiento",
    "sem permissao",
    "sem minha permissao",
    "sem autorizacao",
    "sem minha autorizacao",
    "sem meu consentimento",
    "hackea",
    "hackeo",
    "invadiram",
    "invasao",
    "acceso no autorizado",
    "entro a mi cuenta",
    "entraron a mi cuenta",
    "accedio a mi cuenta",
    "accedieron a mi cuenta",
    "acessou minha conta",
    "acessando minha conta",
    "sabe mi contrasena",
    "tiene mi contrasena",
    "sabe minha senha",
    "usando mi tarjeta",
    "uso mi tarjeta",
    "usou meu cartao",
    "usando meu cartao",
    "perdi mi tarjeta",
    "perdi mi cartera",
    "perdi mi billetera",
    "perdi meu cartao",
    "perdi minha carteira",
    "extravi",
    "me quitaron",
    "levaram minha carteira",
    "asalt",
    "nao fui eu quem",
    "no hice yo",
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
    "intent_low_confidence": "intent classifier confidence below INTENT_MIN_CONFIDENCE — the agent abstains and escalates",
}

# What the specialist reads in the handoff's verified facts. The English text above stays the stored `limitation`,
# which the contract and the evaluation read.
GUARDRAIL_LIMITATIONS_ES = {
    "fraud_suspected": "el cliente menciona fraude, robo o uso sin permiso: siempre lo revisa una persona",
    "amount_threshold": "el monto efectivo alcanza o supera el umbral de escalamiento (GUARDRAIL_MAX_USD)",
    "ambiguity_unresolved": "no hubo una única transacción candidata tras las rondas de aclaración",
    "out_of_scope": "la consulta está fuera del flujo de disputas de transacciones",
    "verify_failed": "no se pudo volver a verificar el caso después de actuar",
    "amount_unknown": "el monto efectivo en USD no se conoce, así que no se puede comparar con el umbral",
    "posted_charge_disputed": "el cobro está aprobado o pendiente: el dinero pudo moverse, así que decide una persona",
    "intent_low_confidence": "la confianza del clasificador de intención fue baja: el agente se abstiene y escala",
}


def normalize(text: str) -> str:
    """Normalize case and accents for keyword matching."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def max_usd() -> float:
    """Return the configured escalation threshold in effective USD."""
    try:
        return float(os.environ.get("GUARDRAIL_MAX_USD", DEFAULT_MAX_USD))
    except ValueError:
        return DEFAULT_MAX_USD


def mentions_fraud(message: str) -> bool:
    """Detect fraud or theft keywords in the customer message."""
    msg = normalize(message)
    return any(keyword in msg for keyword in FRAUD_KEYWORDS)


def effective_usd(transaction: dict) -> float:
    """Return the effective USD amount, or zero when it is unavailable."""
    value = transaction.get("amount_usd_effective")
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def amount_known(transaction: dict) -> bool:
    """Return whether the effective USD amount is a parseable number.

    An unknown amount is never treated as zero; the case must escalate because
    the threshold cannot be checked.
    """
    value = transaction.get("amount_usd_effective")
    if value is None:
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def exceeds_threshold(transaction: dict) -> bool:
    """Check whether the effective USD amount reaches the escalation limit."""
    return effective_usd(transaction) >= max_usd()


# Two shapes: a number with at least one thousands group ("4.189,18", "1,234.56"), or a plain
# number ("4189.18", "1200", "45.50"). The old pattern let \d{1,3} win on "4189.18" and read it
# as 418, which could then match an unrelated transaction of about 418.
AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?")
# Dates and "N days ago" are not amounts.
_MONTH = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|janeiro|fevereiro|mar[cç]o|maio|junho|julho|setembro|outubro|dezembro)"
# A written date ("10 de junho de 2026", "1 de mayo", "junio de 2026") is not an amount either: before this, the
# year was read as 2026 and beat the real 27.65 in the same message.
NOT_AMOUNT_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?"
    rf"|\d{{1,2}}\s*[º°]?\s+de\s+{_MONTH}(?:\s+de(?:l)?\s+\d{{4}})?|{_MONTH}\s+de(?:l)?\s+\d{{4}}"
)
DAYS_RE = re.compile(r"hace\s+(\d+)\s+d[ií]as?|ha\s+(\d+)\s+dias?|last\s+(\d+)\s+days?")


def parse_number(raw: str) -> float:
    """Parse a decimal amount in common US or Latin American notation."""
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
    """Extract the largest mentioned amount and approximate date window."""
    entities: dict = {}
    stripped = DAYS_RE.sub(" ", NOT_AMOUNT_RE.sub(" ", message.lower()))
    numbers = [parse_number(m.group(0)) for m in AMOUNT_RE.finditer(stripped)]
    if numbers:
        entities["amount"] = max(numbers)
    days = DAYS_RE.search(message)
    if days:
        entities["days"] = int(next(g for g in days.groups() if g))
    elif "ayer" in message.lower() or "ontem" in message.lower():
        entities["days"] = 2
    return entities


def matches_amount(transaction: dict, amount: float, exact: bool = False) -> bool:
    """Compare a transaction amount with a claim amount.

    Use one-percent tolerance by default; ``exact=True`` requires a match to
    the cent.
    """

    def close(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        tolerance = 0.005 if exact else max(0.01 * value, 0.01)
        return abs(value - amount) <= tolerance

    return close(transaction.get("amount_usd_effective")) or close(transaction.get("amount"))


def narrow_candidates(candidates: list, message: str, entities: dict) -> list:
    """Return candidates supported by explicit merchant or amount mentions.

    Preserve input order. Return an empty list for unmatched named specifics
    and the full pool when the message provides no specifics.
    """
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

    # An amount given to the cent beats a merely approximate one: 6783.64 must not be ambiguous
    # with a 6736.04 that happens to fall inside the 1% window.
    if amount_hits:
        exact_hits = [tx for tx in amount_hits if matches_amount(tx, amount, exact=True)]
        if exact_hits:
            amount_hits = exact_hits

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
    """Detect a named multiword merchant that matches no candidate.

    Such a mention is a strong signal that the agent must not guess.
    """
    known = {normalize(tx.get("merchant_name") or "") for tx in candidates}
    for match in CAPITALIZED_RE.finditer(message):
        if normalize(match.group(1)) not in known:
            return True
    return False


def guardrail_intent(message: str, intent: str) -> str:
    """Override the classifier when the message mentions suspected fraud."""
    if mentions_fraud(message):
        return "fraud_report"
    return intent


NEGATIONS = {"no", "nao", "nunca", "ni", "tampoco", "nope", "jamas", "nem"}

AFFIRMATIONS = {
    "si", "sip", "esa", "ese", "esa es", "ese es", "correcto", "exacto", "asi es", "claro",
    "sim", "isso", "essa", "essa mesma", "e essa", "certo", "isso mesmo",
}


def is_corroborated(transaction: dict, message: str, entities: dict) -> bool:
    """Check whether the customer's words identify this transaction.

    A named merchant or matching amount corroborates a candidate; a time
    window or vague report alone never identifies it.
    """
    msg = normalize(message)
    merchant = transaction.get("merchant_name")
    if merchant and normalize(merchant) in msg:
        return True
    amount = entities.get("amount")
    return bool(amount) and matches_amount(transaction, amount)


def is_affirmation(message: str) -> bool:
    """Detect a short affirmative response confirming the proposed candidate."""
    words = normalize(message).replace(",", " ").replace(".", " ").replace("!", " ").split()
    if not words or len(words) > 5:
        return False
    # Any negation wins: "no fue esa" must never confirm a transaction.
    if any(w in NEGATIONS for w in words):
        return False
    text = " ".join(words)
    return text in AFFIRMATIONS or any(w in AFFIRMATIONS for w in words)
