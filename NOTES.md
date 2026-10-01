# Notas y hallazgos

## Fase 0

- El bucle es voraz y sin retroceso; el haz y el retroceso llegan en la fase 5.
- Los argumentos se rellenan con la variable compatible más reciente (heurística del
  script). Con varias variables del mismo tipo esto puede ser una decisión real: valorar
  ofrecerla al chooser como `Option(kind="symbol")` en la fase 2.
- `is_done` no se consulta con el programa vacío.
- El casado de tipos es por igualdad de nombre (`TypeRef.name`); subtipos/uniones en fase 2.

## Fase 1

- La stdlib casi no tiene anotaciones en tiempo de ejecución (`typing.get_type_hints`
  devuelve `{}` para casi todo `builtins`, `csv`, `json`...). Los tipos salen de los stubs
  de **typeshed** incluidos en mypy (`catalog/stubs.py`); los docstrings, del objeto real.
  Es un paso offline (`python -m jevsynth.catalog.build`) y el JSON se versiona.
- 913 componentes, 894 con firma tipada (requisito ≥150). Incluye sobrecargas (`id@k`),
  una variante con el primer parámetro opcional posicional (`id+param`), métodos,
  propiedades y 26 operadores de `operator` con tipos escritos a mano (sus stubs son `Any`).
- `Literal[...]` se conserva como tipo: así las sobrecargas binarias de `open` solo son
  candidatas si la petición trae un literal de modo válido (`"rb"`...).
- `X | Any` se simplifica a `X` (convención de typeshed para "normalmente X").
- El filtro anti-inyección es por subcadena, así que "filesystem" también cae (contiene
  "system"): unas pocas descripciones de `pathlib` quedan con el texto neutro de reserva.
- Varias clases no tienen docstring en 3.11 (p. ej. `csv.DictReader`): descripción neutra
  "csv.DictReader (constructor).". Candidato a mejora offline de descripciones.

## Fase 2

- Casado de tipos en `scope/typesys.py`: subtipos nominales (bases de typeshed),
  estructurales (`__iter__`, `__len__`, `read`, `__enter__`...), promociones int→float,
  uniones, `Literal`, TypeVar con restricciones/cotas y ensanchamiento (`max(int, float)`).
- Todos los genéricos son covariantes (simplificación); el supertipo genérico más
  cercano decide (`TextIOWrapper` itera `str` aunque `_IOBase` declare `bytes`).
- Los literales no rellenan protocolos de colección: `"age"` es un `str`, que es
  iterable, pero `csv.reader("age")` o `len("age")` no son candidatos.
- Por defecto se excluyen componentes sin parámetros obligatorios (`list()`,
  `Path.cwd()`): no consumen nada del scope y meten ruido en cada hueco.
- Hallazgo: con tipos correctos `dict[str, str]` y `list[str]` también son
  `Iterable[str]`, así que `csv.reader(row)` es candidato. Es correcto por tipos; queda
  para el chooser descartarlo.

## Fase 3

- Extractor de literales con reglas fijas: comillas, ficheros, columnas (tras
  "columna"/"campo"/"column", tras un agregado "media de X"/"sum of X", "X column"),
  snake_case y números. No hay literales por defecto (ni `0`, ni `","`): si la
  petición no lo menciona, no existe. Límite conocido: "separa por comas" no da `","`.
- Combinadores de control fijos: `with`, `for`, comprensión, `if`, `return`, `print`
  y `end` (cerrar bloque).

## Fase 4

- IR propia y pequeña (`emit/ir.py`) que se baja a `ast` y se emite con `ast.unparse`.
  Los huecos se emiten como `...`, así que también el programa parcial compila y es lo
  que ve el chooser como "resumen del programa".
- Métodos, propiedades, operadores (`a + b`, `d[k]`, `x in c`, `not x`) y parámetros
  solo-keyword se emiten con su sintaxis. `import` solo de los módulos usados.
- Pase opcional de plegado: una temporal de un solo uso se mete en la instrucción
  siguiente si se evalúa una sola vez allí (no en el cuerpo de un `for` ni en el
  elemento/condición de una comprensión).

## Fase 5

- Motor (`synth/engine.py`): el programa parcial es la IR + una agenda de tareas. Las
  tareas de decisión (instrucción, hueco de expresión, colección a recorrer) generan
  opciones cerradas; las automáticas (nombrar/tipar resultados, comprobar llamadas
  anidadas) las ejecuta el script. Cada rama trabaja sobre una copia profunda.
- Huecos: argumentos de instrucciones solo con símbolos o literales (los intermedios se
  asignan a variables). Se permite anidar llamadas (profundidad ≤ 2) solo donde no hay
  instrucción a la que asignar: elemento/condición de comprensión, condición de `if` y
  recurso del `with`. Para ofrecer ahí `float(row['age'])` se usan "variables virtuales":
  una por tipo producible en un paso.
- Decisiones forzadas (una sola opción) no consultan al chooser.
- Elección jerárquica cuando hay más de `max_options` (30) opciones: grupo (módulo,
  clase, variables, literales, control) y luego opción. Un hueco de instrucción con
  `text: str` tiene ~200 candidatos tipados.
- Búsqueda en haz con puntuación = suma de log-probabilidades; cada expansión genera
  `max(width, branch)` hijos y los que no caben van a una reserva que se usa al vaciarse
  el haz (retroceso). Se para cuando ninguna rama del haz puede superar a la mejor
  completa. `is_done` con umbral solo en scripts; las funciones terminan con `return`.
- El oráculo necesita saber en qué punto de la solución está cada rama. El estado que
  recibe el chooser es un `str` (`StateText`) con un atributo `decisions` que el chooser
  real ignora; el oráculo casa su secuencia objetivo como subsecuencia.
- Rendimiento: ~0,6 s por tarea con el oráculo tras cachear hash de TypeRef, ancestros,
  casados con tipos sin variables y candidatos por perfil de tipos del scope.

## Fase 6

- La web de documentación (docs.typesafe.ai) y la API (api.typesafe.ai) no son
  accesibles desde este entorno (proxy). La API se ha leído del SDK publicado en PyPI
  (`typesafe-sdk` 0.7.2): `TypeSafeClient.system_one(state, questions)` con preguntas
  `Choice` (probabilidades por criterio) y `Noul` (sí/no; el nombre es literal). Clave en
  `TYPESAFE_API_KEY`, URL en `TYPESAFE_BASE_URL`, modelo por defecto `jev-latest`.
- Estado enviado: JSON `{"tarea", "programa"}`; el hueco va en las instrucciones de cada
  pregunta. Así varias preguntas comparten estado y van en una sola petición: las
  elecciones dentro de los mejores grupos y, en scripts, la pregunta de parada junto con
  la siguiente instrucción.
- Claves de los criterios configurables (`criteria_style`): `id` (por defecto, el id del
  componente con la etiqueta como descripción), `label` o `letter` (A, B, C...). Es una de
  las variantes de redacción a evaluar con Jev real.
- Reintentos con backoff y timeout: los del SDK (`RetryPolicy`). Caché LRU por
  (tarea, programa, hueco, opciones).
- Tests sin red con `httpx2.MockTransport` sobre el SDK real. Los tests con Jev real
  (`pytest -m jev`) no se han podido ejecutar aquí: sin clave y sin salida a la API.
- Pendiente: la petición de usar una clave de **Opper**. El SDK de Opper (`opperai`)
  no expone `system_one`/`Choice`/`Noul` ni probabilidades por opción; falta confirmar
  cómo da Opper acceso a Jev antes de escribir un adaptador.
