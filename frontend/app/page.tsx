// Server component: the browser never talks to the backend, this page does, on the server.
// BACKEND_URL is a server-only variable set in the Vercel project.
export const dynamic = "force-dynamic";

type DataMeta = {
  gold: { table: string; rows: number }[];
  last_successful_run: { run_id: string; status: string; started_at: string; finished_at: string } | null;
};

const base = process.env.BACKEND_URL?.replace(/\/$/, "");

async function call<T>(path: string): Promise<T | null> {
  if (!base) return null;
  try {
    const res = await fetch(`${base}${path}`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

const numbers = new Intl.NumberFormat("es");
const dates = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

function Status({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className={`row ${ok ? "ok" : "bad"}`}>
      <span>
        <span className="dot" />
        {label}
      </span>
      <span>{detail}</span>
    </div>
  );
}

export default async function Home() {
  const [health, db, meta] = await Promise.all([
    call<{ status: string }>("/health"),
    call<{ status: string }>("/health/db"),
    call<DataMeta>("/meta/data"),
  ]);
  const run = meta?.last_successful_run;

  return (
    <main>
      <h1>Asistente bancario LATAM</h1>
      <p className="sub">Prototipo. Por ahora solo comprueba que las piezas estén conectadas; el chat llega con el agente.</p>

      <section className="card">
        <h2>Servicios</h2>
        {!base && <p className="muted">Falta configurar BACKEND_URL en el proyecto de Vercel.</p>}
        <Status ok={health?.status === "ok"} label="Backend (herramientas)" detail={health ? "operativo" : "sin respuesta"} />
        <Status ok={db?.status === "ok"} label="Base de datos" detail={db ? "operativa" : "sin conexión"} />
      </section>

      <section className="card">
        <h2>Datos disponibles (capa gold)</h2>
        {meta ? (
          meta.gold.map((t) => (
            <div className="row" key={t.table}>
              <code>{t.table}</code>
              <span>{numbers.format(t.rows)} filas</span>
            </div>
          ))
        ) : (
          <p className="muted">No se pudieron leer los datos.</p>
        )}
      </section>

      <section className="card">
        <h2>Última corrida exitosa del pipeline</h2>
        {run ? (
          <>
            <div className="row">
              <span>Terminó (UTC)</span>
              <span>{dates.format(new Date(run.finished_at))}</span>
            </div>
            <div className="row">
              <span>Identificador</span>
              <code>{run.run_id.slice(0, 8)}</code>
            </div>
          </>
        ) : (
          <p className="muted">{meta ? "Todavía no hay corridas registradas." : "No disponible."}</p>
        )}
      </section>
    </main>
  );
}
