"""What a model-written reply must satisfy before the customer sees it.

The model only phrases a case the policy already decided and the backend already recorded; it must not add anything
to it. A bank cannot let a draft promise a time ("it will disappear in 24-48 hours"), a refund, or a number nobody
verified. These checks are deterministic and cheap; a draft that fails one is dropped and the fixed template is sent
instead, so the worst a model can do is be replaced by the text the agent already had.
"""

import re

# Words that make a promise about time or about money moving. The fixed templates contain none of them.
PROMISE = re.compile(
    r"\b(horas|hora|d[ií]as|d[ií]a|semanas?|minutos?|hours?|days?|weeks?|prazo|dias|pr[oó]ximos?|"
    r"reembols\w*|reembols|estorn\w*|devolver[eé]\w*|devolveremos|acreditar[eé]\w*|acreditaremos|ressarc\w*)\b",
    re.IGNORECASE,
)
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# An identifier of a customer, or anything that looks like a document number, must never be repeated.
IDENTITY = re.compile(r"\bCLI-[A-Z0-9]+\b|\b\d{7,}\b")
# Names the system uses inside (case states, resolutions, transaction statuses). A customer must not read them: the
# fixed templates say the same thing in plain words.
INTERNAL_NAME = re.compile(
    r"\b(auto_resolved|in_progress|escalated|no_charge_confirmed|reversal_confirmed|Approved|Declined|Pending|Reversed)\b"
)
# A transaction's own id (TRX-..., TXN-...): the specialist needs it, the customer does not, and it reads as noise.
TRANSACTION_ID = re.compile(r"\b(?:TRX|TXN)-[A-Z0-9-]+\b")
MAX_LENGTH = 900


def numbers(text: str) -> set[str]:
    """The numbers in a text, with a decimal comma read as a point ("256,10" is "256.10"), without ids."""
    found = set()
    for token in NUMBER.findall(UUID.sub(" ", text)):
        normalized = token.replace(",", ".") if re.search(r",\d{1,2}$", token) else token.replace(",", "")
        found.add(normalized.rstrip("0").rstrip(".") if "." in normalized else normalized)
    return found


def plain_text(draft: str) -> str:
    """The draft without Markdown. The chat shows text as it comes, so "**rechazada**" would reach the customer with its
    asterisks. The words stay, the marks go."""
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", draft, flags=re.DOTALL)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"`+([^`]*)`+", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    return text.strip()


def without_transaction_ids(text: str) -> str:
    """A fact for the model with the transaction's id taken out, so it has nothing to copy into the reply."""
    return re.sub(r"[ \t]{2,}", " ", TRANSACTION_ID.sub("", text)).replace(" ,", ",").strip()


def check(draft: str, facts: list[str], message: str, case_id: str | None) -> str | None:
    """None when the draft may be sent, otherwise the name of the rule it broke."""
    if len(draft) > MAX_LENGTH:
        return "too_long"
    if PROMISE.search(draft):
        return "promise"
    if IDENTITY.search(draft):
        return "identity"
    if INTERNAL_NAME.search(draft):
        return "internal_name"
    if TRANSACTION_ID.search(draft):
        return "transaction_id"
    allowed = numbers(" ".join(facts) + " " + message)
    # A year, a day or the decline code appear in the facts; anything else is something nobody verified.
    invented = numbers(draft) - allowed
    if invented:
        return "ungrounded_number"
    return None


def with_case_id(draft: str, case_id: str | None, language: str) -> str:
    """The customer must have the case number whatever the model wrote: add it when the draft left it out."""
    if not case_id or case_id in draft:
        return draft
    # "Caso registrado" reads the same in Spanish and in Portuguese.
    return draft.rstrip() + f"\n\nCaso registrado: {case_id}."
