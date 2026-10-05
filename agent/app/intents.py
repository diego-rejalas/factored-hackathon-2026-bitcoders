"""Intent classification, language fallback, and confidence-aware abstention."""

import os
import time

from app.guardrail import normalize
from app.replies import detect_language

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

def baseline_language(message: str) -> str:
    """The language detector the replies use: letters and words only Portuguese has, Spanish by default."""
    return detect_language(message)


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

    Candidates are tried in this order: structured LLM output, then the
    deterministic keyword baseline. Abstention is decided
    in code; the fraud override remains ahead of it in the graph.
    """
    start = time.monotonic()
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
