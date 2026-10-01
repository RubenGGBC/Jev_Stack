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
