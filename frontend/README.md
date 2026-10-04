# frontend/: chat del cliente y consola del especialista

Next.js 16 (App Router) y TypeScript, sin Tailwind. Corre en Cloud Run (`output: standalone`). Llama **solo al agente** desde el navegador (`POST /session`, `POST /chat`, `GET /me/*`, `GET /admin/*`): nunca al backend ni a Postgres.

## Cliente (`/`)

- **Ingreso:** `customer_id` más número de documento (sandbox, sin proveedor de identidad). Los **escenarios de demostración** vienen de `/meta/demo-scenarios` y se ven como tarjetas.
- **Chat al estilo de un asistente:** barra lateral con *Nueva conversación*, *Mis casos* y las conversaciones recientes (se guardan en el agente y se reabren), columna central, compositor flotante que crece y envía con Enter, preguntas sugeridas, indicador de escritura y respuesta que aparece palabra por palabra.
- **Tarjetas:** las transacciones candidatas para elegir, el caso con su evidencia (la transacción y lo decidido, con detalle al pasar el cursor) y el traspaso a una persona.
- **Idioma:** español o portugués, según el que detecta el agente.
- **Tema:** claro u oscuro; sigue el sistema y un botón lo cambia y lo recuerda.
- **Sesión vencida:** un 401 del agente vuelve al ingreso con un aviso.
- **Accesibilidad:** foco visible, navegación por teclado, `aria-live`, objetivos táctiles de 44 px y `prefers-reduced-motion`.

## Especialistas (`/admin`)

- Ingreso de sandbox aparte (`ADMIN_USERS` en el backend).
- Bandeja de casos escalados y en curso, con filtros; detalle con el traspaso, la auditoría y la traza del agente.
- `claim → in_progress → close`: cerrar exige nota y resultado.
- Métricas de backend y agente con sus denominadores; sin muestra suficiente muestran "No definido".
- Sin proveedor de identidad real; el token vive solo en la memoria del navegador.

## Variables

| Variable | Qué es |
|---|---|
| `AGENT_URL` | URL del agente en tiempo de ejecución (Cloud Run). Es la única API que conoce el navegador |
| `NEXT_PUBLIC_AGENT_URL` | Alternativa para desarrollo local |

## Desarrollo y verificación

```bash
pnpm install          # desde frontend/
pnpm build            # compilación y tipos (también corre en el CI)
pnpm dev              # servidor de desarrollo
pnpm start            # sirve la compilación
```

`pnpm-workspace.yaml` fija `trustPolicyIgnoreAfter` para que `pnpm install` funcione con la política de confianza de pnpm 11 sin banderas locales. Si `pnpm` falla al descargar su propia versión, ver [`docs/LOCAL_DEV.md`](../docs/LOCAL_DEV.md).

## Despliegue

En GCP es el servicio de Cloud Run `frontend`; Terraform fija `AGENT_URL` al agente, detrás del balanceador. Para otro host, define `AGENT_URL` o `NEXT_PUBLIC_AGENT_URL`.
