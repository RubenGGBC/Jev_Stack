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
