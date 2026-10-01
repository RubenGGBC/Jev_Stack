"""Ejecución aislada del código generado: subproceso, timeout y sin red."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

from jevsynth.eval.tasks import EvalTask

# Se ejecuta antes del código generado: corta la red a nivel de socket.
_PREAMBLE = textwrap.dedent(
    """
    import socket as _socket

    def _no_network(*args, **kwargs):
        raise OSError("red deshabilitada en el runner")

    _socket.socket = _no_network
    _socket.create_connection = _no_network
    _socket.getaddrinfo = _no_network
    del _socket
    """
)


@dataclass
class RunResult:
    passed: bool
    error: str = ""
    stdout: str = ""


def run_code(code: str, task: EvalTask, timeout: float = 10.0) -> RunResult:
    """Ejecuta `code` y los tests de `task` en un directorio temporal."""
    with tempfile.TemporaryDirectory(prefix="jevsynth-") as tmp:
        d = Path(tmp)
        for name, content in task.files.items():
            path = d / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        harness = [_PREAMBLE, code]
        if task.tests:
            harness.append("\n".join(task.tests))
        (d / "main.py").write_text("\n".join(harness))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "main.py"],
                cwd=d,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={"PYTHONHASHSEED": "0", "PATH": "/usr/bin:/bin"},
            )
        except subprocess.TimeoutExpired:
            return RunResult(False, "timeout")
        if proc.returncode != 0:
            err = proc.stderr.strip().splitlines()
            return RunResult(False, err[-1] if err else f"código de salida {proc.returncode}", proc.stdout)
        if task.stdout is not None and proc.stdout.strip() != task.stdout.strip():
            return RunResult(
                False, f"stdout {json.dumps(proc.stdout.strip())} != {json.dumps(task.stdout)}", proc.stdout
            )
        return RunResult(True, "", proc.stdout)
