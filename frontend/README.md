# frontend/ — interfaz de chat (Vercel)

Vertical 5 de `../spec/ARCHITECTURE.md`. App Next.js (App Router, TypeScript) desplegada en Vercel, con el directorio raíz del proyecto en `frontend/`.

## Estado: cascarón

Una página que prueba el cableado de punta a punta: desde el servidor consulta al backend (`/health`, `/health/db`, `/meta/data`) y muestra si responde, qué tablas `gold` hay y cuándo terminó la última corrida exitosa del pipeline. **El chat llega con el agente.**

## Cómo habla con el backend

La página es un componente de servidor: es Vercel quien llama al backend, el navegador nunca lo hace. La URL pública del backend va en la variable **`BACKEND_URL`** (solo servidor, configurada en el proyecto de Vercel; ver `.env.example`). Por eso no hay CORS. El backend hoy tiene URL pública solo para esto: cuando exista el agente, el frontend hablará con el agente y el backend volverá a ser privado.

## Desarrollo

```bash
cd frontend
cp .env.example .env.local   # completar BACKEND_URL
npm install
npm run dev
```
