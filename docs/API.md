# Contrato de las APIs

[Índice](README.md) · [Workflow](WORKFLOW.md) · [Arquitectura](ARCHITECTURE.md) · [Datos](DATA.md) · [API](API.md)

Contrato del workflow A (disputas de transacciones) entre **la interfaz web**, **el agente** y **el backend**, incluida la consola del especialista. Fecha: 2026-10-04, ya con el trabajo de Felix (consola y casos del cliente) fusionado.

## Cómo se mantiene este contrato

| Fuente | Qué dice | Quién la hace cumplir |
|---|---|---|
| `backend/tests/contract/openapi.json` y `agent/tests/contract/openapi.json` | Rutas, parámetros, cuerpos y esquemas de respuesta. **Lo genera el código** | Una prueba falla si el código genera algo distinto. Cambiar el contrato es una decisión que se revisa en el diff (`UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py` lo regenera) |
| **Este documento** | Lo que un esquema no puede decir: reglas, estados, orden de las llamadas, seguridad, límites y supuestos | Revisión |

Si este documento y un OpenAPI se contradicen, **gana el OpenAPI**: es el que ejecutan las pruebas.

Lo que el contrato del backend hace cumplir con pruebas:
- las operaciones que **no** piden sesión son exactamente: `GET /health`, `GET /ready`, `POST /session`, `POST /admin/session`, `POST /v1/auth/login`, `GET /v1/auth/demo-accounts` y `GET /meta/demo-scenarios`. Se comprobó haciendo público `/v1/me` y viendo fallar la prueba;
- ninguna ruta de cliente recibe un `customer_id` del que llama (las de administrador pueden filtrar por cliente: el rol es lo que las autoriza);
- ningún esquema tiene un campo para `is_fraud`, `fraud_score`, `password_hash`, `credit_score` ni `estimated_monthly_income`;
- el cuerpo de `POST /chat` no puede nombrar a un cliente.

## 1. Quién llama a quién

```
Navegador ─► ALB + Cloud Armor ─┬─► Frontend (Next.js)   páginas: / (cliente) y /admin (especialista)
                                └─► Agente  (/agent/*)   ◄── el navegador lo llama directo, con el token de sesión
                                         │
                                         └─► Backend (privado, ID token de Cloud Run) ─► Cloud SQL
```

- **La interfaz web llama al agente desde el navegador** (`/session`, `/chat`, `/me/disputes`, `/disputes/{id}`, `/meta/demo-scenarios`, y `/admin/*` para la consola). El agente reenvía al backend lo que no es suyo.
- **El backend es privado:** solo cuentas de servicio con `run.invoker` lo llaman, con su ID token en `X-Serverless-Authorization`. `Authorization` queda libre para el token de sesión.
- **El agente** lee datos solo a través del backend; nunca toca la base de los clientes. Solo escribe su propia traza (`agent.trace_log`).

## 2. Convenciones comunes

| Tema | Regla |
|---|---|
| Formato | JSON en UTF-8. Fechas en ISO 8601 (las marcas con zona terminan en `Z`) |
| Dinero | **Número** más `currency` aparte. `amount_usd_effective` es `amount_usd` o, si falta y la moneda es USD, `amount`. Es `null` si no se conoce: **nunca se trata como cero** |
| Identificadores | Opacos. `case_id` es un UUID; los de transacción y producto son texto del dataset |
| Sesión | `Authorization: Bearer <token>`. JWT HS256, emisor `backend-sandbox`. **Dos roles:** `customer` (`sub` = `customer_id`, 2 horas) y `admin` (`sub` = usuario, `role=admin`, 8 horas por defecto). **Un token de un rol no abre las rutas del otro** (`403`). La identidad sale siempre del token |
| Trazabilidad | Toda respuesta del backend y del agente lleva `X-Request-ID`. Si la solicitud trae uno válido (8 a 100 caracteres de `A-Za-z0-9._-`) se conserva; si no, se crea. El agente lo reenvía al backend. Cada solicitud escribe una línea de registro JSON con `severity`; **no** se registra `Authorization`, la cadena de consulta ni ningún cuerpo |
| Paginación | La API `/v1` pagina por **cursor** (`?limit=` de 1 a 100 y `?cursor=`); un cursor que el servicio no emitió da `422`. La bandeja del administrador usa `limit` y `offset` |
| Un caso por transacción | Reportar de nuevo una transacción que ya tiene un caso (no `closed`) **devuelve ese caso**: la ruta responde `201` y el cuerpo es el caso que ya existía. Dos solicitudes simultáneas crean uno solo. Un caso **sin** transacción nunca es duplicado de otro |
| Versiones | `/v1` solo admite cambios que no rompen. Las rutas de la raíz son las de la interfaz y el agente y están congeladas en su forma |

### Errores

El cuerpo es `{"detail": "<texto>"}`. Los errores de validación (`422`) traen `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`. El texto no incluye datos de otro cliente.

| Código | Cuándo |
|---|---|
| `401` | Falta el token, está mal formado o venció. También el login con credenciales erróneas (**la misma respuesta si el usuario no existe**) |
| `403` | El token es de otro rol |
| `404` | No existe **o no es del cliente**. Las dos cosas son indistinguibles a propósito |
| `409` | `resolve` sobre un caso que no está `open`, o que cambió de estado mientras tanto |
| `422` | Parámetro o cuerpo inválido |
| `429` | Cinco intentos de login fallidos (`LOGIN_MAX_FAILED_ATTEMPTS`): la cuenta se bloquea 15 minutos. Trae `Retry-After` |
| `503` | `GET /ready` sin base; el login de administrador si `ADMIN_USERS` está vacío |

## 3. Backend

El esquema exacto está en `backend/tests/contract/openapi.json`. Aquí, lo que cada ruta hace y lo que el esquema no dice.

### 3.1 Raíz, la que usan la interfaz y el agente

| Ruta | Sesión | Hace |
|---|---|---|
| `POST /session` `{customer_id, document_number}` | no | Login de **sandbox** del cliente: valida contra `gold.customers`. No hay proveedor de identidad detrás |
| `POST /admin/session` `{username, password}` | no | Login del especialista con `ADMIN_USERS` (hashes bcrypt, en Secret Manager). Cinco fallos por IP y usuario bloquean 60 s |
| `GET /me`, `GET /me/transactions`, `GET /me/transactions/{id}` | cliente | Perfil mínimo y movimientos propios (lista simple). Cada movimiento trae `response_meaning` |
| `GET /me/disputes` | cliente | Mis casos, más nuevos primero (incluye los cerrados y los que no tienen transacción) |
| `GET /me/conversations` | cliente | Mis conversaciones, la más reciente primero, con el título (lo primero que escribió). Propias del agente: `agent.conversation_messages` |
| `GET /me/conversations/{id}` | cliente | Una conversación completa (mensajes y las tarjetas de cada respuesta). 404 si no existe o es de otro cliente |
| `POST /disputes` `{transaction_id?, reason_code, summary}` | cliente | Abre el caso. `transaction_id` es **opcional**: una escalada que no pudo atarse a una transacción es un caso sin transacción |
| `GET /disputes/{case_id}` | cliente | El caso con su línea de tiempo (`events`) |
| `POST /disputes/{case_id}/escalate` `{handoff}` | cliente | Lo llama el agente. Marca `escalated` y guarda el traspaso. **No se guarda por estado**: se puede llamar sobre cualquier caso del cliente |
| `POST /disputes/{case_id}/resolve` `{resolution}` | cliente | Lo llama el agente. `resolution` es `no_charge_confirmed` o `reversal_confirmed`. Pasa `open` a `auto_resolved`; repetirlo sobre uno ya `auto_resolved` lo devuelve igual; sobre cualquier otro estado, `409`. **Los humanos nunca ponen `auto_resolved`** |
| `GET /meta/demo-scenarios` | no | Hasta cuatro escenarios deterministas para la demo, calculados de los datos (umbral, fraude, auto-resuelto…). Público a propósito: solo expone lo que el login de prueba ya pide |
| `GET /health`, `GET /ready` | no | El proceso vive / alcanza la base |

### 3.2 Administrador (`role=admin`)

| Ruta | Hace |
|---|---|
| `GET /admin/disputes?status=&customer_id=&limit=&offset=` | Bandeja con cliente, idioma y motivo del traspaso. `status=active` incluye `escalated` e `in_progress` |
| `GET /admin/disputes/{case_id}` | Detalle: traspaso, `conversation_id` y eventos auditados |
| `POST /admin/disputes/{case_id}/transition` `{action, note, resolution?}` | `claim`: `open` o `escalated` → `in_progress`. `close`: `in_progress` → `closed`, con **nota obligatoria y resolución obligatoria**. Cada transición agrega un evento |
| `GET /admin/metrics?window=<horas>` | Totales por estado, resolución automática segura **con su denominador**, escalamientos, cierres humanos, idioma y motivo. Sin casos la tasa es `null` ("no definida"), no cero |
| `GET /meta/data` | Frescura: conteos de `gold.*`, el borde del snapshot y la última corrida de `ops.etl_runs` |

### 3.3 `/v1`, la superficie para una aplicación web que no usa el agente directo

La interfaz actual **no la usa**; se conserva porque está cubierta por pruebas y por este contrato, y es el camino para un BFF futuro.

| Ruta | Hace |
|---|---|
| `POST /v1/auth/login` `{username, password}` | Usuario y clave (argon2id). Cinco fallos bloquean la cuenta; un acceso correcto la reinicia. La misma respuesta si el usuario no existe |
| `GET /v1/auth/demo-accounts` | Cuentas de demostración y su clave compartida (pública a propósito). **`404` salvo `DEMO_ACCOUNTS_ENABLED=true`** |
| `GET /v1/me`, `/v1/me/summary` | Perfil, y saldos por moneda (**depósitos y crédito separados, nunca neteados**) con los últimos movimientos y los casos activos |
| `GET /v1/me/products` y `/{id}` | Productos con el número **enmascarado** (`****1234`) y `kind` (`deposit`, `credit`, `other`) |
| `GET /v1/me/transactions` y `/{id}` | `{items, next_cursor}` con filtros `product_id`, `status`, `merchant`, `from`, `to`. Cada fila trae `case_id`, `dispute_status` y `response_meaning` |
| `GET /v1/disputes`, `/v1/disputes/{id}`, `POST /v1/disputes…` | Las mismas rutas de disputas de la raíz |

**`response_meaning`** (`{es, pt}` o `null`) es el significado estándar (ISO 8583) del `response_code`. **Es un supuesto:** el organizador no define los códigos; el dataset solo trae `00`, `05`, `14`, `51` y `54` (y vacío en ~5 %). Un código vacío o desconocido da `null`: no se inventa un motivo.

**`kind` y los saldos:** el diccionario del organizador tampoco define `current_balance`. En un depósito es lo que el cliente tiene; **en crédito se infiere que es lo que debe** (hay 7.510 productos de crédito con saldo mayor que su límite, lo que solo tiene sentido si el saldo es lo usado).

## 4. Estados del caso y quién los cambia

```
              ┌─── resolve (agente) ──► auto_resolved ──┐
   open ──────┤                                          ├── escalate (agente) ──► escalated ── claim (especialista) ──► in_progress ── close ──► closed
              └──────────── escalate (agente) ──────────┘
```

| Estado | Significa | Lo pone |
|---|---|---|
| `open` | Recién abierto, en proceso | `POST /disputes` |
| `auto_resolved` | La política lo resolvió **y quedó registrado** (`no_charge_confirmed` o `reversal_confirmed`) | solo el agente, por `resolve` |
| `escalated` | Espera a un especialista, con su traspaso | el agente, por `escalate` |
| `in_progress` | Un especialista lo tomó | el especialista, por `claim` |
| `closed` | El especialista lo cerró, con nota y resolución | el especialista, por `close`. **Un caso `closed` no cuenta**: la transacción se puede reportar de nuevo |

Las escaladas **sin transacción** (fraude sin una transacción elegida, ambigüedad que no se resolvió) son casos con `transaction_id` nulo: así llegan igual a la bandeja del especialista. Un caso escalado no tiene `resolved_at`: eso es solo para lo que se resolvió.

La línea de tiempo (`events`) solo crece: `created`, y luego `auto_resolved`, `escalated`, `claimed`, `closed`.

## 5. Agente

El esquema exacto está en `agent/tests/contract/openapi.json`.

### `POST /chat`

Pide: `{session_token, message, conversation_id?, transaction_id?}`. El token va en el cuerpo, no en una cabecera.

- **`transaction_id`** es el movimiento que el cliente eligió. Identifica la transacción mejor que cualquier texto: no se busca ni se pide confirmar. **Todo lo demás sigue aplicando** (umbral de USD 500, cobro ya aprobado, monto desconocido). El backend verifica que sea del cliente; **uno ajeno se ignora** como si no se hubiera elegido, sin error y sin datos ajenos. No se hereda al siguiente turno. *La interfaz actual no lo usa: arma una frase ("Fue el cobro de X en Y") al elegir un candidato.*
- **`conversation_id`** continúa una conversación; si falta, se crea y se devuelve.

Responde: `{reply, conversation_id, outcome, handoff, case_id, case_status, case, candidates, reason, language}`. `case_id` y `case_status` son el caso que este turno abrió o encontró; `case`, `candidates`, `reason` y `language` son los que la interfaz usa para sus tarjetas.

| `outcome` | Significa | Caso |
|---|---|---|
| `resolved` | La política resolvió, o el agente respondió (saludo, estado de un caso) | `auto_resolved` si hubo disputa |
| `clarify` | Hay 0 o varias transacciones candidatas, o falta el dato clave (con `candidates` si hay). Una pregunta por turno, máximo 2; luego escala | ninguno |
| `escalated` | Pasa a una persona | **el caso, `escalated`**, atado a la transacción si se pudo; sin transacción si no |
| `unavailable` | **No se pudo verificar** por un fallo del servicio bancario tras los reintentos. No se cambió nada: el cliente puede reintentar | ninguno |

**La resolución automática se cierra o escala.** Después de abrir el caso, el agente lo relee y lo marca `auto_resolved` por `resolve`, y lo relee de nuevo. **Si no se puede marcar, el turno se vuelve una escalada con motivo `verify_failed`**: "resuelto" nunca es una promesa que nadie registró.

`unavailable` llega con `200` y un texto simple en el idioma del cliente (es o pt), no con un `502`. Una sesión vencida sigue siendo `401`.

`handoff` (cuando `outcome` es `escalated`): `reason`, `limitation`, `request` (`{es, pt}`), `customer_language`, `conversation_id`, `verified_facts`, `actions_taken`, `evidence`, `open_questions`, y `case_id` y `escalated_in_backend` si hubo caso. Razones: `amount_threshold`, `amount_unknown`, `posted_charge_disputed`, `fraud_suspected`, `out_of_scope`, `ambiguity_unresolved`, `verify_failed`.

**Motivo del rechazo:** si la transacción está `Declined` y su código es conocido, la respuesta lo dice con el código y aclarando que es el significado estándar. Con un código vacío o desconocido no agrega nada.

**Reintentos del agente al backend:** hasta 3 intentos con esperas cortas, ante fallo de conexión o `502`, `503`, `504`; **nunca** ante un `4xx`. Es seguro repetir todo porque las escrituras son idempotentes. La conexión tiene su propio límite de 2 s; **el peor caso medido, con el backend caído, fue 6,9 s** hasta responder `unavailable`.

### El resto de las rutas del agente

Son reenvíos delgados al backend con la misma sesión, con comprobaciones previas que fallan rápido: `GET /me/disputes`, `GET /disputes/{id}`, `GET /meta/demo-scenarios`, `GET /meta/data` y, para el especialista, `POST /admin/session`, `GET /admin/disputes`, `GET /admin/disputes/{id}` y `POST /admin/disputes/{id}/transition`, más `GET /admin/metrics`. **Dos rutas son del propio agente**: `GET /admin/agent-metrics` (resultados, contención, latencia p50 y p95, intenciones e idiomas, de `agent.trace_log`) y `GET /admin/conversations/{id}/trace` (los pasos de una conversación). También son del agente las del cliente `GET /me/conversations` y `GET /me/conversations/{id}`: guardan lo que el cliente escribió y lo que se le respondió, y solo se leen con el cliente que sale del token verificado (la tabla es la que lleva la política de retención; `trace_log` sigue sin texto de usuario). `POST /session` reenvía el login del backend.

## 6. Flujos de punta a punta

**Cliente:** `POST /session` → `POST /chat` (con `message` y, si lo eligió, `transaction_id`) → `resolved` con su caso, o `escalated` con su caso y su traspaso → `GET /me/disputes` para "Mis casos" y `GET /me/conversations` para las conversaciones recientes, que se reabren con `GET /me/conversations/{id}`.

**Especialista:** `POST /admin/session` → `GET /admin/disputes?status=active` → detalle (traspaso y eventos) → `claim` → `close` con nota y resolución → `GET /admin/metrics`.

## 7. Evolución posible: un servidor intermedio (BFF) para la web

No existe, y no hace falta para la entrega. Si la interfaz dejara de llamar al agente desde el navegador, el servidor de Next sería quien guardara el token en una cookie `httpOnly` y llamara a `/v1` y a `/chat`. Eso **forzaría cambios de infraestructura**: hoy el agente solo acepta tráfico del balanceador, así que el servidor de Next no podría llamarlo; el agente tendría que volverse privado como el backend, con el frontend como invocador. Por eso `/v1` se mantiene.

## 8. Límites y supuestos

- **El motivo del rechazo (`response_meaning`) es el estándar ISO 8583**, no una definición del organizador. Se dice así en la respuesta.
- **El saldo de un producto de crédito se interpreta como lo adeudado** (inferido). El dataset no tiene MXN aunque la mitad de los clientes es mexicana: la moneda se muestra como está guardada.
- **No hay un servicio de identidad real.** El login del cliente (`customer_id` y documento) y el del especialista son de demostración, El del especialista tiene un límite de intentos por proceso. El contrato lo declara; no lo disimula.
- **`escalate` no se guarda por estado**: se puede volver a llamar sobre un caso ya escalado o cerrado y reescribe el traspaso. Es lo que hace la implementación de la consola; conviene protegerlo antes de producción.
- **El estado de la conversación del agente vive en la memoria de cada instancia.** Con más de una instancia, un turno puede caer en otra y perder el hilo (se pierde el contexto de la aclaración, no los casos, que están en la base). Producción real necesita un almacén compartido.
- **El límite de intentos del login del especialista vive en la memoria de cada proceso** (con varias instancias, cada una cuenta aparte). El de `POST /v1/auth/login` está en la base, por cuenta. `POST /session` (cliente y documento) no tiene límite de intentos.
