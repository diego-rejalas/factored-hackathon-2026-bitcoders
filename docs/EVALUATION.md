# Evaluación

[Índice](README.md) · [Workflow](WORKFLOW.md) · [Datos](DATA.md) · [Criterios](CRITERIA.md)

*Qué se midió, cómo, con qué resultados y qué no se puede concluir. Es una medición **offline** sobre casos que el equipo generó; no es una medición en producción ni una proyección de ahorro.*

## Resumen

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Un modelo clasifica la intención mejor que las palabras clave? | **Sí, con mucho margen sobre texto que no usa esas palabras**: 100 % (228 de 228) contra 49,1 % en el conjunto ciego. Sobre casos adversariales hechos a mano, 97,5 % contra 87,5 %, una diferencia que no es significativa con 40 casos | [Componente](#1-el-componente-clasificación-de-intención) |
| ¿El sistema completo cumple la política? | **99,2 %** en los 384 casos de disputa con el modelo y **90,1 %** sin él. La política, que es código, no cambia entre los dos: cambia que sin modelo no se entienden mensajes sin palabras clave | [Sistema](#2-el-sistema-completo-de-punta-a-punta) |
| ¿Resolvió algo que debía pasar a una persona? | **0 de 396** casos que la política manda a una persona. Con ese tamaño de muestra, el riesgo real podría llegar hasta el 1 % | [Resultados inseguros](#resultados-inseguros) |
| ¿Qué encontró la evaluación? | **Tres defectos reales**, corregidos: un año leído como monto, frases de fraude sin escalar, y un traspaso sin hechos verificados | [Hallazgos](#3-lo-que-encontró-la-evaluación) |

## Cómo se evaluó

**Qué es el "componente aprendido".** El agente decide con código; el modelo hace dos cosas: clasificar la intención de un mensaje y redactar la respuesta de un caso ya resuelto. El componente evaluado contra una línea base es la **clasificación de intención**: `anthropic/claude-haiku-4.5` (por OpenRouter) frente a las palabras clave en español y portugués que usa el agente sin modelo. No se entrenó ningún modelo.

**Por qué no hay conjunto de entrenamiento ni particiones.** No hay nada que entrenar, así que no hay fuga entre entrenamiento y prueba. La separación que importa es otra: los conjuntos de prueba se escribieron **antes** de ejecutar nada y ni el prompt del modelo ni la lista de palabras clave se tocaron para ellos. Lo único que se ajustó después fueron las correcciones de la sección 3, y esas se validaron con un conjunto nuevo, no con el que las originó.

**Etiquetas sin fuga.** `is_fraud` y `fraud_score` no existen en `gold` ni en los casos. El resultado esperado de cada caso se deriva de la política (estado de la transacción y monto), restablecida de forma independiente en `agent/eval/fixture.py`, no se lee del agente. Los mensajes los parafrasea un modelo distinto del clasificador (`openai/gpt-4o-mini`) a partir de los datos de la transacción, sin decirle su estado: un cliente no lo conoce.

**Datos.** Todo es inventado por el equipo y está rotulado así:

| Conjunto | Casos | Cómo se hizo | Etiqueta |
|---|---:|---|---|
| Intenciones, ciego | 228 | Un modelo ajeno al clasificador escribe mensajes por intención, en español y portugués, la mitad **sin** las palabras habituales de banca. Los 241 se revisaron uno por uno y se quitaron 13 dudosos (`intent_blind.excluded.json`) | Por construcción |
| Intenciones, adversarial | 40 | A mano: inyecciones, pedidos de datos ajenos, jerga, errores de tipeo, ruido, dos idiomas mezclados | A mano |
| Fraude, nuevo | 40 | Generado después de ver el primer resultado, para validar la corrección. Se revisaron uno por uno y se quitaron 9 dudosos (`fraud_fresh.excluded.json`) | Por construcción |
| Punta a punta | 549 | 12 clientes y 96 transacciones inventados con semilla (`fixture.py`); 384 mensajes que declaran el monto, más aclaraciones, fraude, fuera de alcance, saludos, inyecciones, datos ajenos, datos inexistentes, sesión vencida y fallo de herramienta | Oráculo de la política |

**Métricas.** Las del reto: resolución automática segura (y qué parte de lo en alcance se intentó), contención, calidad del escalamiento (se pierden o sobran transferencias, y qué lleva el traspaso), resultados inseguros con su denominador, y latencia y costo. Cada proporción lleva su intervalo de Wilson al 95 %; la comparación entre dos clasificadores sobre los mismos casos usa la prueba exacta de McNemar. Una proporción sin denominador se informa como "no definida", no como cero.

**Umbral.** USD 500 es una decisión de producto, no un hallazgo de los datos (ver [Workflow](WORKFLOW.md)). El oráculo lo aplica inclusivo: 500,00 escala.

Todo número de este documento se recalcula con los archivos por caso de `agent/eval/results/`. Cómo repetirlo: `agent/eval/README.md`.

## 1. El componente: clasificación de intención

Cuatro etiquetas: disputa, estado de un caso, saludo y fuera de alcance.

| | Palabras clave | Modelo | Casos |
|---|---:|---:|---:|
| **Conjunto ciego**, exactitud | 49,1 % (IC 42,7 a 55,6) | **100 %** (IC 98,3 a 100) | 228 |
| Macro F1 | 0,479 | 1,000 | |
| Español | 53,9 % | 100 % | 115 |
| Portugués | 44,3 % | 100 % | 113 |
| Mensajes naturales | 52,3 % | 100 % | 153 |
| Mensajes **sin jerga bancaria** | 42,7 % | 100 % | 75 |
| *Por etiqueta:* disputa / estado / saludo / fuera de alcance | 61,7 / **13,3** / 59,0 / 65,0 % | 100 % en las cuatro | 47 / 60 / 61 / 60 |
| **Conjunto adversarial**, exactitud | 87,5 % (IC 73,9 a 94,5) | 97,5 % (IC 87,1 a 99,6) | 40 |

- En el conjunto ciego, de 228 casos, **116 los acierta solo el modelo y ninguno solo las palabras clave** (McNemar exacto, p menor que 0,001).
- En el adversarial: 5 los acierta solo el modelo y 1 solo las palabras clave (p = 0,22): **con 40 casos no se puede afirmar diferencia**.
- El modelo falló un caso adversarial: el mensaje `?` lo etiquetó como saludo y la referencia dice fuera de alcance.
- Las palabras clave fallan sobre todo en **estado del caso** (13 %): los clientes preguntan "cómo va lo que reporté" sin decir "caso" ni "reclamo".
- Latencia de la llamada al modelo: p50 1,22 s y p95 1,72 s. Costo: 0,000322 USD por mensaje clasificado (0,0735 USD por los 228).

**Cómo leerlo.** El 100 % es un techo, no una promesa: el límite inferior del intervalo es 98,3 %, los mensajes los escribió otro modelo de lenguaje, y la tarea es fácil para un modelo. Y la línea base **no se reforzó**: es la lista de palabras clave sin cambios. Una lista más larga cerraría parte de la brecha; lo que se midió es "el modelo contra estas reglas", no "el modelo contra las mejores reglas posibles".

## 2. El sistema completo, de punta a punta

Se corrió contra el backend y la base reales del stack local, en dos configuraciones: **sin modelo** (palabras clave, reglas y textos fijos) y **con modelo** (clasifica y redacta, como con una clave de OpenRouter). Cada caso es una conversación nueva. Los casos que chocarían entre sí (mismo cliente y transacción) corren en rondas con la tabla de casos vaciada entre una y otra.

**Primera corrida, antes de las correcciones** (esta es la medición retenida):

| Categoría | Casos | Sin modelo | Con modelo |
|---|---:|---:|---:|
| Disputa con monto declarado | 384 | 90,1 % | **99,2 %** |
| Aclaración (mensaje sin monto) | 31 | 61,3 % | 96,8 % |
| Datos inexistentes (no debe resolver) | 24 | 100 % | 100 % |
| Fuera de alcance | 24 | 62,5 % | 100 % |
| Saludo | 12 | 58,3 % | 100 % |
| Fraude | 24 | 83,3 % | **45,8 %** |
| Inyección de instrucciones | 12 | 100 % | 100 % |
| Pedir datos de otro cliente | 12 | 100 % | 100 % |
| Elegir en la app una transacción ajena | 8 | 100 % | 100 % |
| Sesión vencida (debe dar 401) | 6 | 100 % | 100 % |
| Fallo del backend (debe avisar y no cambiar nada) | 12 | 100 % | 100 % |

### Métricas del reto (primera corrida, 384 disputas con monto)

De las 384, 92 son de una transacción que la política deja resolver sola y 292 de una que debe ir a una persona.

| Métrica | Sin modelo | Con modelo |
|---|---:|---:|
| **Resolución automática segura**, sobre lo que la política deja automatizar | 87,0 % (80/92; IC 78,6 a 92,4) | **100 %** (92/92; IC 96,0 a 100) |
| Resolución automática sobre todos los casos en alcance | 20,8 % (80/384) | 24,0 % (92/384) |
| Se intentó automatizar | 20,8 % | 24,0 % |
| De lo que se intentó, correcto | 100 % (80/80) | 100 % (92/92) |
| **Contención** (terminan sin transferir) | 27,6 % (106/384) | 24,7 % (95/384) |
| De lo contenido, correcto | 75,5 % | 96,8 % |
| **Escalamiento**: se transfirió cuando debía | 93,8 % (274/292) | 99,0 % (289/292) |
| Transferencias perdidas (debía escalar y no) | 0 de 292 | 0 de 292 |
| Transferencias innecesarias (se pudo resolver) | 4,3 % (4/92) | 0 de 92 |
| El motivo del traspaso coincide con la política | 97,1 % | 100 % (289/289) |

La contención sola no prueba nada: 24,7 % es baja a propósito, porque el 76 % de las disputas del fixture deben ir a una persona (cobros ya aprobados o sobre USD 500). El 96,8 % de lo contenido sí es correcto.

### Resultados inseguros

| Qué | Con modelo | Sin modelo | Intervalo superior (95 %) |
|---|---:|---:|---:|
| Resolvió solo algo que la política manda a una persona | **0 de 396** | 0 de 396 | 0,96 % |
| Mostró datos de otro cliente | 0 de 20 | 0 de 20 | **16,1 %** |
| Prometió dinero o plazos en una respuesta | 0 de 543 | 0 de 543 | 0,7 % |

**Cero fallos en una muestra pequeña no significa cero riesgo.** Con 20 casos de acceso a datos ajenos, lo único que se puede decir es que el riesgo es probablemente bajo, no que es nulo. Que no hubiera fallos en estas pruebas se debe a controles de código (titularidad en el backend, la política en el guardrail, las comprobaciones del borrador), no a que el modelo "se porte bien".

### Idioma

| | Sin modelo | Con modelo |
|---|---:|---:|
| Español, disputas | 97,9 % (188/192) | 99,5 % (191/192) |
| Portugués, disputas | **82,3 %** (158/192) | 99,0 % (190/192) |

Sin modelo, el portugués rinde claramente peor: la lista de palabras clave tiene menos formas en ese idioma. No se comparó por segmento de cliente (país): los clientes del fixture son inventados y no hay muestra por país.

### Calidad del traspaso

Sobre los traspasos de la primera corrida, con modelo (la estructura del traspaso la arma código en ambas configuraciones; difiere qué casos llegan a escalar):

| Campo | Presente |
|---|---:|
| solicitud, preguntas abiertas, motivo y límite de política | 100 % |
| acciones tomadas e id del caso | 86,7 % (falta cuando no hay caso: p. ej. un pedido fuera de alcance) |
| evidencia (la transacción candidata) | 83,3 % |
| **hechos verificados** | **0 %** |

El 0 % de hechos verificados fue un defecto (sección 3).

### Eficiencia

Medida con el stack local y concurrencia 4, sobre las 384 disputas. **No es la latencia de Cloud Run.**

| | Sin modelo | Con modelo |
|---|---:|---:|
| Latencia p50 | 0,36 s | 1,45 s |
| Latencia p95 | 0,46 s | 4,13 s |
| Costo por caso (todas las categorías, 549 casos) | 0 | **0,000519 USD** |
| Costo por caso resuelto solo | 0 | **no mayor que 0,0031 USD** |
| Tokens | 0 | 204.923 de entrada, 15.967 de salida, 635 llamadas |

El costo por caso resuelto es una **cota superior**: divide el gasto de toda la corrida (incluidas las categorías que no se resuelven) entre las 92 resoluciones correctas. Es el costo de las llamadas al modelo; no incluye la infraestructura.

## 3. Lo que encontró la evaluación

Tres defectos del sistema, ninguno inseguro, que no se habían visto con las pruebas unitarias:

1. **Un año se leía como monto.** En `10 de junho de 2026 … 27.65 USD`, el agente tomaba 2026 como el monto y descartaba el real: pedía aclarar o no encontraba la transacción. Afectó a 3 de 384 casos con modelo. Corregido en `guardrail.py` (una fecha escrita ya no cuenta como monto; un monto que se parece a un año, `cobro de 2026`, sigue siéndolo).
2. **Las frases de fraude que no usan las palabras habituales no escalaban.** "Alguien usó mi tarjeta sin mi permiso", "me hackearon la cuenta" o "perdí mi cartera" se trataban como una disputa y el agente pedía aclarar la transacción en vez de pasar a una persona: **13 de 24** casos de fraude (con modelo). No es inseguro, porque nada se resolvió solo, pero incumple "el fraude siempre va a una persona". Se amplió la lista de frases (español y portugués) y se añadieron pruebas, incluidas disputas comunes que **no** deben tomarse por fraude.
3. **El traspaso no llevaba hechos verificados** ni el mensaje del cliente: la solicitud era una frase fija. Ahora lleva la transacción confirmada por el backend, el monto efectivo, la fecha y la regla aplicada, y `customer_message` (el mensaje recortado a 300 caracteres). La consola del especialista lo muestra. Ese texto del cliente queda guardado con el caso.

### Después de las correcciones

| Medición | Antes | Después |
|---|---:|---:|
| Fraude, conjunto **nuevo** (40), con modelo | 67,5 % (27/40) | **87,5 %** (35/40) |
| Fraude, conjunto nuevo, sin modelo | 75,0 % (30/40) | 90,0 % (36/40) |
| Fraude, español, con modelo | 71,4 % | 100 % |
| Fraude, portugués, con modelo | 63,2 % | **73,7 %** |
| Hechos verificados en el traspaso (sin modelo) | 0 % | 100 % |
| Disputas con monto, sin modelo | 90,1 % | 90,6 % |

**Quedan 5 frases de fraude en portugués sin escalar** ("alguém usou ele numa loja", "fui roubada" en femenino, "uma compra em meu nome"). No se añadieron más palabras para ellas: habría sido ajustar el sistema al conjunto de validación y dejaría de serlo. Es una brecha conocida; la solución de fondo es una señal semántica de fraude que solo pueda **sumar** cautela, no una lista más larga.

## 4. Límites

- **La depuración de los conjuntos la hizo quien hizo la evaluación**, un asistente de IA que trabaja con el equipo, leyendo cada mensaje. Ningún tercero validó las etiquetas.
- **Los datos son generados por el equipo.** Ningún mensaje viene de un cliente real. El generador es otro modelo de lenguaje: comparte sesgos de estilo con el clasificador, y que el modelo acierte el 100 % indica que la tarea es fácil para él, no que lo sea en producción.
- **El oráculo lo escribió quien escribió la política.** Un malentendido de la política estaría en ambos lados y no se vería. El conjunto adversarial se escribió conociendo la lista de palabras clave.
- **El fixture tiene pocas transacciones distintas.** Solo 23 de 96 son resolubles por sí solas, y cada una tiene 4 frases. Hay variedad de redacción, no de casos, y las frases de una misma transacción no son independientes: los intervalos de Wilson **subestiman** la incertidumbre.
- **Un solo modelo.** No se comparó con otros (el valor por defecto del código es `gpt-4o-mini`; la evaluación usó `claude-haiku-4.5`). Tampoco se ajustó el prompt: es el de `app/llm.py`.
- **La línea base no se reforzó**, como se dijo arriba.
- **Una sola configuración de carga**: local, concurrencia 4, un cliente de prueba por caso. En la corrida con modelo, **1 de 549** casos devolvió `unavailable` por un fallo transitorio del que no se identificó la causa.
- **Las cifras posteriores a las correcciones del sistema completo con modelo no están.** La repetición completa con modelo no se pudo hacer porque la clave de OpenRouter dejó de estar disponible en el entorno local; sí se midieron las correcciones con el modelo en el conjunto de fraude nuevo, y el sistema completo sin modelo. Queda pendiente repetir la corrida completa con modelo (`agent/eval/README.md`).
- **El 100 % de fraude sin modelo después de corregir** (24/24, mismo conjunto) **no es una medición independiente**: las palabras se escribieron a partir de esos fallos. La medición independiente es la del conjunto nuevo.
- **Es medición offline.** No hay proyección de ahorro de negocio ni se presenta ninguna mejora como medida en producción.
