# frontend/ — chat UI

Deploy en Vercel, no Railway. Pega directo a `POST /chat` de `../agent/`, nunca accede a Postgres ni a `../backend/` directo.

Pendiente de crear (una vez el equipo vote el workflow): app Next.js mínima con interfaz de chat, capaz de mostrar los 3 caminos obligatorios (resolución normal, aclaración por ambigüedad, handoff a humano) y soportar input en español y portugués.
