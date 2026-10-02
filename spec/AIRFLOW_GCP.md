# Airflow en GCP: comparativa de opciones y decisión

Estado: decisión tomada para el diseño del módulo `modules/airflow_vm`; el módulo está en construcción. Las cifras de precio son de fuentes públicas citadas abajo o estimaciones propias marcadas como tales; deben verificarse en la calculadora de Google Cloud antes de comprometer presupuesto.

## 1. Las opciones

| | A. Managed Service for Apache Airflow (Cloud Composer 3) | B. Airflow autohospedado en una VM (elegida) | C. Cloud Run Job + Cloud Scheduler (sin Airflow) | D. Cloud Workflows + varios Cloud Run Jobs |
|---|---|---|---|---|
| Qué es | Airflow administrado por Google. Es el mismo producto que Cloud Composer, renombrado | Airflow 3 en Compute Engine, con Docker Compose y `LocalExecutor` | El pipeline completo en un contenedor, lanzado a demanda o por horario | Una etapa por job, orquestadas por Workflows |
| Interfaz de Airflow, DAG y etapas visibles | Sí | Sí | No | No (hay una vista de ejecuciones de Workflows) |
| Reintentos y registros por etapa | Sí | Sí | No: un solo job | Sí por paso |
| Costo en reposo | **Alto**: no se puede apagar | Bajo: la VM se apaga; quedan los discos | ~0 | ~0 |
| Mantenimiento | Lo hace Google | **Lo hacemos nosotros** | Mínimo | Mínimo |
| Cambios al pipeline | Adaptar a su modelo de entorno | Ninguno: es el que ya se probó | Ninguno (ya existe) | **Rediseño**: los jobs no comparten disco, DuckDB tendría que pasar por Parquet en Cloud Storage |
| Control de versiones de DuckDB y dbt | Limitado a lo que Composer permite instalar | Total | Total | Total |

## 2. Costo

**Composer 3.** Cobra por DCU-hora (unidad de cómputo de vCPU, memoria y almacenamiento): US$0,06 por DCU-hora en `us-central1`, más almacenamiento de la base de datos de Airflow (US$0,000232877 por GiB-hora, mínimo 10 GiB) y transferencia de red. Un ambiente pequeño consume unas 9 DCU por hora, lo que da **unos US$400 al mes**, y soporta 50 DAGs y 18 tareas concurrentes. Hay descuentos por compromiso de uno o tres años, que no aplican a un hackathon. **No se puede detener**: se puede borrar y restaurar desde una instantánea, lo que simula apagarlo pero implica recrearlo cada vez. Los US$300 de crédito de bienvenida no alcanzan para un mes. Composer 3 tampoco es serverless: mantiene el clúster activo aunque no corra ninguna tarea.

**VM autohospedada (estimación propia, verificar):**

| Concepto | Orden de magnitud |
|---|---|
| `e2-standard-4` encendida todo el mes | ~US$98 |
| `e2-standard-4` con unas 20 horas de uso al mes | ~US$3 |
| Disco de datos de 100 GB y disco de arranque de 30 GB, aunque la VM esté apagada | ~US$13 |
| Cloud NAT | ~US$1 a 2 |
| Base de metadatos de Airflow | US$0 adicional: base y usuario propios dentro del Cloud SQL que ya existe |
| **Total con uso a demanda** | **~US$17 al mes** |

Con ese patrón de uso, la VM cuesta unas 20 veces menos que Composer, y se acerca al costo de una opción serverless.

## 3. Por qué no serverless

Los procesos del planificador, el procesador de DAGs y el triggerer deben estar siempre vivos. En Cloud Run se podrían mantener con instancia mínima 1 y CPU siempre asignada, pero se paga todo el tiempo y tres servicios cuestan más que la VM. GKE Autopilot tampoco apaga lo permanente y agrega el costo del clúster. Lo serverless real es **no usar Airflow**: opciones C y D de la tabla.

## 4. Decisión

**B, Airflow autohospedado en una VM `e2-standard-4`, apagada cuando no se usa**, porque:
- El requisito es contar con Airflow como orquestador (interfaz, DAG con etapas visibles, historial de corridas).
- El pipeline es **a demanda**, no una carga continua: encaja con una VM que se enciende para correr.
- Es lo que ya se probó de punta a punta (el DAG real en la imagen real, contra un PostgreSQL real, camino feliz y falla forzada).
- Con US$300 de crédito y un plazo de pocos días, Composer no cabe.

**Lo que se acepta a cambio:** el mantenimiento es nuestro (imagen, actualizaciones, espacio en disco). Se mitiga con: imagen versionada por commit y construida en CI, comprobación de espacio libre antes de cada corrida, copias diarias del disco y apagado automático nocturno.

**Cuándo se cambiaría de decisión:** si hubiera un equipo de datos con muchos DAGs y corridas continuas, Composer sería razonable; si Airflow dejara de ser un requisito, la opción C ya está funcionando (el Cloud Run Job `etl`).

## 5. Diseño de la VM

- **Máquina:** `e2-standard-4` (4 CPU, 16 GB), Debian 12, **Shielded VM** (arranque seguro, vTPM, monitoreo de integridad), **sin IP externa**.
- **Acceso:** Identity-Aware Proxy (túnel TCP) y OS Login; el firewall solo admite el rango de IAP, en los puertos 22 y 8080. La interfaz se abre con `gcloud compute start-iap-tunnel` hacia `localhost:8080`.
- **Salida a internet** (S3, OpenRouter, paquetes): Cloud NAT, porque la VM no tiene IP externa.
- **Componentes de Airflow:** cuatro contenedores separados (api-server, scheduler, dag-processor, triggerer) más un paso de migración de una sola vez, con `LocalExecutor`.
- **dbt:** en su propio entorno virtual dentro de la imagen, porque sus dependencias chocan con las restricciones de Airflow; DuckDB fijado en la misma versión en ambos entornos.
- **Datos:** disco aparte para el archivo de DuckDB y los registros, con copias diarias de 7 días.
- **Secretos:** contraseña de la base de metadatos, clave Fernet, secreto JWT de la API y contraseña del administrador, generados por Terraform y guardados en Secret Manager; la VM los lee con su cuenta de servicio.
- **Cuenta de servicio propia** con permisos mínimos: leer sus secretos, leer el repositorio de imágenes, escribir en el bucket del lago, y registros y métricas.
- **Apagado:** una política de horario apaga la VM cada noche (03:00 hora de Asunción) y un script la enciende y apaga a mano.
- **Despliegue:** una nueva etiqueta de imagen, no un `git pull` en la VM.

## 6. Fuentes

- [Cloud Composer 3: ¿realmente serverless?](https://medium.com/@shuvro_25220/cloud-composer-3-truly-serverless-5af001bc7930)
- [Precios de Managed Service for Apache Airflow (Cloud Composer)](https://cloud.google.com/composer/pricing)
- [Cloud Composer: optimización de costos](https://www.nops.io/blog/google-cloud-composer-cost-optimization-managed-airflow/)
- [Cloud Composer 3: guía y precios](https://www.cloudzone.io/blog/google-cloud-composer-guide)
- [Cloud Composer frente a Cloud Workflows](https://oneuptime.com/blog/post/2026-02-17-how-to-choose-between-cloud-composer-and-cloud-workflows-for-orchestrating-gcp-pipelines/view)
- [Escalado de ambientes de Composer](https://cloud.google.com/composer/docs/scale-environments)
- [Ahorro apagando un ambiente de Composer de desarrollo](https://medium.com/condenastengineering/automating-a-cloud-composer-development-environment-590cb0f4d880)

Nota sobre las fuentes: la página del producto y la de precios de Google se cargan de forma dinámica y el lector no pudo ver su contenido; las cifras de Composer salen de las fuentes secundarias de arriba y están referidas a `us-central1`. La región de este proyecto es `us-east4`, que puede tener un precio algo distinto.
