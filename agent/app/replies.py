def _fmt_amount(tx: dict) -> str:
    amount = tx.get("amount_usd_effective")
    currency = "USD" if amount is not None else tx.get("currency")
    try:
        value = f"{float(amount if amount is not None else tx.get('amount')):,.2f}"
    except (TypeError, ValueError):
        value = "?"
    return f"{value} {currency}"


def describe(tx: dict) -> str:
    """The merchant is empty in most transactions: fall back to what kind of movement it was."""
    return tx.get("merchant_name") or tx.get("transaction_type") or tx.get("transaction_category") or "una transacción"


def _fmt_date(tx: dict) -> str:
    date = str(tx.get("transaction_date") or "")[:10]
    return date


STATUS_EXPLANATION = {
    "es": {
        "Declined": "fue rechazada, por lo que el dinero nunca salió de tu cuenta",
        "Reversed": "fue revertida, por lo que el importe ya fue devuelto a tu cuenta",
    },
    "pt": {
        "Declined": "foi recusada, então o dinheiro nunca saiu da sua conta",
        "Reversed": "foi revertida, então o valor já foi devolvido à sua conta",
    },
}


def resolved_reply(language: str, case: dict, tx: dict) -> str:
    status = tx.get("transaction_status", "")
    explanation = STATUS_EXPLANATION.get(language, STATUS_EXPLANATION["es"]).get(
        status, STATUS_EXPLANATION["es"].get(status, status)
    )
    if language == "pt":
        return (
            f"Verifiquei sua transação na {_fmt_date(tx)} em {describe(tx)} "
            f"por {_fmt_amount(tx)}: {explanation}. Registrei o caso {case['case_id']} "
            f"com o detalhe e a evidência da verificação. Não foi movido nenhum dinheiro."
        )
    return (
        f"Verifiqué tu transacción del {_fmt_date(tx)} en {describe(tx)} "
        f"por {_fmt_amount(tx)}: {explanation}. Registré el caso {case['case_id']} "
        f"con el detalle y la evidencia de la verificación. No se movió dinero."
    )


def clarify_reply(language: str, candidates: list) -> str:
    options = "; ".join(
        f"{describe(tx)} {_fmt_amount(tx)} del {_fmt_date(tx)}" for tx in candidates[:3]
    )
    if language == "pt":
        return (
            "Encontrei mais de uma transação que pode ser a que você menciona. "
            f"Qual delas é? ({options}). Se nenhuma for, me diga o comércio, o valor "
            "aproximado ou a data."
        )
    return (
        "Encontré más de una transacción que podría ser la que mencionas. "
        f"¿Cuál es? ({options}). Si no es ninguna, dime el comercio, el monto "
        "aproximado o la fecha."
    )


def confirm_reply(language: str, tx: dict) -> str:
    """One candidate exists but the customer did not identify it: ask, never assume."""
    what = f"{describe(tx)} {_fmt_amount(tx)} del {_fmt_date(tx)}"
    if language == "pt":
        return (
            f"Encontrei uma transação que pode ser a que você menciona: {what}. "
            "É essa? Se não for, me diga o comércio, o valor aproximado ou a data."
        )
    return (
        f"Encontré una transacción que podría ser la que mencionas: {what}. "
        "¿Es esa? Si no es, dime el comercio, el monto aproximado o la fecha."
    )


def clarify_empty_reply(language: str) -> str:
    if language == "pt":
        return (
            "Não encontrei uma transação com esses dados. "
            "Você pode me dizer o comércio, o valor aproximado ou a data aproximada?"
        )
    return (
        "No encontré una transacción con esos datos. "
        "¿Me puedes decir el comercio, el monto aproximado o la fecha aproximada?"
    )


def escalated_reply(language: str, handoff: dict) -> str:
    case_id = handoff.get("case_id")
    case_bit = (
        (f" (caso {case_id})" if language != "pt" else f" (caso {case_id})")
        if case_id
        else ""
    )
    if language == "pt":
        return (
            "Entendi. Este caso precisa de revisão humana e foi encaminhado ao nosso "
            f"time especializado{case_bit}, com todas as informações verificadas e as "
            "perguntas em aberto. Um agente vai continuar a partir daqui."
        )
    return (
        "Entiendo. Este caso necesita revisión humana y fue escalado a nuestro "
        f"equipo especializado{case_bit}, con toda la información verificada y las "
        "preguntas abiertas. Una persona continúa desde acá."
    )


def greeting_reply(language: str) -> str:
    if language == "pt":
        return "Olá! Te ajudo com cobranças que não reconheces ou transações recusadas/revertidas. Me conta o que aconteceu."
    return "Hola. Te ayudo con cobros que no reconozcas o transacciones rechazadas/revertidas. Cuéntame qué pasó."


def status_reply(language: str, case: dict) -> str:
    events = case.get("events") or []
    last = events[-1]["event"] if events else case.get("status", "open")
    if language == "pt":
        return f"Seu caso {case['case_id']} está como \"{case.get('status')}\" (último evento: {last})."
    return f"Tu caso {case['case_id']} está como \"{case.get('status')}\" (último evento: {last})."
