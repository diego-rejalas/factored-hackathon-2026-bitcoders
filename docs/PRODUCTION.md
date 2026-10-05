# Ruta a producción

[Índice](README.md) · [Arquitectura](ARCHITECTURE.md) · [Seguridad](SECURITY.md) · [Evaluación](EVALUATION.md) · [Criterios](CRITERIA.md)

*Lo que haría falta para llevar esto a un banco de verdad, dicho sin adornos. Es un prototipo sobre datos sintéticos, no una implementación de producción. Cada sección separa lo que **existe hoy** de lo que **falta**; lo marcado como propuesta no está decidido ni implementado.*

## Capacidad y límites

**Hoy**
- **Cloud Run:** `backend` y `agent` con 1 instancia mínima en `prod` y 3 como máximo por defecto (`max_instances`), 1 CPU cada una. El frontend escala a cero.
- **Cloud SQL (`prod`):** `db-custom-2-7680` (2 CPU, 7,5 GB), 50 GB, una sola instancia sin réplica. Cada servicio abre su propio grupo de conexiones con asyncpg, con el tamaño por defecto de la biblioteca.
- **Pipeline:** una VM `e2-standard-4` que procesa las 23,5 millones de filas del dataset en unos minutos y se apaga de noche. Es un snapshot cerrado: no hay carga continua que dimensionar.
- **Modelo de lenguaje:** una llamada de clasificación por mensaje y otra de redacción por caso resuelto. Con `claude-haiku-4.5` midieron p50 de 1,2 s y p95 de 1,7 s por llamada, y 0,0005 USD por caso ([Evaluación](EVALUATION.md)).

**Falta**
- **Una prueba de carga.** No se midió cuántos clientes simultáneos soporta nada. La evaluación corrió con concurrencia 4 en local; no dice nada sobre Cloud Run.
- **Dimensionar las conexiones.** Con 3 instancias por servicio y el tamaño por defecto del grupo, la base se podría quedar sin conexiones antes de que Cloud Run se quede sin instancias.
- **Límite de tasa del modelo.** Un pico de mensajes se convierte en un pico de llamadas pagadas a un tercero. Hoy solo Cloud Armor limita por IP.
- **Alta disponibilidad de la base.** Una instancia sin réplica es un punto único de falla.

## Monitoreo

**Hoy**
- Cada solicitud lleva `X-Request-ID` y se registra en JSON, que Cloud Logging recoge.
- `agent.trace_log` guarda cada paso del agente con su resultado y latencia, sin texto del cliente. `GET /admin/agent-metrics` y la consola agregan resultados, contención, latencia p50 y p95, intenciones, idiomas y el resultado de la verificación.
- `ops.etl_runs` registra cada corrida del pipeline y `GET /meta/data` la expone. La consola muestra la frescura.
- `GET /ready` comprueba la base.

**Falta**
- **Alertas.** Nada avisa si el agente falla, si sube la latencia o si el pipeline no corrió. Tampoco hay presupuesto con alerta de costo (está en el pendiente de `infra/gcp/README.md`).
- **Sondas de disponibilidad y objetivos de servicio** (por ejemplo, un porcentaje de respuestas sin `unavailable`).
- **Seguimiento de calidad en producción.** La evaluación es offline. En producción haría falta muestrear conversaciones reales, medir cuántas se escalan o se abandonan y revisar los rechazos de las comprobaciones del borrador del modelo (`llm_rejected_*` en la traza).
- **Registro de auditoría inmutable** de las acciones del especialista. Hoy los eventos de un caso solo crecen, pero están en la misma base que la aplicación.

## Controles de acceso

**Hoy** (el detalle está en [Seguridad](SECURITY.md))
- Sesión con JWT firmado, con vencimiento y rol. La identidad sale siempre del token, y toda consulta se filtra por el cliente.
- El backend es privado; un rol de base por servicio; Cloud Armor delante; despliegue sin llaves guardadas.

**Falta**
- **Identidad real.** El chat acepta cliente y número de documento. En un banco haría falta un proveedor de identidad con segundo factor. El acceso del especialista es un usuario y una clave en un secreto manual, con límite de intentos por proceso (no compartido entre instancias).
- **Contenedores sin root** en `backend`, `agent` y `frontend`, e imágenes base con vulnerabilidades sin parche publicado.
- **Aprobación humana del despliegue a `prod`.** El entorno de GitHub `prod` no tiene revisores obligatorios.
- **Rotación de secretos** (la clave de sesión, las del modelo y las del origen de datos) y separación de funciones entre quien despliega y quien aplica permisos.

## Retención de datos

**Hoy no hay política aplicada.** Qué se guarda y dónde:

| Dato | Dónde | Contiene texto del cliente | Retención hoy |
|---|---|---|---|
| Conversaciones (lo que escribió el cliente y lo que se le respondió) | `agent.conversation_messages` | **Sí** | Ninguna: se conserva siempre |
| Casos, eventos y traspasos | `app.disputes` y `app.dispute_events` | Sí, el mensaje recortado a 300 caracteres dentro del traspaso | Ninguna |
| Traza de pasos del agente | `agent.trace_log` | **No**, por diseño | Ninguna |
| Registros de las aplicaciones | Cloud Logging | No incluyen el texto del chat | La del servicio por defecto |
| Datos del pipeline (bronze y silver) | Cloud Storage, Parquet | Sintéticos | Se pasan a almacenamiento más barato con el tiempo; no se borran |
| Copias de la base | Cloud SQL, con recuperación a un instante en `prod` | Todo lo anterior | La del servicio |

**Propuesta, sin decidir** (la fija el banco, no el equipo): conversaciones por un plazo corto y acotado, con borrado automático; casos y traspasos por el plazo que exija la normativa de reclamos; y un mecanismo para atender el borrado a pedido del cliente. Cualquiera de las tres exige un trabajo programado que hoy no existe. Las copias de la base conservan lo borrado hasta que expiran.

**Datos que salen del sistema.** Con una clave de modelo, el mensaje del cliente y los hechos de la transacción viajan a OpenRouter y al proveedor del modelo. En un banco real eso requeriría un acuerdo de tratamiento de datos, una región acordada y, probablemente, enmascarar identificadores antes de enviarlos. Hoy el agente funciona también sin modelo.

## Separar la base de la aplicación de la del pipeline

**Hoy** todo vive en una instancia y una base (`data`): `gold` lo publica el pipeline, `app` lo escribe el backend y `agent` lo escribe el agente. Hay un rol por servicio y cada uno solo ve lo suyo.

**Por qué conviene separarlas.** El pipeline reescribe `gold` completo en cada corrida; una carga pesada o un error ahí comparte CPU, conexiones y copias con las escrituras de los clientes. Y un incidente en uno obliga a restaurar el otro. **Propuesta:** una base transaccional para `app` y `agent` (con réplica) y otra de consulta para `gold`, que el pipeline publique y el backend lea. El costo es una instancia más y un lugar más donde configurar red y roles.

## Despliegue y recuperación

**Hoy:** todo es Terraform y el CI construye y escanea las imágenes; los `apply` de `prod` los corre una persona. La base tiene recuperación a un instante en `prod`.

**Falta:** despliegue gradual con vuelta atrás (hoy se aplica y se espera), una **restauración probada** (se configuró la recuperación, no se ensayó), y un plan para cuando el proveedor del modelo no responda más de unos minutos (el agente ya cae a texto fijo y no se rompe, pero la calidad baja: ver el 82 % contra el 99 % en portugués de la [Evaluación](EVALUATION.md)).

## Qué se haría primero

1. Identidad real con segundo factor y contenedores sin root.
2. Alertas, sondas y un presupuesto con aviso.
3. Una política de retención acordada con el banco, y el trabajo que la aplique.
4. Una prueba de carga y el dimensionamiento de conexiones.
5. Separar la base de la aplicación de la del pipeline.
6. Revisión de las conversaciones reales y del rendimiento del modelo, antes de ampliar el alcance a otros flujos.
