# Auditoria estatica — 2026-09-28

## Alcance ejecutado

Revision de todos los archivos versionados de pipeline, infraestructura, CI y
documentacion; sin acceso de escritura a S3, Postgres o Railway y sin ejecutar
un DAG, dbt contra una base, contenedores ni despliegues.

| Comprobacion | Resultado |
| --- | --- |
| Parseo AST de Python (`data/dags`, `infra`) | Pasa: 5 archivos |
| Parseo YAML del repositorio | Pasa: 7 archivos |
| Sintaxis de `infra/airflow/docker-entrypoint.sh` | Pasa |
| `git diff --check` | Pasa |
| `dbt parse` | Bloqueado: dbt 1.11.11 instalado sin adaptador `dbt-postgres` |

El `dbt parse` se intento con credenciales ficticias y `target-path` temporal;
no se conecto a una base de datos. El adaptador si esta declarado en
`infra/dbt/requirements.txt`, por lo que debe validarse dentro de la imagen dbt
o un entorno local que instale ese archivo antes de afirmar que los modelos
compilan.

## Hallazgos confirmados

1. La ingesta declara 13 tablas, mientras que dbt declara 5 fuentes, 5 modelos
   staging y 5 modelos gold. Ocho tablas cargadas no tienen contrato/modelo.
2. El workflow CI observa `airflow/**` y construye `./airflow`, rutas que no
   existen en este repositorio. El Dockerfile real es
   `infra/airflow/Dockerfile` y su contexto requerido es la raiz.
3. La carga bronze usa `ON CONFLICT ... DO NOTHING`; una correccion con la misma
   clave queda descartada y el contador `rows_upserted` representa filas leidas,
   no filas realmente insertadas. Esto se debe resolver con una semantica de
   fuente definida, no con un `DO UPDATE` ciego.
4. Los documentos del organizador PDF estan versionados. Uno contiene secretos
   de acceso del organizador; su eliminacion/reemplazo y rotacion externa son
   un bloqueo de publicacion, descrito sin reproducir el secreto en
   `spec/CLAUDE_CODE_VERIFICATION_AND_FIX_PLAN.md`.
5. Backend, agente y frontend solo contienen contratos README. Las secciones de
   arquitectura que los describen como servicios ejecutables deben marcarse
   como planificadas hasta su implementacion y prueba.

## Perfilado S3 asociado

El perfilado de solo lectura ya finalizado esta en
`2026-09-28-data-profile.json` y la comprobacion independiente de titularidad
en `2026-09-28-ownership-verification.json`. Cubrio las seis tablas no
particionadas completas y cinco archivos espaciados por cada tabla
particionada (663.086 filas); no es un censo de todas las particiones ni una
muestra aleatoria.

## Limites pendientes, deliberadamente no ejecutados

Quedan fuera de esta auditoria estatica: compilacion dbt con el adaptador,
pruebas de loader contra Postgres, reejecucion idempotente, pruebas de
autorizacion, builds Docker y cualquier accion Railway. La secuencia y criterios
para esas verificaciones estan en `../CLAUDE_CODE_VERIFICATION_AND_FIX_PLAN.md`.
