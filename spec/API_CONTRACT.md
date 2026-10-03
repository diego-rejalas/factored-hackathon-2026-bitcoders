# Contrato de las APIs

Contrato del workflow A (disputas de transacciones) entre las tres capas: **el backend**, **el agente** y **el servidor de la aplicación web (BFF)**. Fecha: 2026-10-03.

## Cómo se mantiene este contrato

Hay dos fuentes y se complementan:

| Fuente | Qué dice | Quién la hace cumplir |
|---|---|---|
| `backend/tests/contract/openapi.json` y `agent/tests/contract/openapi.json` | Rutas, parámetros, cuerpos y esquemas de respuesta. **Lo genera el código** | Una prueba falla si el código genera algo distinto. Cambiar el contrato es una decisión que se revisa en el diff (`UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py` lo regenera) |
| **Este documento** | Lo que un esquema no puede decir: reglas, estados, orden de las llamadas, seguridad, límites y supuestos | Revisión |

Si este documento y un OpenAPI se contradicen, **gana el OpenAPI**: es el que ejecutan las pruebas. Avísalo y se corrige aquí.

Lo que el contrato hace cumplir con pruebas (no con buena voluntad):
- el conjunto de operaciones que **no** piden sesión es exactamente: `GET /health`, `GET /ready`, `POST /session`, `POST /v1/auth/login`, `GET /v1/auth/demo-accounts`. Se comprobó haciendo público `/v1/me` y viendo fallar la prueba;
- ninguna ruta recibe un `customer_id` del que llama (ni por parámetro, ni por ruta, ni en el cuerpo);
- ningún esquema tiene un campo para `is_fraud`, `fraud_score`, `password_hash`, `credit_score` ni `estimated_monthly_income`;
- el cuerpo de `POST /chat` no puede nombrar a un cliente.

## 1. Quién llama a quién

```
Navegador ──► ALB + Cloud Armor ──► Frontend (Next.js) = BFF  ── /api/* ──┬──► Backend  /v1     (ID token de Cloud Run)
                                                                           └──► Agente   /chat   (token de sesión del cliente)
                                                                                    └──► Backend (raíz, ID token)  ──► Cloud SQL
```

- **El navegador solo habla con el BFF.** No conoce la dirección del backend ni del agente, y nunca ve el token de sesión.
- **El backend es privado:** solo cuentas de servicio con `run.invoker` lo llaman, con su ID token en `X-Serverless-Authorization`. `Authorization` queda libre para el token de sesión del cliente.
- **El agente** lee datos solo a través del backend (nunca toca la base). Usa las rutas de la **raíz** del backend; la web usa `/v1`.

## 2. Convenciones comunes

| Tema | Regla |
|---|---|
| Formato | JSON en UTF-8. Fechas en ISO 8601 (`2026-06-19T15:45:00`; las marcas con zona terminan en `Z`) |
| Dinero | **Número** más `currency` aparte. `amount_usd_effective` es `amount_usd` o, si falta y la moneda es USD, `amount`. Es `null` si no se conoce: **nunca se trata como cero** |
| Identificadores | Opacos. `case_id` es un UUID; los de transacción y producto son texto del dataset |
| Sesión | `Authorization: Bearer <token>`. JWT HS256, emisor `backend-sandbox`, vigencia de 2 horas (`expires_in` en segundos). El `sub` es el `customer_id`. **La identidad sale siempre del token** |
| Trazabilidad | Toda respuesta lleva `X-Request-ID`. Si la solicitud trae uno válido (8 a 100 caracteres de `A-Za-z0-9._-`) se conserva; si no, se crea. El BFF lo genera y lo reenvía; el agente lo reenvía al backend. Cada solicitud escribe una línea de registro JSON con `severity`; **no** se registra `Authorization`, la cadena de consulta ni ningún cuerpo |
| Paginación | Por **cursor**, no por posición: `?limit=` (1 a 100, 20 por defecto) y `?cursor=` con el `next_cursor` de la página anterior. `next_cursor` es `null` en la última. Un cursor que el servicio no emitió da `422` |
| Idempotencia | `POST /disputes` es idempotente **por (cliente, transacción)**: repetirlo devuelve el mismo caso con `200` (la primera vez, `201`). Acepta además `Idempotency-Key` |
| Versiones | `/v1` solo admite cambios que no rompen: campos nuevos opcionales, rutas nuevas. Lo que rompa va en `/v2`. Las rutas de la **raíz** son las del agente y están congeladas en su forma |

### Errores

El cuerpo es `{"detail": "<texto>"}`. Los errores de validación (`422`) traen `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`. El texto no incluye datos de otro cliente.

| Código | Cuándo |
|---|---|
| `401` | Falta el token, está mal formado o venció. También el login con credenciales erróneas (**la misma respuesta si el usuario no existe**) |
| `404` | No existe **o no es del cliente**. Las dos cosas son indistinguibles a propósito |
| `422` | Parámetro o cuerpo inválido, `from` posterior a `to`, cursor inválido |
| `429` | Cinco intentos de login fallidos (por defecto; `LOGIN_MAX_FAILED_ATTEMPTS`): la cuenta se bloquea 15 minutos (`LOGIN_LOCK_MINUTES`). Trae `Retry-After` (segundos) |
| `503` | `GET /ready` cuando no se alcanza la base |

## 3. Backend

El esquema exacto de cada cuerpo está en `backend/tests/contract/openapi.json`. Aquí, lo que hace cada ruta y lo que el esquema no dice.

### 3.1 `/v1` (la usa el BFF)

| Ruta | Sesión | Hace |
|---|---|---|
| `POST /v1/auth/login` `{username, password}` | no | Devuelve `{session_token, token_type, expires_in, customer}`. La clave se compara con argon2id. Cinco fallos bloquean la cuenta; un acceso correcto reinicia la cuenta |
| `GET /v1/auth/demo-accounts` | no | `{accounts: [{username, label, hint, first_name, country}], password}`. **`404` salvo `DEMO_ACCOUNTS_ENABLED=true`.** La clave compartida es pública a propósito: los datos son sintéticos |
| `GET /v1/me` | sí | `{customer_id, first_name, last_name, country}`. Nunca ingresos, puntaje ni documento |
| `GET /v1/me/summary` | sí | `{balances, recent_transactions, disputes}`. Los saldos son por moneda y **separan depósitos de crédito** (nunca se netean); `disputes` cuenta los casos activos por estado |
| `GET /v1/me/products` y `/{product_id}` | sí | Productos con el número **enmascarado** (`****1234`), `kind` (`deposit`, `credit`, `other`), saldo, límite y estado. Los activos primero |
| `GET /v1/me/transactions` | sí | `{items, next_cursor}`, de más nueva a más vieja. Filtros: `product_id`, `status`, `merchant` (mínimo 2 caracteres), `from`, `to` (fechas, `to` inclusivo). **Cada fila trae `case_id` y `dispute_status`** si ya tiene un caso, y `response_meaning` |
| `GET /v1/me/transactions/{id}` | sí | Una transacción, con las mismas columnas |
| `GET /v1/meta/data` | sí | `{gold: [{table, rows}], last_successful_run}`: cuándo corrió por última vez el pipeline con éxito. **`last_successful_run: null` significa "no se sabe"**, no "hoy" |
| `GET /v1/disputes` | sí | Mis casos, de más nuevo a más viejo. `?status=` es `open`, `auto_resolved` o `escalated`. No incluye los `closed` |
| `GET /v1/disputes/{case_id}` | sí | El caso con su línea de tiempo (`events`) |
| `POST /v1/disputes` `{transaction_id, reason_code, summary}` | sí | Abre el caso. **La web no debe llamarlo** (ver §5): la política decide en el agente |
| `POST /v1/disputes/{case_id}/escalate` `{handoff}` | sí | Lo llama el agente. Ver §4 |
| `POST /v1/disputes/{case_id}/resolve` `{resolution}` | sí | Lo llama el agente. Ver §4 |
| `GET /health`, `GET /ready` | no | El proceso vive / alcanza la base |

**`response_meaning`** (`{es, pt}` o `null`) es el significado estándar (ISO 8583) del `response_code`. **Es un supuesto:** el organizador no define los códigos. El dataset solo trae `00`, `05`, `14`, `51` y `54` (y vacío en ~5%). Un código vacío o desconocido da `null`: no se inventa un motivo.

**`kind` y los saldos:** el diccionario del organizador tampoco define `current_balance`. En un depósito es lo que el cliente tiene; **en crédito se infiere que es lo que debe** (hay 7.510 productos de crédito con saldo mayor que su límite, lo que solo tiene sentido si el saldo es lo usado). Por eso la pantalla debe rotularlos distinto.

### 3.2 Raíz (la usa el agente)

Misma lógica y mismas reglas, con la forma de siempre: `POST /session` (`{customer_id, document_number}`), `GET /me`, `GET /me/transactions` (lista simple, no paginada) y `GET /me/transactions/{id}`, más las mismas rutas de disputas que bajo `/v1`. No se usa desde el navegador.

## 4. Estados del caso y quién los cambia

```
            ┌──────────── resolve (el agente) ───────────► auto_resolved ─┐
  open ─────┤                                                              ├─ escalate (el agente) ─► escalated
            └──────────────────── escalate (el agente) ───────────────────┘
  closed: lo cierra una persona (operación futura, fuera de alcance). Un caso cerrado no cuenta: se puede reportar de nuevo.
```

| Operación | Transición | Si ya no aplica |
|---|---|---|
| Abrir | → `open` | Si la transacción ya tiene un caso que no está `closed`, **devuelve ese** (`200`) |
| `resolve` | `open` → `auto_resolved` (guarda `evidence.resolution`) | Devuelve el caso sin cambiarlo. **No deshace una escalada** |
| `escalate` | `open` o `auto_resolved` → `escalated` (guarda `evidence.handoff`) | `escalated` y `closed` son finales: devuelve el caso sin cambiarlo ni reescribir el traspaso |

Repetir una operación **no es un error**. La línea de tiempo (`events`) solo crece: `created`, y luego `resolved` o `escalated`.

Por qué existe `resolve`: hasta entonces nada marcaba `auto_resolved`, y los casos que la política resolvía quedaban `open` para siempre en la lista del cliente.

## 5. Agente

Esquema exacto en `agent/tests/contract/openapi.json`.

### `POST /chat`

Pide: `{session_token, message, conversation_id?, transaction_id?}`. El token va en el cuerpo, no en una cabecera.

- **`transaction_id`** es el movimiento que el cliente eligió en la pantalla. Identifica la transacción mejor que cualquier texto: no se busca ni se pide confirmar. **Todo lo demás sigue aplicando** (umbral de USD 500, cobro ya aprobado, monto desconocido). El backend verifica que sea del cliente; **uno ajeno se ignora** como si no se hubiera elegido (nunca un error y nunca datos ajenos). **No se hereda al siguiente turno** de la conversación.
- **`conversation_id`** continúa una conversación. Si falta, se crea y se devuelve.

Responde: `{reply, conversation_id, outcome, handoff, case_id, case_status}`.

| `outcome` | Significa | `case_id` |
|---|---|---|
| `resolved` | La política resolvió o el agente respondió (saludo, estado de un caso) | el caso, `auto_resolved`, si hubo disputa |
| `clarify` | Hay 0 o varias transacciones candidatas, o falta el dato clave. Una sola pregunta por turno, máximo 2 turnos; luego escala | `null` |
| `escalated` | Pasa a una persona | **el caso, `escalated`**, si la escalada es sobre una transacción; `null` si no hay transacción (fraude sin elegir una, fuera de alcance, ambigüedad) |
| `unavailable` | **No se pudo verificar** por un fallo del servicio bancario tras los reintentos. No se cambió nada y no hay caso: el cliente puede reintentar | `null` |

`unavailable` llega con `200` y un texto simple en el idioma del cliente (es o pt), no con un `502`. Una sesión vencida sigue siendo `401`.

`handoff` (cuando `outcome` es `escalated`): `reason`, `limitation`, `request` (`{es, pt}`), `customer_language`, `conversation_id`, `verified_facts`, `actions_taken`, `evidence`, `open_questions`, y `case_id` y `escalated_in_backend` si hubo caso. Razones: `amount_threshold`, `amount_unknown`, `posted_charge_disputed`, `fraud_suspected`, `out_of_scope`, `ambiguity_unresolved`, `verify_failed`.

**Motivo del rechazo:** si la transacción está `Declined` y su código es conocido, la respuesta lo dice con el código y aclarando que es el significado estándar. Con un código vacío o desconocido no agrega nada.

**Reintentos del agente al backend:** hasta 3 intentos, con esperas cortas, ante fallo de conexión o `502`, `503`, `504`; **nunca** ante un `4xx`. Es seguro repetir todo porque las escrituras son idempotentes. La conexión tiene su propio límite de 2 s; **el peor caso medido, con el backend caído, fue 6,9 s** hasta responder `unavailable`.

### `POST /session` y `GET /health`

`/session` reenvía el login del backend por `customer_id` y documento; la web no lo usa (entra por `/v1/auth/login`: el token que emite sirve igual para `/chat`).

## 6. BFF (el servidor de Next.js) — contrato a implementar

Aún **no existe**: el frontend actual es el chat viejo, que llama directo al agente. Esto es lo que debe cumplir el nuevo.

| Ruta del BFF | Reenvía a | Notas |
|---|---|---|
| `POST /api/auth/login` | `POST /v1/auth/login` | Pone la cookie y devuelve `{customer}`. **El token no va en el cuerpo de la respuesta** |
| `POST /api/auth/logout` | — | Borra la cookie. `204` |
| `GET /api/auth/demo-accounts` | `GET /v1/auth/demo-accounts` | Sin sesión. Para la pantalla de entrada |
| `GET /api/me`, `/api/me/summary`, `/api/me/products`, `/api/me/products/{id}`, `/api/me/transactions`, `/api/me/transactions/{id}`, `/api/meta/data` | la misma ruta bajo `/v1` | Reenvío tal cual (cuerpo y consulta). Tipos generados del OpenAPI del backend |
| `GET /api/disputes`, `GET /api/disputes/{id}` | `GET /v1/disputes…` | Solo lectura |
| `POST /api/chat` `{message, conversation_id?, transaction_id?}` | `POST /chat` del agente | Pone el token de la cookie en `session_token` |

**Lo que el BFF no debe exponer jamás:** `POST /disputes`, `escalate` ni `resolve`. Abrir, resolver y escalar es política y vive en el agente: un botón "Disputar" en un movimiento **abre el asistente con `transaction_id` elegido**, no crea el caso desde el navegador. Tampoco debe aceptar un `customer_id` del navegador ni devolver el token.

**Sesión:** cookie `__Host-session` (`Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, sin `Domain`), con la vigencia de `expires_in`. En desarrollo local sin HTTPS, `session`. Ante un `401` de cualquier capa, el BFF borra la cookie y responde `401`: la pantalla vuelve al login.

**CSRF:** además de `SameSite=Strict`, las rutas `POST` exigen `Content-Type: application/json` y un `Origin` igual al del propio sitio; si no, `403`.

**Errores:** el mismo código de estado y `{"detail": "...", "request_id": "..."}`. Un fallo de conexión con el backend o el agente es `502` con un texto genérico, sin direcciones internas.

**Tiempos:** 10 s hacia el backend; **60 s hacia el agente** (cubre sus reintentos y al modelo de lenguaje).

**Trazabilidad:** genera `X-Request-ID` si el navegador no trae uno, lo reenvía a ambas capas y lo devuelve.

**Tipos:** se generan de los dos OpenAPI (`openapi-typescript`), de modo que un cambio en una capa rompe la compilación del frontend en lugar de romper la pantalla en producción.

### Lo que el BFF obliga a cambiar en la infraestructura

Hoy, en prod, el frontend y el agente aceptan tráfico **solo del balanceador** (`edge_lockdown`) y el navegador llama al agente por `/agent/*`. Con el BFF eso cambia, y sin estos cambios **el BFF no podría llamar al agente**:

1. **El agente pasa a ser privado como el backend:** ingreso abierto pero **sin `allUsers`**, solo con `roles/run.invoker` para la cuenta de servicio del frontend, que le manda su ID token (en `X-Serverless-Authorization`, igual que hace hoy el agente con el backend). Deja de existir la ruta `/agent/*` del balanceador y la variable `agent_public_url`.
2. **El frontend recibe `run.invoker` sobre el backend** (hoy solo lo tiene el agente) y las direcciones `BACKEND_URL` y `AGENT_URL` como variables **del servidor**, no `NEXT_PUBLIC_*`.
3. **El agente deja de necesitar CORS:** el navegador ya no lo llama. `CORS_ALLOWED_ORIGINS` se puede vaciar.
4. **La cuenta de servicio del frontend necesita poder pedir el ID token** (por el servidor de metadatos, como en `agent/app/gcp_auth.py`).

Esto se aplica con el despliegue del BFF, no antes: mientras el frontend viejo siga llamando al agente desde el navegador, el estado actual es el correcto.

## 7. Flujos de punta a punta

**Entrar:** `POST /api/auth/login` → cookie → `GET /api/me/summary`. Con 5 fallos, `429` con `Retry-After`.

**Ver la cuenta:** `GET /api/me/products`, `GET /api/me/transactions` (con `next_cursor` para más), `GET /api/meta/data` para "datos al…".

**Reportar un cargo desde un movimiento:** `POST /api/chat` con `message` y el `transaction_id` de la fila. Respuesta: `resolved` con su `case_id`, o `escalated` con su `case_id` y el traspaso. La fila se actualiza porque `GET /api/me/transactions` ya trae `case_id` y `dispute_status`.

**Reportar describiendo el cargo:** `POST /api/chat` solo con el texto. Puede responder `clarify` (hasta 2 veces), `resolved`, `escalated` o `unavailable`.

**Seguir un caso:** `GET /api/disputes` y `GET /api/disputes/{id}` (con `events`).

## 8. Límites y supuestos de este contrato

- **El motivo del rechazo (`response_meaning`) es el estándar ISO 8583**, no una definición del organizador. Se dice así en la respuesta.
- **El saldo de un producto de crédito se interpreta como lo adeudado** (inferido). El dataset no tiene MXN aunque la mitad de los clientes es mexicana: la moneda se muestra como está guardada.
- **No hay un servicio de identidad real:** el login es de demostración, con cuentas de demostración de clave pública. El contrato lo declara; no lo disimula.
- **El estado de la conversación del agente vive en la memoria de cada instancia.** Si hay más de una instancia, un turno puede caer en otra y perder el hilo (pierde el contexto de la aclaración, no los casos, que están en la base). Para producción real se necesita un almacén compartido.
- **Un caso `closed` no se puede crear desde ninguna ruta:** lo cierra una persona, y esa operación no existe todavía.
- **La vista del agente humano que recibe las escaladas no está en el alcance:** el traspaso queda guardado en el caso (`evidence.handoff`) y en su línea de tiempo.
