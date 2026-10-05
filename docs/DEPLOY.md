# Despliegue a producción

[Índice](README.md) · [Arquitectura](ARCHITECTURE.md) · [Ruta a producción](PRODUCTION.md) · [Seguridad](SECURITY.md)

*Qué cambia, qué hacer antes, cómo aplicar, qué hacer después y cómo volver atrás. Pensado para correrlo de arriba abajo. Cada paso dice quién lo hace y por qué.*

## Qué cambia

Lo dice el `plan` de `prod`, que se corrió desde GitHub con la cuenta de solo lectura y no aplicó nada: **3 recursos nuevos, 5 cambios en sitio, 0 destruidos.**

| Cambio | Qué es |
|---|---|
| Servicios `frontend`, `agent`, `backend` y el job `etl` | Imagen nueva (la del commit) y variables nuevas. El agente pasa a usar `anthropic/claude-haiku-4.5`, el modelo de la [Evaluación](EVALUATION.md) |
| VM de Airflow | Solo cambia la etiqueta de la imagen en sus metadatos. La VM sigue apagada hasta que se use |
| Secreto `factored-prod-admin-users` y su permiso de lectura para el backend | **Nuevo, vacío (`NOT_SET`)**: hay que cargarlo, o la consola `/admin` responde 503 |

Un `plan` anterior mostraba 3 destrucciones: el acceso a la VM de Airflow de quien la opera. Eran permisos que un `apply` local había dado con una variable que el flujo de GitHub no pasaba. Ya la pasa, desde la variable del repositorio `AIRFLOW_ADMIN_MEMBERS`; sin ella, aplicar desde GitHub le quita el acceso a quien lo tenía.

**Datos.** Las migraciones del backend corren al arrancar, una vez y con un candado:

- `0003` deja **un solo caso por cliente y transacción**: cierra los más antiguos si había duplicados. No se deshace.
- `0005` permite casos sin transacción, admite el estado `in_progress` y repara traspasos guardados como texto.

## Antes de aplicar

| # | Paso | Quién |
|---|---|---|
| 1 | Mirar los duplicados que cerraría `0003` (abajo). Si son casos de prueba, no importa | Tú |
| 2 | Opcional pero recomendado: en GitHub, **Settings, Environments, prod**, añadir revisores obligatorios. Hoy cualquiera con permiso de escritura puede aplicar a `prod` | Tú |
| 3 | Confirmar que `AIRFLOW_ADMIN_MEMBERS` existe: `gh variable list` | Tú |

**Mirar los duplicados** (enciende la VM, consulta y la apaga):

```bash
ENVIRONMENT=prod ./infra/gcp/scripts/airflow_vm.sh start
cat <<'PY' | gcloud compute ssh factored-prod-airflow --zone us-east4-a --project bitcoders-factored-hackathon \
    --tunnel-through-iap --quiet --command "sudo docker exec -i airflow-scheduler-1 python -"
import os, psycopg2
c = psycopg2.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"], dbname=os.environ["PG_DATABASE"],
                     user=os.environ["PG_USER"], password=os.environ["PG_PASSWORD"], sslmode="require")
cur = c.cursor()
cur.execute("select count(*) from app.disputes"); print("casos:", cur.fetchone()[0])
cur.execute("""select customer_id, transaction_id, count(*) from app.disputes
               where transaction_id is not null and status <> 'closed'
               group by 1, 2 having count(*) > 1""")
print("transacciones con más de un caso abierto:", cur.fetchall())
PY
```

## Aplicar

```bash
gh workflow run "GCP deploy" --ref main -f environment=prod -f terraform_action=apply -f run_etl=false
gh run watch            # elegir la corrida
```

Hace, en orden: crea el registro de imágenes si falta, construye las cinco imágenes con el commit como etiqueta, las sube, planifica, **revisa el plan con Checkov**, aplica el mismo plan y comprueba la salud (`/` y `/agent/health` por el balanceador, y que el backend responda 403 sin credenciales). Tarda unos 8 minutos. Solo aplica desde `main`.

`run_etl=true` además relanza el job que carga los datos. No hace falta: `gold` ya está cargado.

## Después de aplicar

**1. Los permisos de base de datos.** `roles.sql` cambió (permisos de lectura para la consola). Con la VM encendida:

```bash
ENVIRONMENT=prod ./infra/gcp/scripts/db_roles.sh
```

**2. Los dos secretos.**

```bash
# Consola de especialistas: usuario:hash de bcrypt, varios separados por coma. La clave no queda escrita en ningún sitio.
python3 -c "import bcrypt,getpass; print('ops:'+bcrypt.hashpw(getpass.getpass('clave: ').encode(), bcrypt.gensalt()).decode())" \
  | gcloud secrets versions add factored-prod-admin-users --data-file=- --project bitcoders-factored-hackathon

# Modelo de lenguaje: sin esta clave el agente funciona sin modelo (90,6 % de las disputas, 82,8 % en portugués)
printf '%s' "$OPENROUTER_API_KEY" \
  | gcloud secrets versions add factored-prod-openrouter-api-key --data-file=- --project bitcoders-factored-hackathon
```

**3. Que los servicios lean los secretos nuevos.** Cloud Run lee un secreto al arrancar una instancia:

```bash
for s in backend agent; do
  gcloud run services update factored-prod-$s --region us-east4 --project bitcoders-factored-hackathon \
    --update-labels redeploy=$(date +%s)
done
```

**4. Verificar.**

```bash
AGENT_URL="$(cd infra/gcp/envs/prod && terraform output -raw edge_url)/agent" python3 infra/gcp/scripts/e2e.py   # 11 escenarios, debe salir 0
```

Y a mano, en el navegador con la URL del balanceador: entrar como un cliente de demostración, un caso que se resuelve, uno que se escala, otro en portugués, y la consola `/admin` con el usuario cargado.

**5. Apagar la VM** si se encendió: `./infra/gcp/scripts/airflow_vm.sh stop` (también se apaga sola a las 03:00).

## Volver atrás

- **Servicios.** Cloud Run guarda las revisiones anteriores y el cambio es inmediato:

  ```bash
  gcloud run revisions list --service factored-prod-agent --region us-east4 --project bitcoders-factored-hackathon
  gcloud run services update-traffic factored-prod-agent --to-revisions=<revisión-anterior>=100 \
    --region us-east4 --project bitcoders-factored-hackathon
  ```

  Igual para `backend` y `frontend`.
- **Base de datos.** Las migraciones solo avanzan. Lo que hizo `0003` (cerrar casos duplicados) no vuelve; las copias de la base conservan el estado anterior si hiciera falta (recuperación a un instante en `prod`).
- **Secretos.** Se vuelve a una versión anterior desactivando la nueva: `gcloud secrets versions disable <n> --secret ...`.

## Lo que no está verificado

- **El despliegue mismo.** El `plan` y las pruebas locales no sustituyen a un `apply` real: nada de esto se ha aplicado todavía.
- **El camino por el balanceador** con esta versión: el certificado gestionado puede tardar en aprovisionarse tras cambios de dominio (en este despliegue el dominio no cambia).
- **`e2e.py` contra el borde.** Sus 11 escenarios pasaron contra el stack local y contra `prod` en el despliegue anterior; con `AGENT_URL` apuntando a `/agent` del balanceador es la forma prevista, no la que se probó.
