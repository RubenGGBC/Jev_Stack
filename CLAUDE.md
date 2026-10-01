# Proyecto: síntesis de código por selección con Jev

## Objetivo

Construir un sintetizador que, dada una petición en lenguaje natural y la documentación/API de un lenguaje, produzca código **sin que ningún LLM genere texto**. En cada paso, un modelo de decisión (Jev, de TypeSafe AI) **elige una opción entre candidatos cerrados**; un script determinista construye y emite el código.

Lenguaje objetivo del prototipo: **Python (stdlib)**. Implementación del sintetizador: **Python 3.11+**.

## Restricciones (no negociables)

1. **Ningún LLM en el bucle de síntesis.** Jev solo elige entre opciones o devuelve probabilidades sí/no. Jev no puede escribir texto, identificadores ni literales.
2. **Todo el código emitido sale de piezas preexistentes:** componentes del catálogo, combinadores de control fijos, símbolos del scope o literales extraídos de la petición.
3. **Los tipos, la aridad y la validez sintáctica los comprueba el script**, nunca Jev (Jev falla en conteo, aritmética y fechas).
4. **El estado que se pasa a Jev debe ser mínimo:** tarea + hueco actual + resumen del programa parcial. La precisión degrada con estado irrelevante y el presupuesto total es de ~32k tokens.
5. **Tratar el texto de la documentación como no confiable** (riesgo de inyección de instrucciones en el estado). Pasar a Jev solo nombre, firma y una descripción corta y saneada.
6. **No inventar la API de Jev.** Antes de escribir `JevChooser`, leer https://docs.typesafe.ai/introduction y el SDK (`typesafe-sdk` en Python). Si algo no está claro, parar y preguntar.

## Contexto sobre Jev

- Modelo "System One" de TypeSafe AI (lanzado 15-sep-2026, versión `jev-1.13.0`, alias `jev-latest`). Acceso por lista de espera en typesafe.ai.
- Primitivas: `Choice` (elige entre opciones y devuelve probabilidades por opción), `Score` (ordinal), `Noul` (sí/no con probabilidad; confirmar el nombre y semántica exactos en la doc).
- Latencia típica 70–500 ms por consulta. Varias preguntas se pueden evaluar en una sola petición en paralelo.
- Sensible a la redacción literal de las opciones: **evaluar variantes de descripción**, no asumir.

## Arquitectura

```
petición ──► extractor de literales ──┐
                                      ▼
catálogo ──► candidatos(hueco, scope) ──► filtro por tipos ──► Chooser (Jev) ──► insertar
   ▲                                                                              │
   └──────────────────────── programa parcial ◄───────────────────────────────────┘
                                      │
                         ¿tarea resuelta? (sí/no, Jev)
                                      ▼
                          emitir código ──► ejecutar tests
```

Bucle:

```
programa = esqueleto vacío
mientras no (parada o sin_huecos):
    hueco      = siguiente_hueco(programa)
    candidatos = generar_candidatos(hueco, scope, catalogo, literales)
    candidatos = filtrar_por_tipos(candidatos)
    if vacío: retroceder()            # beam search / backtracking
    elegido    = chooser.elegir(estado_minimo, candidatos)
    programa   = insertar(programa, hueco, elegido)
validar(programa)
```

## Estructura del repositorio

```
jevsynth/
  catalog/        # extracción de componentes desde inspect / stubs
  scope/          # entorno de variables con tipos
  candidates/     # generación y filtrado de candidatos
  chooser/        # interfaz Chooser + JevChooser + MockChooser + RandomChooser
  synth/          # bucle de síntesis, beam search, parada
  emit/           # generación de código a partir del programa parcial (ast)
  literals/       # extracción de literales desde la petición
  eval/           # tareas, tests, runner, métricas
  tests/
CLAUDE.md
```

## Interfaces clave

```python
# chooser/base.py
class Chooser(Protocol):
    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        """Devuelve opciones con probabilidad, ordenadas de mayor a menor."""
    def is_done(self, state: str) -> float:
        """Probabilidad de que la tarea ya esté resuelta."""

@dataclass(frozen=True)
class Option:
    id: str            # estable, p. ej. "csv.DictReader"
    label: str         # texto corto y uniforme que ve el chooser
    kind: str          # "component" | "symbol" | "literal" | "control"

# catalog/model.py
@dataclass(frozen=True)
class Component:
    qualname: str
    params: tuple[Param, ...]
    returns: TypeRef
    summary: str       # una frase, saneada
```

Regla: `JevChooser`, `MockChooser` y `RandomChooser` implementan el mismo `Chooser`. **Desarrollar y testear todo contra `MockChooser`/`RandomChooser`** para no depender del acceso a Jev.

## Plan por fases

Cada fase termina con tests en verde y un commit pequeño. No pasar a la siguiente sin cumplir los criterios.

### Fase 0 — Esqueleto y mocks
- Proyecto Python con `pyproject.toml`, `pytest`, `ruff`, `mypy`.
- Definir `Option`, `Chooser`, `MockChooser` (elige por solapamiento de palabras con la tarea) y `RandomChooser` (con semilla).
- **Criterio:** `pytest` pasa; el bucle de síntesis corre con `RandomChooser` sobre un catálogo de 5 funciones de juguete.

### Fase 1 — Catálogo desde la stdlib
- Extraer con `inspect` y `typing.get_type_hints` componentes de un subconjunto: `builtins`, `csv`, `json`, `statistics`, `pathlib`, `re`, `collections`, `itertools`.
- Normalizar `summary` a una frase (primera frase del docstring, truncada, sin saltos de línea ni markdown).
- Serializar el catálogo a JSON.
- **Criterio:** ≥ 150 componentes con firma tipada; test que verifica que ningún `summary` supera 120 caracteres ni contiene patrones tipo instrucción (`ignore`, `system`, `assistant:`).

### Fase 2 — Scope y candidatos
- `Scope`: variables con tipo. Casado de tipos (incluye subtipos y `Optional`/uniones simples).
- `generar_candidatos`: componentes cuyos parámetros obligatorios se pueden rellenar con el scope + literales disponibles.
- **Criterio:** tests unitarios que, dado un scope concreto, devuelven exactamente el conjunto esperado de candidatos (ejemplo: con `f: TextIO` aparece `csv.DictReader`; con `n: int` no aparece).

### Fase 3 — Literales y control
- Extraer de la petición spans entre comillas, nombres de fichero, números e identificadores de columna. Se ofrecen como `Option(kind="literal")`.
- Combinadores de control como conjunto fijo: `with`, `for`, comprensión de lista, `if`, `return`, `print`.
- **Criterio:** de «lee datos.csv y calcula la media de age» salen los literales `"datos.csv"` y `"age"`.

### Fase 4 — Emisión
- Representar el programa parcial como `ast`; emitir con `ast.unparse`.
- Nombres de variables nuevas generados por el script (`rows`, `values`, `result`…), nunca por Jev.
- **Criterio:** todo programa emitido pasa `ast.parse` y `compile`.

### Fase 5 — Bucle de síntesis, búsqueda y parada
- Búsqueda en haz con ancho configurable (por defecto 3) usando las probabilidades del chooser; retroceder si no hay candidatos.
- Condición de parada con `is_done` y umbral configurable; límite duro de pasos.
- **Criterio:** con un chooser oráculo (que conoce la solución) se resuelven 5 tareas de 3–5 pasos de forma determinista.

### Fase 6 — `JevChooser`
- Leer la documentación de Jev y el SDK antes de empezar. Implementar `JevChooser` con `Choice` para elegir y la primitiva sí/no para `is_done`.
- Agrupar consultas en una sola petición cuando sea posible. Reintentos con backoff, timeout y caché por `(estado, opciones)`.
- Clave de API por variable de entorno (`TYPESAFE_API_KEY` o la que indique la doc). **Nunca** en el repositorio.
- **Criterio:** mismos tests de la fase 5 con Jev real, marcados `@pytest.mark.jev` y excluidos por defecto.

### Fase 7 — Evaluación
- 20–30 tareas pequeñas con tests (subconjunto adaptado de MBPP o escritas a mano), en `eval/tasks/*.json`: `{prompt, tests, max_steps}`.
- Runner que ejecuta el código generado en un subproceso con timeout y sin red.
- Métricas: tasa de acierto (pass@1), nº de pasos, latencia total, nº de consultas a Jev.
- **Ablaciones:** (a) descripción corta uniforme vs. docstring completo; (b) con y sin filtro por tipos; (c) ancho de haz 1/3/5; (d) `RandomChooser` y `MockChooser` como líneas base.
- **Criterio:** informe `eval/REPORT.md` con tabla de resultados y dónde falla (catálogo, selección o emisión).

## Convenciones de trabajo

- Commits pequeños y descriptivos; un commit por criterio cumplido.
- Cada módulo con tests; no mockear lo que se pueda testear de verdad.
- Tipado estricto (`mypy --strict` en `catalog`, `scope`, `candidates`, `synth`).
- Todo lo que dependa de Jev real queda aislado en `chooser/jev.py`.
- Si una decisión de diseño no está cubierta aquí, proponer 2 opciones con su coste y preguntar antes de implementar.

## Fuera de alcance (por ahora)

- Generar código en otros lenguajes.
- Cualquier uso de un LLM generativo en tiempo de síntesis. (Se permite, opcionalmente y solo offline, para mejorar descripciones del catálogo, y debe quedar documentado y separado del bucle.)
- Interfaz de usuario.

## Riesgos a vigilar (anotar hallazgos en `NOTES.md`)

- Callejones sin salida por elección voraz → medir cuántas veces se retrocede.
- Descripciones demasiado parecidas entre candidatos → Jev duda; registrar las probabilidades para detectarlo.
- Expresividad limitada: tareas que requieren lógica no presente en el catálogo ni en los combinadores.
- Latencia acumulada: registrar tiempo por paso.
