"""JevChooser: elección con Jev (TypeSafe AI, modelo "System One") vía `typesafe-sdk`.

API usada (leída del SDK `typesafe-sdk` 0.7.2, `TypeSafeClient.system_one`):

    client.system_one(state=<texto|JSON>, questions={nombre: Choice(...) | Noul(...)})
      → SystemOneResponse
          .choices[nombre].probabilities  dict[criterio, prob]
          .nouls[nombre].noul             prob de "sí"

- `Choice(instructions, criteria={clave: descripción})`: elige entre opciones cerradas.
- `Noul(instructions, criteria={"true": ..., "false": ...})`: sí/no con probabilidad.
- Varias preguntas sobre el mismo `state` van en una sola petición.
- Clave en `TYPESAFE_API_KEY`; URL base en `TYPESAFE_BASE_URL`; modelo por defecto
  `jev-latest` (o `TYPESAFE_DEFAULT_MODEL`). Reintentos con backoff los hace el SDK
  (`RetryPolicy`).

Jev no escribe texto: solo devuelve probabilidades sobre las claves que le damos.
Todo lo que depende de Jev real está aislado en este módulo.
"""

from __future__ import annotations

import string
from collections import OrderedDict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal

from jevsynth.chooser.base import Option, parse_state, rank

if TYPE_CHECKING:  # pragma: no cover
    from typesafe_sdk import TypeSafeClient

CriteriaStyle = Literal["id", "label", "letter"]

CHOOSE_INSTRUCTIONS = (
    "Estás construyendo, paso a paso, un programa Python que resuelve la tarea. En el "
    "programa parcial, ⟨?⟩ marca el hueco que hay que rellenar ahora: {hole}. Elige la "
    "opción que mejor rellena ese hueco para avanzar hacia la solución."
)
DONE_INSTRUCTIONS = "¿El programa parcial ya resuelve la tarea por completo?"
DONE_CRITERIA = {
    "true": "el programa ya hace todo lo que pide la tarea",
    "false": "todavía falta algún paso para resolver la tarea",
}

Query = tuple[str, list[Option]]  # (descripción del hueco, opciones)


class JevChooser:
    """Implementa `Chooser` (y el lote opcional `batch`) sobre la API de Jev."""

    def __init__(
        self,
        client: TypeSafeClient | None = None,
        *,
        model: str | None = None,
        criteria_style: CriteriaStyle = "id",
        timeout: float = 10.0,
        max_retries: int = 3,
        cache_size: int = 4096,
        **client_kwargs: Any,
    ) -> None:
        if client is None:
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            client = TypeSafeClient(
                model=model,
                timeout=timeout,
                retry=RetryPolicy(max_retries=max_retries, timeout=timeout * (max_retries + 1)),
                **client_kwargs,
            )
        self.client = client
        self.model = model
        self.criteria_style = criteria_style
        self.requests = 0  # peticiones HTTP realmente enviadas (sin contar caché)
        self.questions = 0
        self._cache: OrderedDict[tuple[object, ...], object] = OrderedDict()
        self._cache_size = cache_size

    # -- utilidades --------------------------------------------------------------------

    def _keys(self, options: Sequence[Option]) -> list[str]:
        if self.criteria_style == "letter":
            alphabet = string.ascii_uppercase
            return [alphabet[i % 26] + (str(i // 26) if i >= 26 else "") for i in range(len(options))]
        if self.criteria_style == "label":
            keys = [o.label for o in options]
            if len(set(keys)) == len(keys):
                return keys
        return [o.id for o in options]

    def _criteria(self, options: Sequence[Option]) -> dict[str, str | None]:
        keys = self._keys(options)
        if self.criteria_style == "label" and keys != [o.id for o in options]:
            return dict.fromkeys(keys)
        return {k: o.label for k, o in zip(keys, options, strict=True)}

    @staticmethod
    def _state(state: str) -> tuple[dict[str, str], str]:
        task, hole, program = parse_state(state)
        return {"tarea": task, "programa": program}, hole

    def _cache_get(self, key: tuple[object, ...]) -> object | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: tuple[object, ...], value: object) -> None:
        self._cache[key] = value
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    # -- API Chooser ---------------------------------------------------------------------

    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        _, hole = self._state(state)
        ranked, _ = self.batch(state, [(hole, options)], done=False)
        return ranked[0]

    def is_done(self, state: str) -> float:
        _, p = self.batch(state, [], done=True)
        assert p is not None
        return p

    def batch(
        self, state: str, queries: Sequence[Query], done: bool
    ) -> tuple[list[list[tuple[Option, float]]], float | None]:
        """Varias elecciones (y opcionalmente la pregunta de parada) en una sola petición.

        Todas comparten el mismo estado (tarea + programa); cada pregunta lleva su hueco en
        las instrucciones. Las respuestas en caché no se vuelven a pedir.
        """
        from typesafe_sdk import Choice, Noul

        jstate, _ = self._state(state)
        base = (jstate["tarea"], jstate["programa"], self.criteria_style, self.model)
        results: list[list[tuple[Option, float]] | None] = []
        questions: dict[str, Any] = {}
        pending: dict[str, tuple[int, list[Option], list[str], tuple[object, ...]]] = {}
        for i, (hole, options) in enumerate(queries):
            key: tuple[object, ...] = (*base, "choice", hole, tuple((o.id, o.label) for o in options))
            hit = self._cache_get(key)
            if isinstance(hit, list):
                results.append(hit)
                continue
            results.append(None)
            name = f"q{i}"
            questions[name] = Choice(
                instructions=CHOOSE_INSTRUCTIONS.format(hole=hole), criteria=self._criteria(options)
            )
            pending[name] = (i, options, self._keys(options), key)
        done_p: float | None = None
        done_key = (*base, "done")
        if done:
            hit = self._cache_get(done_key)
            if isinstance(hit, float):
                done_p = hit
            else:
                questions["done"] = Noul(instructions=DONE_INSTRUCTIONS, criteria=DONE_CRITERIA)  # type: ignore[arg-type]
        if questions:
            kwargs: dict[str, Any] = {} if self.model is None else {"model": self.model}
            resp = self.client.system_one(state=jstate, questions=questions, **kwargs)
            self.requests += 1
            self.questions += len(questions)
            for name, (i, options, keys, ckey) in pending.items():
                probs = resp.choices[name].probabilities
                ranked = rank(options, [max(float(probs.get(k, 0.0)), 0.0) for k in keys])
                self._cache_put(ckey, ranked)
                results[i] = ranked
            if "done" in questions:
                done_p = float(resp.nouls["done"].noul)
                self._cache_put(done_key, done_p)
        return [r for r in results if r is not None], done_p

    def close(self) -> None:
        self.client.close()
