"""Intent classification, language fallback, and confidence-aware abstention."""

import os
import time

import httpx

from app.guardrail import normalize

INTENTS = ("dispute", "case_status", "greeting", "out_of_scope")

KEYWORDS = {
    "dispute": [
        "cobro", "cobrado", "cobraron", "cargo", "me cobraron", "no reconozco",
        "no reconocido", "duplicado", "doble cobro", "disputa", "reclamo",
        "reclamar", "devuelvan", "devolucion", "no llego", "rechazaron",
        "rechazada", "rechazado", "declinada", "declinado", "reembolso",
        "compre", "pagué", "pague", "pago", "transferencia", "cajero",
        "cobranca", "cobrado", "lancamento", "nao reconheco", "duplicado",
        "disputa", "reclamacao", "estorno", "comprei", "recusada", "recusado",
        "pagamento", "paguei", "devolvam", "caixa",
    ],
    "case_status": [
        "mi caso", "estado de mi caso", "que paso con mi caso", "protocolo",
        "numero de caso", "seu caso", "status do caso", "andamento", "protocolo",
    ],
    "greeting": ["hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "que tal", "ola", "bom dia", "boa tarde", "boa noite", "oi"],
    "out_of_scope": [
        "saldo", "cuanto tengo", "prestamo", "prestamos", "aumentar limite",
        "subir limite", "limite de tarjeta", "nuevo producto", "inversion",
        "invertir", "hipoteca", "abrir cuenta", "cerrar cuenta", "cambiar datos",
        "emprestimo", "emprestimos", "saldo da conta", "aumentar limite",
        "investimento", "hipoteca",
    ],
}

_INTENT_PRIORITY = ("case_status", "out_of_scope", "dispute", "greeting")

# Marcadores de portugués de la detección por substring en producción.
PT_MARKERS = (
    "não", "você", "obrigado", "obrigada", "bom dia", "boa tarde", "boa noite",
    "não reconheço", "cobrança", "estorno",
)


def baseline_language(message: str) -> str:
    """Detección de idioma de producción: marcadores por substring, es por defecto."""
    return "pt" if any(w in message.lower() for w in PT_MARKERS) else "es"


def baseline_classify(message: str) -> str:
    """Classify a message with the deterministic keyword reference baseline.

    The retained evaluation compares semantic classifiers against this result.
    """
    msg = normalize(message)
    for intent in _INTENT_PRIORITY:
        if intent == "case_status" and "disputa" in msg:
            continue
        if any(keyword in msg for keyword in KEYWORDS[intent]):
            return intent
    return "out_of_scope"


async def typesafe_classify(message: str) -> str | None:
    """Classify a message through the optional TypeSafe API.

    Return ``None`` when credentials are absent or the API request fails, so
    callers can fall through to the LLM or deterministic baseline.
    """
    api_key = os.environ.get("TYPESAFE_API_KEY")
    api_url = os.environ.get("TYPESAFE_API_URL")
    if not api_key or not api_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"task": "intent_classification", "labels": list(INTENTS), "input": message},
            )
            response.raise_for_status()
            data = response.json()
        label = data.get("label") or data.get("output") or data.get("result")
        return label if label in INTENTS else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return None


def min_confidence() -> float:
    """Return the configured intent abstention threshold.

    Values below this threshold cause the agent to escalate instead of acting
    on an uncertain intent.
    """
    try:
        return float(os.environ.get("INTENT_MIN_CONFIDENCE", "0.5"))
    except ValueError:
        return 0.5


async def classify_detailed(message: str, llm=None) -> dict:
    """Classify a message and return confidence, source, and abstention state.

    Candidates are tried in this order: TypeSafe (no confidence), structured
    LLM output, then the deterministic keyword baseline. Abstention is decided
    in code; the fraud override remains ahead of it in the graph.
    """
    start = time.monotonic()
    label = await typesafe_classify(message)
    if label is not None:
        return {
            "intent": label, "language": baseline_language(message),
            "confidence": None, "source": "typesafe", "abstain": False,
            "prompt_version": None,
            "classifier_latency_ms": int((time.monotonic() - start) * 1000),
        }
    if llm is not None and llm.enabled:
        detail = await llm.classify_detailed(message)
        if detail is not None:
            return {
                "intent": detail["intent"],
                "language": detail["language"] or baseline_language(message),
                "confidence": detail["confidence"],
                "source": f"llm:{detail['model']}",
                "abstain": detail["confidence"] < min_confidence(),
                "prompt_version": detail.get("prompt_version"),
                "classifier_latency_ms": int((time.monotonic() - start) * 1000),
            }
    return {
        "intent": baseline_classify(message), "language": baseline_language(message),
        "confidence": None, "source": "baseline", "abstain": False,
        "prompt_version": None,
        "classifier_latency_ms": int((time.monotonic() - start) * 1000),
    }


async def classify(message: str, llm=None) -> str:
    """Return the selected intent label, falling back to the keyword baseline."""
    result = await classify_detailed(message, llm)
    return result["intent"] if result["intent"] in INTENTS else baseline_classify(message)
