import os

import httpx

DEFAULT_MODELS = ["openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"]

SYSTEM_RULES = (
    "Eres el asistente virtual de atención al cliente de un banco. Reglas estrictas:\n"
    "1. Responde en el idioma del usuario (español o portugués), nunca en otro.\n"
    "2. Usa ÚNICAMENTE los hechos verificados que se te entregan. No inventes montos, "
    "fechas, comercios ni estados.\n"
    "3. Nunca prometas reembolsos, ni muevas dinero, ni ofrezcas productos nuevos.\n"
    "4. Nunca pidas ni repitas datos de identidad (documento, customer_id, contraseñas).\n"
    "5. Sé breve y claro; si el caso fue escalado, incluye el número de caso."
)

CLASSIFY_PROMPT = (
    "Clasifica el mensaje del cliente en UNA etiqueta y responde solo con la etiqueta:\n"
    "- dispute: reporta un cobro/cargo que no reconoce, un cobro duplicado o una compra rechazada.\n"
    "- case_status: pregunta por el estado de un caso/disputa previo.\n"
    "- greeting: saludo o cortesía sin solicitud concreta.\n"
    "- out_of_scope: cualquier otra cosa (saldos, préstamos, límites, inversiones, etc.).\n\n"
    "Ejemplos:\n"
    "\"Me hicieron un cobro que no reconozco\" -> dispute\n"
    "\"Me cobraron dos veces la misma compra\" -> dispute\n"
    "\"¿Qué pasó con mi caso?\" -> case_status\n"
    "\"Hola, buenas tardes\" -> greeting\n"
    "\"¿Cuánto saldo tengo?\" -> out_of_scope\n"
    "\"Quiero un préstamo personal\" -> out_of_scope\n"
    "\"Não reconheço esse lançamento\" -> dispute\n"
    "Mensaje: \"{message}\" ->"
)


class LLM:
    """OpenRouter chat client. Disabled (returns None) without an API key —
    every caller must handle the None with a deterministic fallback."""

    def __init__(self, api_key: str | None = None, models: list | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.models = models or (
            [os.environ["OPENROUTER_MODEL"]] + [m for m in DEFAULT_MODELS if m != os.environ.get("OPENROUTER_MODEL")]
            if os.environ.get("OPENROUTER_MODEL")
            else DEFAULT_MODELS
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def chat(self, user_prompt: str, system: str = SYSTEM_RULES) -> str | None:
        if not self.enabled:
            return None
        for model in self.models:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": 0.2,
                            "max_tokens": 400,
                        },
                    )
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"]
            except Exception:
                continue
        return None

    async def classify_intent(self, message: str) -> str | None:
        from app.intents import INTENTS

        raw = await self.chat(CLASSIFY_PROMPT.format(message=message).strip(), system="Eres un clasificador de intenciones. Responde con una sola etiqueta.")
        if raw is None:
            return None
        label = raw.strip().strip('"\'`.').lower()
        return label if label in INTENTS else None
