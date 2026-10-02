# Backend y arquitectura de la aplicación web

Decisiones de diseño del backend para el home banking del asistente de disputas (workflow A). Complementa `DISPUTE_WORKFLOW.md` (la política) y `backend/README.md` (el contrato endpoint por endpoint). Fecha: 2026-10-02.

## 1. Arquitectura

```
Navegador ──► ALB + Cloud Armor ──► Frontend Next.js   (BFF: /api/*, cookie httpOnly)
                                       ├─► Backend  /v1   (ID token de Cloud Run, privado) ──► Cloud SQL
                                       └─► Agente   /chat (JWT del cliente)  ──► Backend (ID token) ──► Cloud SQL
```

**El navegador no habla con el backend.** Lo hace el servidor de Next.js (BFF), por tres razones:
1. El backend sigue **privado**: solo cuentas de servicio con `run.invoker` lo llaman, con su ID token.
2. El JWT de sesión vive en una cookie `httpOnly`, `Secure`, `SameSite=Strict`: ningún JavaScript de la página puede leerlo (un XSS no se lo lleva).
3. Un solo origen: no hay CORS ni lista de orígenes que mantener.

Dos superficies sobre el mismo servicio de FastAPI: la **raíz** es la del agente y no cambia de forma; **`/v1`** es la de la web. El agente no se tocó salvo para marcar los casos resueltos (§4).

## 2. Autenticación

- `POST /v1/auth/login` con usuario y clave. La clave se guarda como **argon2id** (`app.credentials`); nunca viaja en una respuesta.
- **Sin enumeración de usuarios:** un usuario inexistente y una clave errónea dan la misma respuesta, y tardan lo mismo (el usuario inexistente se compara contra un hash de relleno).
- **Bloqueo:** 5 fallos seguidos bloquean la cuenta 15 minutos (`429` con `Retry-After`); un acceso correcto reinicia la cuenta. Cloud Armor además limita las solicitudes por IP.
- **Cuentas de demostración:** tres clientes del dataset sintético, los mismos que usa `infra/gcp/scripts/e2e.py`, así que lo que cada uno muestra está verificado (escala por monto; se resuelve solo; se resuelve solo por reverso). Se crean al arrancar con una clave compartida **pública a propósito** (los datos son sintéticos) y se listan en `GET /v1/auth/demo-accounts`. Se apagan con `DEMO_ACCOUNTS_ENABLED=false`.
- El JWT (HS256, 2 horas) es el mismo que usa el agente: `sub` es el `customer_id`. La identidad **siempre** sale del token validado.

## 3. Datos

- **Productos** (`gold.products`): número enmascarado en SQL (`****1234`), nunca el completo. `kind` clasifica el producto: *depósito* (Cuenta Ahorro, Cuenta Corriente, Inversión), *crédito* (Tarjeta Crédito, Préstamos) u *otro*.
- **Supuesto sin verificar:** el diccionario del organizador no define `current_balance`. En un depósito es lo que el cliente tiene; en crédito se **infiere** que es lo que debe (7.510 productos de crédito tienen saldo mayor que su límite, lo que solo tiene sentido si el saldo es lo usado). Por eso el resumen suma depósitos y crédito **por separado** y nunca los netea.
- **Moneda:** el dataset no tiene MXN aunque la mitad de los clientes es mexicana (`DATA_FINDINGS.md`): se muestra la moneda como está guardada.
- **Historial** paginado por **cursor** (fecha e id), no por OFFSET: no repite ni salta filas aunque entren movimientos nuevos, y desempata los de igual instante. Cada fila dice si ya tiene un caso (`case_id`, `dispute_status`) para ofrecer "reportar" o "ver mi caso".
- Dinero como número en el JSON (la base usa `numeric`, que Pydantic escribiría como texto).

## 4. Casos de disputa

- **Un caso por (cliente, transacción)**, con un índice único parcial (excluye los `closed`). Reportar de nuevo devuelve el mismo caso (`200`, no `201`). Antes, cada intento del agente abría uno nuevo. La migración 0003 cierra los duplicados viejos (conserva el más reciente) y deja un evento que explica por qué.
- **Estados:** `open → auto_resolved` o `open/auto_resolved → escalated`. `escalated` y `closed` son finales; repetir una operación no es un error ni reescribe nada.
- **Hueco que se cerró:** ningún endpoint marcaba `auto_resolved`, así que los casos que el agente resolvía por política quedaban `open` y "Mis casos" los habría mostrado como abiertos. Nuevo `POST /disputes/{id}/resolve`; el agente lo llama en su paso `verify` y vuelve a leer el caso (no confía en su propia escritura). Con un backend antiguo (404) el caso queda `open` y el cliente recibe la misma respuesta.

## 5. Cómo se verificó (y qué reveló)

La suite tiene dos capas. Las rutas se prueban con un store en memoria; **el SQL real se prueba contra PostgreSQL** (migraciones, paginación, resumen, bloqueo, carreras, y el arranque completo: migrar, sembrar, iniciar sesión). El CI levanta un PostgreSQL 18.

Esa segunda capa encontró tres errores que la primera no podía ver:
1. **Preexistente:** `escalate_dispute` pasaba un texto JSON a un parámetro `jsonb` cuyo códec ya serializa, así que **todo handoff se guardaba como texto dentro de JSON**. La migración 0004 repara lo ya guardado.
2. `last_transaction_date` es `timestamp` en `gold` y el modelo de respuesta decía `date`: habría dado un 500 con cualquier hora que no fuera medianoche.
3. `case_id` llega como `UUID` y el modelo decía `str`: un 500 en `GET /v1/disputes`.

## 6. Pendiente

- **El BFF y las pantallas** en el frontend (login, inicio, productos, movimientos, mis casos, el asistente en un panel).
- **Desplegar:** requiere imagen nueva del backend y del agente, y un `apply` (variables `demo_accounts_enabled` y `demo_password`).
- Comprobar en prod que la migración 0004 repara los handoffs ya guardados.
- Cambio de clave y recuperación: fuera de alcance (cuentas de demostración).
