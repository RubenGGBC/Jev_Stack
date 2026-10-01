# Informe de evaluación

Generado por `python -m jevsynth.eval.run` (no editar a mano; el análisis está en
`jevsynth/eval/analysis.md`).

- Tareas: 6 (`jevsynth/eval/tasks/*.json`); cada una con tests que se ejecutan
  en un subproceso con timeout y sin red.
- pass@1: el programa de mayor puntuación de la búsqueda pasa todos los tests.
- Pasos: instrucciones insertadas. Preguntas: elecciones + paradas enviadas al chooser.
  Peticiones: llamadas reales (un lote cuenta como una). Dudas: decisiones con
  margen top1 - top2 < 0,1.
- Categorías de fallo: **catálogo** (no hay solución expresable con el catálogo y los
  combinadores: ni el oráculo la tiene), **selección** (había solución y el chooser eligió
  otra cosa que no pasa los tests), **búsqueda** (no se encontró programa completo),
  **tipos** (error de tipos en ejecución), **emisión** (código que no compila).

## Resultados principales (ancho de haz 3)

| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea | peticiones/tarea | retrocesos | dudas/tarea |
|---|---|---|---|---|---|---|---|
| noisy:0.9 w=3 | 3/6 (50%) | 0.0 | 0.89 | 79.2 | 79.2 | 0 | 38.0 |
| noisy:0.75 w=3 | 2/6 (33%) | 0.0 | 2.96 | 236.2 | 236.2 | 6 | 120.8 |

## Ablación (c): ancho de haz

| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea | peticiones/tarea | retrocesos | dudas/tarea |
|---|---|---|---|---|---|---|---|
| noisy:0.9 w=1 | 2/6 (33%) | 0.0 | 1.15 | 65.3 | 65.3 | 3 | 32.0 |
| noisy:0.9 w=3 | 3/6 (50%) | 0.0 | 0.89 | 79.2 | 79.2 | 0 | 38.0 |
| noisy:0.9 w=5 | 3/6 (50%) | 0.0 | 1.53 | 158.0 | 158.0 | 0 | 84.0 |
| noisy:0.75 w=1 | 1/6 (17%) | 0.0 | 2.62 | 198.5 | 198.5 | 30 | 96.0 |
| noisy:0.75 w=3 | 2/6 (33%) | 0.0 | 2.96 | 236.2 | 236.2 | 6 | 120.8 |
| noisy:0.75 w=5 | 2/6 (33%) | 0.0 | 1.96 | 178.5 | 178.5 | 0 | 96.2 |

## Ablación (a): descripción corta uniforme vs. docstring

(sin datos)

## Ablación (b): con y sin filtro por tipos

| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea | peticiones/tarea | retrocesos | dudas/tarea |
|---|---|---|---|---|---|---|---|
| noisy:0.9 w=3 | 3/6 (50%) | 0.0 | 0.89 | 79.2 | 79.2 | 0 | 38.0 |
| noisy:0.9 w=3 sin-tipos | 3/6 (50%) | 0.0 | 0.28 | 137.3 | 137.3 | 0 | 79.3 |

## Dónde falla

| configuración | ok | catálogo | selección | búsqueda | tipos | emisión |
|---|---|---|---|---|---|---|
| noisy:0.9 w=3 | 3 | 0 | 3 | 0 | 0 | 0 |
| noisy:0.75 w=3 | 2 | 0 | 4 | 0 | 0 | 0 |
| noisy:0.9 w=3 sin-tipos | 3 | 0 | 3 | 0 | 0 | 0 |

## Detalle por tarea (ancho 3)

| tarea | noisy:0.9 w=3 | noisy:0.75 w=3 |
|---|---|---|
| count_words | ✓ | ✓ |
| mean_age | ✓ | ✗ selección |
| top3_words | ✓ | ✓ |
| sum_price | ✗ selección | ✗ selección |
| long_words | ✗ selección | ✗ selección |
| even_numbers | ✗ selección | ✗ selección |
