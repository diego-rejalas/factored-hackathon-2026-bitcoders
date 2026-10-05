# Evaluación

[Índice](README.md) · [Workflow](WORKFLOW.md) · [Datos](DATA.md) · [Ruta a producción](PRODUCTION.md) · [Criterios](CRITERIA.md)

*Qué se midió, cómo, con qué resultados y qué no se puede concluir. Es una medición **offline** sobre casos que el equipo generó; no es una medición en producción ni una proyección de ahorro.*

## Resumen

| Pregunta | Respuesta | Dónde |
|---|---|---|
| ¿Un modelo clasifica la intención mejor que las palabras clave? | **Sí, con mucho margen sobre texto que no usa esas palabras**: 100 % (228 de 228) contra 49,1 % en el conjunto ciego. Sobre 40 casos adversariales hechos a mano, 97,5 % contra 87,5 %, una diferencia que no es significativa a ese tamaño | [Componente](#1-el-componente-clasificación-de-intención) |
| ¿El sistema completo cumple la política? | En la primera corrida: **99,2 %** de 384 disputas con el modelo y **90,1 %** sin él. Tras corregir lo que se encontró: 549 de 549 con el modelo y 90,6 % de las disputas sin él | [Sistema](#2-el-sistema-completo-de-punta-a-punta) |
| ¿Resolvió algo que debía pasar a una persona? | **0 de 372** casos. Con esa muestra, el riesgo real podría llegar hasta el 1 % | [Resultados inseguros](#resultados-inseguros) |
| ¿Qué encontró la evaluación? | **Ocho defectos reales**, todos corregidos con pruebas, entre ellos un error 500 del backend que existía desde el principio | [Hallazgos](#3-lo-que-se-encontró) |
| ¿Cuánto de esto es evidencia independiente? | **Menos de lo que parece**: el 100 % posterior a las correcciones se mide sobre los mismos casos que las originaron. Lo independiente es el conjunto ciego de intenciones y el tercer conjunto de fraude | [Límites](#4-límites) |

## Cómo se evaluó

**Qué es el "componente aprendido".** El agente decide con código; el modelo hace tres cosas: clasificar la intención de un mensaje, dar una segunda lectura de fraude que solo puede sumar cautela, y redactar la respuesta de un caso ya resuelto. El componente evaluado contra una línea base es la **clasificación de intención**: `anthropic/claude-haiku-4.5` (por OpenRouter) frente a las palabras clave en español y portugués que usa el agente sin modelo. No se entrenó ningún modelo.

**Por qué no hay conjunto de entrenamiento ni particiones.** No hay nada que entrenar, así que no hay fuga entre entrenamiento y prueba. La separación que importa es otra: los conjuntos de prueba se escribieron **antes** de ejecutar nada y ni el prompt del modelo ni la lista de palabras clave se tocaron para ellos. Lo que se ajustó después se validó, cuando fue posible, con un conjunto nuevo que no se había visto.

**Etiquetas sin fuga.** `is_fraud` y `fraud_score` no existen en `gold` ni en los casos. El resultado esperado de cada caso se deriva de la política (estado de la transacción y monto), restablecida de forma independiente en `agent/eval/fixture.py`, no se lee del agente. Los mensajes los parafrasea un modelo distinto del clasificador (`openai/gpt-4o-mini`) a partir de los datos de la transacción, sin decirle su estado: un cliente no lo conoce.

**Datos.** Todo es inventado por el equipo y está rotulado así:

| Conjunto | Casos | Cómo se hizo |
|---|---:|---|
| Intenciones, ciego | 228 | Un modelo ajeno al clasificador escribe mensajes por intención, en español y portugués, la mitad **sin** las palabras habituales de banca. Se revisaron los 241 uno por uno y se quitaron 13 dudosos (`intent_blind.excluded.json`) |
| Intenciones, adversarial | 40 | A mano: inyecciones, pedidos de datos ajenos, jerga, errores de tipeo, ruido, dos idiomas mezclados |
| Fraude, conjunto 2 y 3 | 36 y 34 | Generados después de ver los primeros resultados, para validar las correcciones; 14 y 15 dudosos quitados (`fraud_fresh*.excluded.json`). Ningún mensaje se repite entre conjuntos |
| Punta a punta | 549 | 12 clientes y 96 transacciones inventados con semilla (`fixture.py`); 384 mensajes que declaran el monto, más aclaraciones, fraude, fuera de alcance, saludos, inyecciones, datos ajenos, datos inexistentes, sesión vencida y fallo de herramienta |

**Métricas.** Las del reto: resolución automática segura (y qué parte de lo en alcance se intentó), contención, calidad del escalamiento, resultados inseguros con su denominador, y latencia y costo. Cada proporción lleva su intervalo de Wilson al 95 %; la comparación entre dos clasificadores sobre los mismos casos usa la prueba exacta de McNemar. Una proporción sin denominador se informa como "no definida", no como cero. El umbral de USD 500 es una decisión de producto y el oráculo lo aplica inclusivo.

Todo número de este documento se recalcula con los archivos por caso de `agent/eval/results/`. Cómo repetirlo: `agent/eval/README.md`.

## 1. El componente: clasificación de intención

Cuatro etiquetas: disputa, estado de un caso, saludo y fuera de alcance.

| | Palabras clave | Modelo | Casos |
|---|---:|---:|---:|
| **Conjunto ciego**, exactitud | 49,1 % (IC 42,7 a 55,6) | **100 %** (IC 98,3 a 100) | 228 |
| Macro F1 | 0,479 | 1,000 | |
| Español / portugués | 53,9 % / 44,3 % | 100 % / 100 % | 115 / 113 |
| Mensajes naturales / **sin jerga bancaria** | 52,3 % / 42,7 % | 100 % / 100 % | 153 / 75 |
| *Por etiqueta:* disputa / estado / saludo / fuera de alcance | 61,7 / **13,3** / 59,0 / 65,0 % | 100 % en las cuatro | 47 / 60 / 61 / 60 |
| **Conjunto adversarial**, exactitud | 87,5 % (IC 73,9 a 94,5) | 97,5 % (IC 87,1 a 99,6) | 40 |

- En el conjunto ciego, **116 casos los acierta solo el modelo y ninguno solo las palabras clave** (McNemar exacto, p menor que 0,001).
- En el adversarial: 5 los acierta solo el modelo y 1 solo las palabras clave (p = 0,22): **con 40 casos no se puede afirmar diferencia**.
- El modelo falló un caso adversarial: `?` lo etiquetó como saludo y la referencia dice fuera de alcance.
- Las palabras clave fallan sobre todo en **estado del caso** (13 %): los clientes preguntan "cómo va lo que reporté" sin decir "caso" ni "reclamo".
- La llamada al modelo tarda p50 1,2 s y p95 1,4 s, y cuesta 0,00032 USD por mensaje clasificado.

**Cómo leerlo.** El 100 % es un techo, no una promesa: el límite inferior del intervalo es 98,3 %, los mensajes los escribió otro modelo de lenguaje, y la tarea es fácil para un modelo. Y la línea base **no se reforzó**: es la lista de palabras clave sin cambios. Una lista más larga cerraría parte de la brecha; lo que se midió es "el modelo contra estas reglas", no "el modelo contra las mejores reglas posibles".

## 2. El sistema completo, de punta a punta

Se corrió contra el backend y la base reales del stack local, en dos configuraciones: **sin modelo** (palabras clave, reglas y textos fijos) y **con modelo** (clasifica, da la segunda lectura de fraude y redacta, como con una clave de OpenRouter). Cada caso es una conversación nueva. Los casos que chocarían entre sí (mismo cliente y transacción) corren en rondas con la tabla de casos vaciada entre una y otra.

### Primera corrida, antes de cualquier corrección (la medición retenida)

| Categoría | Casos | Sin modelo | Con modelo |
|---|---:|---:|---:|
| Disputa con monto declarado | 384 | 90,1 % | **99,2 %** |
| Aclaración (mensaje sin monto) | 31 | 61,3 % | 96,8 % |
| Datos inexistentes | 24 | 100 % | 100 % |
| Fuera de alcance | 24 | 62,5 % | 100 % |
| Saludo | 12 | 58,3 % | 100 % |
| **Fraude** | 24 | 83,3 % | **45,8 %** |
| Inyección de instrucciones | 12 | 100 % | 100 % |
| Pedir datos de otro cliente | 12 | 100 % | 100 % |
| Elegir en la app una transacción ajena | 8 | 100 % | 100 % |
| Sesión vencida (debe dar 401) | 6 | 100 % | 100 % |
| Fallo del backend (debe avisar y no cambiar nada) | 12 | 100 % | 100 % |

### Corrida final, después de las correcciones

Mismos casos, con una excepción: el oráculo de **fuera de alcance** pasó de "escalar" a "declinar" (sección 3, defecto 5).

| Categoría | Casos | Sin modelo | Con modelo |
|---|---:|---:|---:|
| Disputa con monto declarado | 384 | 90,6 % | **100 %** |
| Aclaración | 31 | 61,3 % | 100 % |
| Fraude | 24 | 100 %\* | 100 %\* |
| Fuera de alcance (debe declinar) | 24 | 62,5 % | 100 % |
| Saludo | 12 | 58,3 % | 100 % |
| Datos inexistentes, inyección, datos ajenos, transacción ajena, sesión vencida, fallo del backend | 74 | 100 % | 100 % |
| **Total** | **549** | | **549 de 549** (IC 99,3 a 100) |

\* Esas palabras de fraude se escribieron a partir de estos mismos casos: es una prueba de regresión, no una medición independiente. La independiente está en la sección 3.

### Métricas del reto (corrida final, 384 disputas con monto)

De las 384, 92 son de una transacción que la política deja resolver sola y 292 de una que debe ir a una persona.

| Métrica | Sin modelo | Con modelo |
|---|---:|---:|
| **Resolución automática segura**, sobre lo que la política deja automatizar | 87,0 % (80/92; IC 78,6 a 92,4) | **100 %** (92/92; IC 96,0 a 100) |
| Sobre todos los casos en alcance | 20,8 % (80/384) | 24,0 % (92/384) |
| Se intentó automatizar / de eso, correcto | 20,8 % / 100 % | 24,0 % / 100 % |
| **Contención** (terminan sin transferir) / de eso, correcto | 27,1 % / 76,9 % | 24,0 % / 100 % |
| **Escalamiento**: se transfirió cuando debía | 91,8 % (268/292; IC 88,1 a 94,4) | 100 % (292/292; IC 98,7 a 100) |
| Transferencias perdidas / innecesarias | 0 de 292 / 0 de 92 | 0 de 292 / 0 de 92 |
| El motivo del traspaso coincide con la política | 100 % | 100 % |

La contención sola no prueba nada: 24 % es baja a propósito, porque el 76 % de las disputas del fixture deben ir a una persona (cobros ya aprobados o sobre USD 500).

### Resultados inseguros

| Qué | Con y sin modelo | Intervalo superior (95 %) |
|---|---:|---:|
| Resolvió solo algo que la política manda a una persona o que no debía resolver | **0 de 372** | 1,0 % |
| Mostró datos de otro cliente | 0 de 20 | **16,1 %** |
| Prometió dinero o plazos en una respuesta | 0 de 543 | 0,7 % |

**Cero fallos en una muestra pequeña no significa cero riesgo.** Con 20 casos de acceso a datos ajenos, lo único que se puede decir es que el riesgo es probablemente bajo, no que es nulo. Que no hubiera fallos se debe a controles de código (titularidad en el backend, la política en el guardrail, las comprobaciones del borrador), no a que el modelo "se porte bien".

### Idioma

| Disputas con monto | Sin modelo | Con modelo |
|---|---:|---:|
| Español | 98,4 % (189/192) | 100 % (192/192) |
| Portugués | **82,8 %** (159/192) | 100 % (192/192) |

Sin modelo, el portugués rinde claramente peor: la lista de palabras clave tiene menos formas en ese idioma. No se comparó por segmento de cliente (país): los clientes del fixture son inventados y no hay muestra por país.

### Calidad del traspaso

| Campo | Primera corrida | Final |
|---|---:|---:|
| solicitud, preguntas abiertas, motivo y límite de política | 100 % | 100 % |
| acciones tomadas e id del caso | 86,7 % | 100 % |
| evidencia (la transacción candidata) | 83,3 % | 91,8 % |
| **hechos verificados** | **0 %** | **100 %** |

La evidencia falta cuando no hay una transacción identificada (un fraude que no nombra ninguna): es correcto que no la haya.

### Eficiencia

Medida con el stack local y concurrencia 4, sobre las 384 disputas. **No es la latencia de Cloud Run.**

| | Sin modelo | Con modelo |
|---|---:|---:|
| Latencia p50 / p95 | 0,30 s / 0,39 s | 1,42 s / 4,17 s |
| Costo por caso (549 casos, todas las categorías) | 0 | **0,00067 USD** |
| Costo por caso resuelto solo | 0 | **no mayor que 0,0040 USD** |
| Tokens | 0 | 277.492 de entrada y 18.119 de salida, 1.153 llamadas |

El costo por caso resuelto es una **cota superior**: divide el gasto de toda la corrida (incluidas las categorías que no se resuelven) entre las 92 resoluciones correctas. Es el costo de las llamadas al modelo; no incluye la infraestructura. La segunda lectura de fraude suma una llamada por mensaje (corre a la vez que la clasificación, así que no añade espera) y subió el costo de 0,00052 a 0,00067 USD por caso.

## 3. Lo que se encontró

Ocho defectos reales. Ninguno dejó pasar algo inseguro, y todos se corrigieron con pruebas que fallan sin la corrección.

| # | Defecto | Cómo se encontró | Corrección |
|---|---|---|---|
| 1 | **Un año se leía como monto.** En "10 de junho de 2026 … 27.65 USD" el agente tomaba 2026 como el monto | La evaluación (3 de 384 casos) | Una fecha escrita ya no cuenta como monto; un monto que se parece a un año (`cobro de 2026`) sigue siéndolo |
| 2 | **Fraude sin las palabras habituales no escalaba.** "Alguien usó mi tarjeta sin mi permiso" o "me hackearon" se trataban como disputa y el agente pedía aclarar: 13 de 24 casos con modelo | La evaluación | Más frases en la lista, y una segunda lectura con el modelo que **solo puede sumar cautela** (un "sí" pasa el caso a una persona; un "no" o un fallo dejan la lista como estaba) |
| 3 | **El traspaso no llevaba hechos verificados** (0 %) ni el mensaje del cliente | La evaluación | Lleva la transacción confirmada por el backend, el monto efectivo, la fecha, la regla aplicada y el mensaje (300 caracteres); la consola lo muestra |
| 4 | **`GET /me/transactions?days=N` devolvía 500 siempre.** Cualquier mensaje con "ayer", "ontem" o "hace 3 días" acababa en `unavailable` | Un caso de la evaluación que fallaba igual en las dos corridas. Primero se tomó por un fallo transitorio, y no lo era | Había que tipar los parámetros del SQL. Existía desde el principio: las pruebas con el almacén en memoria nunca ejecutaban ese SQL. Ahora hay una prueba contra PostgreSQL real |
| 5 | **Una pregunta fuera de alcance ("¿cuál es el clima?") respondía que "este caso fue escalado y una persona continúa desde acá"**, sin que existiera caso ni traspaso: nadie lo iba a atender | El usuario, probando | Se declina con un texto fijo en su idioma (`outcome: declined`), sin caso ni afirmación falsa |
| 6 | **Un saludo mostraba la etiqueta "resuelto automáticamente"** | El usuario | La etiqueta solo aparece si hay un caso o una escalación |
| 7 | **El idioma se reconocía por diez palabras largas**: "Quero aumentar o limite do cartão" se respondía en español | Al escribir una prueba | Letras y palabras que solo existen en portugués |
| 8 | **`escalate` pisaba cualquier estado**: un nuevo reporte podía deshacer el cierre de un especialista | Al documentar la API | Un caso `in_progress` o `closed` responde 409 y no cambia; uno `open`, `auto_resolved` o `escalated` sigue escalando |

### Validación de las correcciones de fraude

| Conjunto | Sin modelo | Con modelo, antes | Con modelo, después |
|---|---:|---:|---:|
| Conjunto 2 (36): validación de la primera corrección | 47,2 % | 47,2 % | 80,6 % (29/36; IC 65,0 a 90,2) |
| **Conjunto 3 (34): independiente**, escrito después de la segunda corrección | 55,9 % (19/34; IC 39,5 a 71,1) | 55,9 % | **100 %** (34/34; IC 89,8 a 100) |

Los fallos que quedaban en el conjunto 2 (una contraseña filtrada, un enlace de phishing, una billetera perdida) eran mensajes que el clasificador llamaba "fuera de alcance". La segunda corrección extendió la segunda lectura a esos mensajes; como eso se diseñó mirando el conjunto 2, la medición independiente es el conjunto 3.

## 4. Límites

- **Los datos son generados por el equipo.** Ningún mensaje viene de un cliente real. El generador es otro modelo de lenguaje: comparte sesgos de estilo con el clasificador, y que el modelo acierte el 100 % indica que la tarea es fácil para él, no que lo sea en producción.
- **La depuración de los conjuntos la hizo quien hizo la evaluación**, un asistente de IA que trabaja con el equipo, leyendo cada mensaje. Ningún tercero validó las etiquetas.
- **El 100 % de la corrida final no es independiente.** Los 549 casos son los mismos con los que se encontraron y corrigieron los defectos 1 a 4. Cuenta como prueba de regresión. La evidencia independiente es: el conjunto ciego de intenciones (el sistema no se tocó para él), el conjunto 3 de fraude, y los defectos 5 y 6, que encontró una persona escribiendo en el chat y que la evaluación no habría visto: su oráculo esperaba "escalar" para lo fuera de alcance.
- **El oráculo lo escribió quien escribió la política.** Un malentendido de la política estaría en ambos lados. El conjunto adversarial se escribió conociendo la lista de palabras clave.
- **El fixture tiene pocas transacciones distintas.** Solo 23 de 96 son resolubles por sí solas, y cada una tiene 4 frases. Hay variedad de redacción, no de casos, y las frases de una misma transacción no son independientes: los intervalos de Wilson **subestiman** la incertidumbre.
- **Un solo modelo.** No se comparó con otros (el valor por defecto del código es `gpt-4o-mini`; la evaluación usó `claude-haiku-4.5`). Tampoco se ajustó el prompt de clasificación.
- **La línea base no se reforzó**, como se dijo arriba.
- **Una sola configuración de carga**: local, concurrencia 4, un cliente de prueba por caso.
- **La segunda lectura de fraude no se midió contra falsos positivos fuera de la evaluación.** Dentro de ella, ninguna de las 92 disputas que la política deja resolver solas se escaló de más. Con mensajes reales, un modelo puede escalar de más; eso cuesta una escalación, no un riesgo, pero hay que vigilarlo.
- **Es medición offline.** No hay proyección de ahorro de negocio ni se presenta ninguna mejora como medida en producción.
