# Plan de verificacion y correccion para Claude Code

## Proposito y limites

Este documento convierte la revision de datos y pipeline del 28-09-2026 en
tareas verificables. No trata los resultados historicos como una evaluacion de
un agente ni autoriza cambios en Railway/produccion. No imprimir registros de
clientes, texto de conversaciones ni credenciales de S3. Antes de hacer
publico el repositorio, retirar o reemplazar el PDF del diccionario que contiene
credenciales del organizador y avisar al propietario para que las revoque o
rote; no intentar esa rotacion desde este repositorio.

La evidencia agregada esta en:

- `spec/evidence/2026-09-28-data-profile.json`: 663.086 filas leidas; las seis
  tablas no particionadas completas y cinco archivos espaciados por tabla
  particionada. No es una muestra aleatoria ni representativa de demanda.
- `spec/evidence/2026-09-28-ownership-verification.json`: segunda comprobacion
  independiente de relaciones de titularidad.

## Hechos comprobados

- El inventario contiene 7.671 CSV (5,35 GB). `data` es la base de datos y
  `bronze`, `silver`, `gold` son sus schemas previstos.
- En la muestra, cada `transactions.customer_id` y `transactions.product_id`
  existe y el producto pertenece al mismo cliente. Esta es una relacion apta
  para un modelo de movimientos del cliente.
- En 200/200 reclamos con `affected_product_id`, el titular del producto es
  distinto del `complaints.customer_id` (se repite en cada uno de cinco
  archivos). No usar ese campo para mostrar, inferir ni autorizar informacion
  de producto; la causa del defecto de fuente no esta determinada.
- Hay 7.044 tarjetas bloqueadas (4.932 credito y 2.112 debito), no 19.935.
  Las monedas observadas son USD, COP y ARS; no se observo MXN. Los transcriptos
  muestreados son en espanol, de pocas plantillas, y no validan portugues.
- Los campos `is_fraud` y `fraud_score` permanecen fuera de las herramientas
  del agente. Son etiquetas/campos del dataset, no evidencia de una senal
  operacional disponible en tiempo real.

## Decisiones de producto seguras

Construir inicialmente una experiencia de **consulta de movimientos propios y
creacion/seguimiento de reclamos simulados**. El backend obtiene la identidad
del cliente de una sesion de prueba confiable; nunca acepta un `customer_id`
elegido por el chat. No hay transferencias, reembolsos, bloqueos reales,
decisiones de credito ni deteccion de fraude. Escalar a humano ante ambiguedad,
autorizacion ausente, idioma no soportado, error de herramienta o solicitud de
accion financiera.

Los porcentajes historicos de resolucion/tiempo solo sirven como contexto
descriptivo; no son una linea base para afirmar exactitud, seguridad o ahorro
del agente.

## Correcciones priorizadas

### P0: seguridad, aislamiento y carga

1. Tratar el PDF con secretos como bloqueo de publicacion: preparar una version
   saneada o excluirlo del artefacto publico, confirmar rotacion externa y
   agregar controles para evitar nuevos secretos. No copiar las credenciales a
   issues, logs ni commits.
2. Corregir `s3_to_raw.py`: hoy `ON CONFLICT DO NOTHING` descarta una actualizacion
   de la misma clave y cuenta filas leidas como `rows_upserted`. Investigar si
   cada archivo es snapshot, delta o correccion antes de elegir politica. La
   implementacion debe conservar `source_key`, fecha de ingesta y hash/identidad
   de archivo; distinguir archivos, filas leidas, insertadas, actualizadas y
   omitidas. Probar una reejecucion identica y una fila modificada.
3. Alinear alcance: el DAG carga 13 tablas, pero dbt solo declara/modela cinco.
   O bien modelar y contratar las tablas necesarias, o bien reducir la carga al
   flujo elegido. No presentar una tabla bronze sin propietario, modelo ni uso.
4. Implementar aislamiento servidor a servidor: toda consulta debe filtrar por
   la identidad autenticada y comprobar pertenencia antes de devolver una
   transaccion o producto. Añadir pruebas de acceso cruzado rechazado.

### P1: contratos, publicacion y CI

1. Crear modelos gold explicitamente orientados a herramientas: movimientos
   propios pueden unir transaccion-producto por ambos `customer_id`; reclamos no
   deben unir detalles de `affected_product_id` hasta que se repare la fuente.
2. Añadir tests dbt de clave, nulos, valores, relaciones y una prueba singular
   de titularidad para transacciones. Para reclamos, medir/reportar el defecto
   conocido sin exponer la relacion insegura como valida.
3. Si un test falla, no marcar la corrida como publicable. Definir una estrategia
   de construccion/promocion que mantenga disponible el ultimo gold valido.
4. Corregir CI: el workflow apunta a `airflow/**` y `./airflow`, pero el Dockerfile
   real esta en `infra/airflow/Dockerfile` con contexto raiz. Validar tambien la
   imagen `infra/dbt/Dockerfile`.
5. Actualizar `README` y `spec/ARCHITECTURE.md` para separar lo implementado
   (Postgres, Airflow, dbt/Railway) de backend, agente, UI, trazas y proveedores
   aun planificados.

### P2: evaluacion y handoff

Crear un set de evaluacion propio, etiquetado y separado del entrenamiento,
con casos normales, ambiguos, no autorizados, inyeccion de prompt, error de
herramienta, expiracion y espanol/portugues. Comparar una base determinista con
el agente en precision de intencion, tasa de escalamiento correcto, aislamiento
de cliente y tasa de acciones prohibidas. Declarar que los textos historicos no
son un corpus de evaluacion suficiente.

## Secuencia de trabajo y aceptacion

1. Fijar el contrato de cada fuente y la politica de mutacion antes de editar
   SQL/Python. Registrar las decisiones en el PR.
2. Escribir pruebas de loader, dbt y autorizacion que fallen con el defecto
   actual; implementar el minimo cambio para hacerlas pasar.
3. Ejecutar, desde `data/dbt/`, `dbt parse`, `dbt build` y la prueba de una
   reejecucion idempotente contra una base de prueba. Ejecutar las pruebas del
   backend con dos clientes de fixture.
4. Verificar imagenes sin desplegar:
   `docker build -f infra/airflow/Dockerfile .` y
   `docker build -f infra/dbt/Dockerfile .`.
5. Antes de aplicar Railway, revisar `railway config plan`; aplicar solo con
   aprobacion explicita y conservar evidencia del despliegue y de las pruebas.

La correccion queda aceptada cuando las pruebas demuestran no filtracion entre
clientes, semantica de carga definida y medible, gold valido tras fallas de
calidad, CI sobre rutas reales, y documentacion que no promete componentes no
implementados.
