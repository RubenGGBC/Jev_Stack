# Informe de evaluación

Generado por `python -m jevsynth.eval.run` (no editar a mano; el análisis está en
`jevsynth/eval/analysis.md`).

- Tareas: 30 (`jevsynth/eval/tasks/*.json`); cada una con tests que se ejecutan
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
| random:0 w=3 | 0/30 (0%) | - | 1.08 | 176.7 | 176.7 | 74 | 134.3 |
| random:1 w=3 | 0/30 (0%) | - | 0.88 | 125.5 | 125.5 | 36 | 95.9 |
| random:2 w=3 | 0/30 (0%) | - | 1.24 | 204.5 | 204.5 | 87 | 150.1 |
| mock w=3 | 0/30 (0%) | - | 1.76 | 379.0 | 379.0 | 344 | 370.1 |
| noisy:0.9 w=3 | 18/30 (60%) | 3.7 | 0.71 | 84.8 | 84.8 | 4 | 45.0 |
| noisy:0.75 w=3 | 9/30 (30%) | 3.6 | 1.33 | 120.7 | 120.7 | 11 | 63.8 |
| oracle w=3 | 26/30 (87%) | 3.4 | 0.81 | 105.2 | 105.2 | 54 | 84.9 |
| mock-en w=3 | 0/30 (0%) | - | 1.66 | 415.8 | 415.8 | 257 | 366.2 |

## Ablación (c): ancho de haz

| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea | peticiones/tarea | retrocesos | dudas/tarea |
|---|---|---|---|---|---|---|---|
| random:0 w=1 | 0/30 (0%) | - | 0.33 | 44.7 | 44.7 | 45 | 32.1 |
| random:0 w=3 | 0/30 (0%) | - | 1.08 | 176.7 | 176.7 | 74 | 134.3 |
| random:0 w=5 | 0/30 (0%) | - | 1.59 | 342.2 | 342.2 | 59 | 251.3 |
| random:1 w=1 | 0/30 (0%) | - | 0.50 | 67.9 | 67.9 | 105 | 48.6 |
| random:1 w=3 | 0/30 (0%) | - | 0.88 | 125.5 | 125.5 | 36 | 95.9 |
| random:1 w=5 | 0/30 (0%) | - | 1.81 | 306.7 | 306.7 | 56 | 230.1 |
| random:2 w=1 | 0/30 (0%) | - | 0.51 | 65.5 | 65.5 | 78 | 47.7 |
| random:2 w=3 | 0/30 (0%) | - | 1.24 | 204.5 | 204.5 | 87 | 150.1 |
| random:2 w=5 | 0/30 (0%) | - | 1.89 | 330.1 | 330.1 | 55 | 250.7 |
| mock w=1 | 0/30 (0%) | - | 1.77 | 364.3 | 364.3 | 1214 | 356.7 |
| mock w=3 | 0/30 (0%) | - | 1.76 | 379.0 | 379.0 | 344 | 370.1 |
| mock w=5 | 0/30 (0%) | - | 2.39 | 413.7 | 413.7 | 99 | 398.2 |
| noisy:0.9 w=1 | 13/30 (43%) | 3.7 | 0.59 | 52.1 | 52.1 | 35 | 26.7 |
| noisy:0.9 w=3 | 18/30 (60%) | 3.7 | 0.71 | 84.8 | 84.8 | 4 | 45.0 |
| noisy:0.9 w=5 | 20/30 (67%) | 3.5 | 1.17 | 170.5 | 170.5 | 6 | 98.5 |
| noisy:0.75 w=1 | 6/30 (20%) | 3.7 | 0.86 | 73.5 | 73.5 | 58 | 37.7 |
| noisy:0.75 w=3 | 9/30 (30%) | 3.6 | 1.33 | 120.7 | 120.7 | 11 | 63.8 |
| noisy:0.75 w=5 | 11/30 (37%) | 3.5 | 1.14 | 159.2 | 159.2 | 5 | 90.4 |
| oracle w=1 | 26/30 (87%) | 3.4 | 0.49 | 64.3 | 64.3 | 207 | 53.4 |
| oracle w=3 | 26/30 (87%) | 3.4 | 0.81 | 105.2 | 105.2 | 54 | 84.9 |
| oracle w=5 | 26/30 (87%) | 3.4 | 1.11 | 165.8 | 165.8 | 12 | 134.2 |
| mock-en w=1 | 0/30 (0%) | - | 1.77 | 419.5 | 419.5 | 1354 | 380.1 |
| mock-en w=3 | 0/30 (0%) | - | 1.66 | 415.8 | 415.8 | 257 | 366.2 |
| mock-en w=5 | 0/30 (0%) | - | 2.35 | 499.8 | 499.8 | 124 | 419.5 |

## Ablación (a): descripción corta uniforme vs. docstring

| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea | peticiones/tarea | retrocesos | dudas/tarea |
|---|---|---|---|---|---|---|---|
| mock w=3 | 0/30 (0%) | - | 1.76 | 379.0 | 379.0 | 344 | 370.1 |
| mock w=3 doc | 0/30 (0%) | - | 1.70 | 380.3 | 380.3 | 339 | 368.4 |
| mock-en w=3 | 0/30 (0%) | - | 1.66 | 415.8 | 415.8 | 257 | 366.2 |
| mock-en w=3 doc | 0/30 (0%) | - | 1.36 | 386.9 | 386.9 | 244 | 330.7 |

## Ablación (b): con y sin filtro por tipos

| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea | peticiones/tarea | retrocesos | dudas/tarea |
|---|---|---|---|---|---|---|---|
| random:0 w=3 | 0/30 (0%) | - | 1.08 | 176.7 | 176.7 | 74 | 134.3 |
| mock w=3 | 0/30 (0%) | - | 1.76 | 379.0 | 379.0 | 344 | 370.1 |
| noisy:0.9 w=3 | 18/30 (60%) | 3.7 | 0.71 | 84.8 | 84.8 | 4 | 45.0 |
| oracle w=3 | 26/30 (87%) | 3.4 | 0.81 | 105.2 | 105.2 | 54 | 84.9 |
| random:0 w=3 sin-tipos | 0/30 (0%) | - | 0.38 | 229.1 | 229.1 | 40 | 170.5 |
| mock w=3 sin-tipos | 0/30 (0%) | - | 0.86 | 458.8 | 458.8 | 156 | 407.5 |
| noisy:0.9 w=3 sin-tipos | 11/30 (37%) | 3.2 | 0.30 | 142.6 | 142.6 | 6 | 88.0 |
| oracle w=3 sin-tipos | 22/30 (73%) | 3.2 | 0.23 | 136.7 | 136.7 | 25 | 116.2 |
| mock-en w=3 | 0/30 (0%) | - | 1.66 | 415.8 | 415.8 | 257 | 366.2 |
| mock-en w=3 sin-tipos | 0/30 (0%) | - | 0.56 | 292.8 | 292.8 | 164 | 255.3 |

## Dónde falla

| configuración | ok | catálogo | selección | búsqueda | tipos | emisión |
|---|---|---|---|---|---|---|
| random:0 w=3 | 0 | 4 | 25 | 1 | 0 | 0 |
| random:1 w=3 | 0 | 4 | 26 | 0 | 0 | 0 |
| random:2 w=3 | 0 | 4 | 24 | 2 | 0 | 0 |
| mock w=3 | 0 | 4 | 14 | 11 | 1 | 0 |
| noisy:0.9 w=3 | 18 | 4 | 8 | 0 | 0 | 0 |
| noisy:0.75 w=3 | 9 | 4 | 16 | 0 | 1 | 0 |
| oracle w=3 | 26 | 4 | 0 | 0 | 0 | 0 |
| mock-en w=3 | 0 | 4 | 14 | 12 | 0 | 0 |
| mock w=3 doc | 0 | 4 | 14 | 11 | 1 | 0 |
| random:0 w=3 sin-tipos | 0 | 4 | 1 | 0 | 25 | 0 |
| mock w=3 sin-tipos | 0 | 4 | 0 | 10 | 16 | 0 |
| noisy:0.9 w=3 sin-tipos | 11 | 4 | 7 | 0 | 8 | 0 |
| oracle w=3 sin-tipos | 22 | 4 | 1 | 0 | 3 | 0 |
| mock-en w=3 doc | 0 | 4 | 16 | 10 | 0 | 0 |
| mock-en w=3 sin-tipos | 0 | 4 | 9 | 6 | 11 | 0 |

## Detalle por tarea (ancho 3)

| tarea | random:0 w=3 | random:1 w=3 | random:2 w=3 | mock w=3 | noisy:0.9 w=3 | noisy:0.75 w=3 | oracle w=3 | mock-en w=3 |
|---|---|---|---|---|---|---|---|---|
| count_words | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✓ | ✓ | ✗ búsqueda |
| mean_age | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✗ selección | ✓ | ✗ búsqueda |
| top3_words | ✗ selección | ✗ selección | ✗ búsqueda | ✗ búsqueda | ✓ | ✓ | ✓ | ✗ búsqueda |
| count_error_lines | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✗ selección | ✓ | ✗ búsqueda |
| sum_numbers_script | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección |
| max_value | ✗ selección | ✗ selección | ✗ selección | ✗ tipos | ✓ | ✓ | ✓ | ✗ selección |
| sort_words | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección | ✓ | ✗ búsqueda |
| count_distinct | ✗ búsqueda | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✗ selección | ✓ | ✗ selección |
| json_port | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✓ | ✓ | ✗ selección |
| count_lines | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✗ selección | ✓ | ✗ búsqueda |
| sum_price | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✗ selección | ✗ selección | ✓ | ✗ búsqueda |
| replace_spaces | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección |
| long_words | ✗ selección | ✗ selección | ✗ búsqueda | ✗ búsqueda | ✗ selección | ✗ selección | ✓ | ✗ búsqueda |
| word_lengths | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✓ | ✓ | ✗ búsqueda |
| join_lines | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✓ | ✓ | ✗ selección |
| print_upper_lines | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección | ✓ | ✗ selección |
| mode_city | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección |
| count_numbers_regex | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✓ | ✓ | ✗ búsqueda |
| file_suffix | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección |
| rounded_mean | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✓ | ✓ | ✗ selección |
| sum_squares | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ tipos | ✓ | ✗ selección |
| word_counts | ✗ selección | ✗ selección | ✗ selección | ✗ búsqueda | ✓ | ✓ | ✓ | ✗ búsqueda |
| csv_row_count_script | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección | ✓ | ✗ selección |
| even_numbers | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección |
| comment_lines | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ búsqueda |
| write_file | ✗ selección | ✗ selección | ✗ selección | ✗ selección | ✓ | ✗ selección | ✓ | ✗ selección |
| reverse_words | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo |
| sort_rows_by_age | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo |
| is_palindrome | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo |
| longest_word | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo | ✗ catálogo |

## Análisis

**Estado:** no ha sido posible evaluar Jev real. Ni la API (`api.typesafe.ai`) ni la
documentación son accesibles desde el entorno donde se construyó el prototipo, y no hay
clave. Todas las filas son líneas base o choosers simulados. La rejilla con Jev se
lanza con `python -m jevsynth.eval.run --jev` y añade las filas `jev ...` y `jev-en ...`.

### Qué dicen las líneas base

- **Oráculo (cota superior del catálogo + combinadores + emisión): 26/30.** Las 4
  tareas restantes no tienen solución expresable y están marcadas como tales
  (`limite:*`). Por tanto **la emisión no falla nunca** (0 en todas las filas) y el
  techo actual lo marca la expresividad, no el resto de la tubería.
- **RandomChooser y MockChooser: 0/30.** Con unos 200 candidatos tipados por hueco de
  instrucción, elegir al azar no llega a nada. El Mock léxico tampoco, ni en español
  ni en inglés. Las peticiones apenas comparten palabras con firmas y descripciones
  (`count` ↔ `str.count`, no `len`), y sus empates hacen que la búsqueda agote el
  presupuesto. Es la confirmación de que la señal tiene que venir del chooser.
- **Oráculo ruidoso (simula un chooser imperfecto):** con un 90 % de acierto por
  decisión resuelve 43 % (ancho 1), 60 % (ancho 3) y 67 % (ancho 5). Con un 75 %,
  20 %, 30 % y 37 %. Los fallos se concentran en las tareas largas: las resueltas
  necesitan de media 8-9 decisiones y las fallidas 11-12. Con p de acierto por
  decisión y n decisiones, la probabilidad de un camino perfecto es pⁿ (0,9¹¹ ≈ 0,31).
  El haz recupera parte de los errores, pero no todos.

### Ablaciones

- **(c) Ancho de haz.** Es la palanca más clara cuando el chooser se equivoca: de 1 a
  3 sube +5 tareas (0,9) y +3 (0,75). De 3 a 5 la ganancia se reduce (+2) y el
  número de preguntas casi se duplica (85 → 170 por tarea con 0,9).
- **(b) Filtro por tipos.** Sin él el oráculo ruidoso (0,9) cae de 18 a 11 y el
  oráculo perfecto de 26 a 22. Los fallos nuevos son errores de tipos en ejecución
  (categoría *tipos*). Además de evitar programas mal tipados, el filtro **convierte en
  forzadas** muchas decisiones (un único argumento válido) que ya no hay que preguntar.
  Sin él, esas decisiones quedan abiertas y cada una es otra oportunidad de fallo.
- **(a) Descripción corta vs. docstring.** Sin efecto en las líneas base (todo 0). Es
  una ablación para Jev: la descripción solo importa a un chooser que la lea.
- **(e) Idioma.** Para el Mock léxico da igual (0 en ambos). Para Jev conviene medirlo:
  las peticiones y las instrucciones están en español y el catálogo en inglés.

### Dónde falla, y qué haría a continuación

1. **Catálogo / expresividad (4 tareas):** faltan funciones como valor (`key=len`,
   `sorted(..., key=...)`), *slicing* (`s[::-1]`) y literales que la petición no dice
   (`" "` para unir palabras). Opciones: componentes "función como valor" para
   parámetros `Callable` de una sola aridad, y un pequeño conjunto fijo de constantes
   (`" "`, `""`, `0`, `1`) como combinador, documentado.
2. **Selección:** es el fallo dominante de cualquier chooser imperfecto. El 74 % de los
   componentes comparte su *summary* con otro (sobrecargas y variantes), y solo la firma
   los distingue. Habría que comprobar con Jev si basta con la firma o hay que fusionar
   variantes en una opción y decidir la sobrecarga por tipos.
3. **Búsqueda:** el presupuesto (400 expansiones) solo se agota con choosers sin señal o
   en tareas sin solución. Para Jev, el coste a vigilar son las preguntas por tarea
   (85-170 con el oráculo ruidoso). Con los lotes y la caché, las peticiones reales
   serán menos que las preguntas.
