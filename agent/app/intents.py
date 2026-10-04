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


def baseline_classify(message: str) -> str:
    """Deterministic keyword baseline. Reference implementation — the LLM
    classifier gets evaluated against it in the (later) eval branch."""
    msg = normalize(message)
    for intent in _INTENT_PRIORITY:
        if intent == "case_status" and "disputa" in msg:
            continue
        if any(keyword in msg for keyword in KEYWORDS[intent]):
            return intent
    return "out_of_scope"


async def classify(message: str, llm=None) -> str:
    label = None
    if llm is not None and llm.enabled:
        label = await llm.classify_intent(message)
    return label if label in INTENTS else baseline_classify(message)
