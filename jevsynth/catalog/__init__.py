from pathlib import Path

from jevsynth.catalog.model import Catalog, ClassInfo, Component, Param, TypeRef

STDLIB_JSON = Path(__file__).parent / "data" / "stdlib.json"


def load_stdlib() -> Catalog:
    """Catálogo de la stdlib ya construido (ver `python -m jevsynth.catalog.build`)."""
    return Catalog.load(STDLIB_JSON)


__all__ = ["STDLIB_JSON", "Catalog", "ClassInfo", "Component", "Param", "TypeRef", "load_stdlib"]
