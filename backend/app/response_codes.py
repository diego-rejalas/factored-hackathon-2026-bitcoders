"""What a card response code means, for explaining a declined transaction to the customer.

The dataset only carries 00, 05, 14, 51 and 54 (and an empty value in about 5% of rows; DATA_FINDINGS.md). The
organizer's documents do not define them: these are the standard meanings of the ISO 8583 response codes that card
networks use. That is an assumption, and the text says so ("segun el estandar") instead of presenting it as the bank's
own reason. An unknown or empty code gets no explanation: the agent never invents one.
"""

# code -> (short reason in Spanish, short reason in Portuguese)
RESPONSE_CODES: dict[str, tuple[str, str]] = {
    "00": ("aprobada", "aprovada"),
    "05": ("el emisor no autorizó la operación", "o emissor não autorizou a operação"),
    "14": ("el número de tarjeta no es válido", "o número do cartão não é válido"),
    "51": ("fondos insuficientes", "saldo insuficiente"),
    "54": ("la tarjeta está vencida", "o cartão está vencido"),
}


def explain(code: str | None, language: str = "es") -> str | None:
    """The reason for a code, or None when the code is empty or not one we know."""
    if not code:
        return None
    entry = RESPONSE_CODES.get(str(code).strip())
    if entry is None:
        return None
    return entry[1] if language == "pt" else entry[0]


def meanings(code: str | None) -> dict[str, str] | None:
    """The reason in every language the agent answers in ({"es": ..., "pt": ...}), or None."""
    if not code:
        return None
    entry = RESPONSE_CODES.get(str(code).strip())
    return {"es": entry[0], "pt": entry[1]} if entry else None
