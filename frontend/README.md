# frontend/ — interfaz de chat (Vercel)

Vertical 5 de `../spec/ARCHITECTURE.md`. App Next.js (App Router, TypeScript) desplegada en Vercel, con el directorio raíz del proyecto en `frontend/`.

## Estado: cascarón

Una página que prueba el cableado de punta a punta: desde el servidor consulta al backend (`/health`, `/health/db`, `/meta/data`) y muestra si responde, qué tablas `gold` hay y cuándo terminó la última corrida exitosa del pipeline. **El chat llega con el agente.**

## Cómo habla con el backend

La página es un componente de servidor: es Vercel quien llama al backend, el navegador nunca lo hace. La URL pública del backend va en la variable **`BACKEND_URL`** (solo servidor, configurada en el proyecto de Vercel; ver `.env.example`). Por eso no hay CORS. El backend hoy tiene URL pública solo para esto: cuando exista el agente, el frontend hablará con el agente y el backend volverá a ser privado.

## Documentación de datos

`/data-docs` sirve el sitio estático de `dbt docs` (grafo de linaje navegable, catálogo de columnas con tipos, tests y descripciones). Es un archivo generado: `public/data-docs/index.html`. No se actualiza solo; regenerarlo cuando cambien los modelos de dbt:

```bash
cd data/dbt && export $(cat .env | xargs)
dbt docs generate --static --target-path /tmp/dbt-docs
cp /tmp/dbt-docs/static_index.html ../../frontend/public/data-docs/index.html
```

Contiene solo metadatos del modelo (nombres, tipos, SQL de los modelos), sin datos de clientes ni credenciales.

## Despliegue

Proyecto de Vercel `latam-bank-frontend` (equipo `eiretelabs`, plan hobby, del que el autor es el único miembro). URL pública: **https://latam-bank-frontend.vercel.app**. Las URLs de cada despliegue y el alias con el nombre del equipo pasan por el login de Vercel (protección por defecto); el dominio de producción de arriba es público.

- Variable `BACKEND_URL` (production, preview, development): URL pública del servicio `backend` de Railway.
- El proyecto **no está conectado a Git todavía**: se despliega a mano con `vercel deploy --prod` desde `frontend/`. Conectar el repo de GitHub desde el panel de Vercel haría que cada push a `main` redespliegue.
- `frontend/.vercel/` (vínculo local al proyecto) está en `.gitignore`.

## Desarrollo

```bash
cd frontend
cp .env.example .env.local   # completar BACKEND_URL
npm install
npm run dev
```
