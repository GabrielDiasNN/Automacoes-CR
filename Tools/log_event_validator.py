"""Validador do contrato de evento de log do Hub (docs/log-event.schema.json).

Sem dependencia de `jsonschema` (evita mexer no lock pip-compile, fragil no
Windows). O schema JSON continua sendo o contrato humano e a fonte unica dos
enums; as regras condicionais sao aplicadas aqui.

Uso:
    python Tools/log_event_validator.py [--rollout] <arquivo.jsonl> [...]

`--rollout`: ignora linhas legadas (sem o campo `trace_id`, exclusivo do schema
novo) em vez de conta-las como violacao. Usado enquanto nem todas as automacoes
migraram.

Saida: relatorio por linha invalida em stderr; exit 0 se tudo valido, 1 se
houver ao menos uma violacao. O modo `warn` do gate e responsabilidade do
wrapper PowerShell (`Tools/Test-LogEventSchema.ps1`), nao deste script.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "log-event.schema.json"

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

REQUIRED_ENVELOPE = (
    "ts",
    "level",
    "component",
    "event",
    "automation",
    "exec_id",
    "trace_id",
    "message",
)


def _load_schema() -> dict[str, Any]:
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        schema: dict[str, Any] = json.load(handle)
    return schema


def _enum(schema: dict[str, Any], field: str) -> set[str]:
    return set(schema["properties"][field]["enum"])


class _Enums:  # pylint: disable=too-few-public-methods
    """Enums extraidos do schema JSON (fonte unica dos valores validos)."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self.level = _enum(schema, "level")
        self.component = _enum(schema, "component")
        self.event = _enum(schema, "event")
        self.step = _enum(schema, "step")
        self.allowed = set(schema["properties"].keys())


# Campos exigidos por evento, alem do envelope base.
_CONDITIONAL_REQUIRED: dict[str, tuple[str, ...]] = {
    "retry.attempt": ("step", "attempt", "max_attempts"),
    "step.end": ("step", "ok", "duration_ms"),
    "execution.end": ("outcome_code", "outcome_reason", "duration_ms", "steps"),
    "step.start": ("step",),
}


def _check_envelope(evt: dict[str, Any], enums: _Enums) -> list[str]:
    errs = [f"campo desconhecido: {k!r}" for k in evt if k not in enums.allowed]
    errs += [
        f"campo obrigatorio ausente: {f!r}" for f in REQUIRED_ENVELOPE if f not in evt
    ]
    if "ts" in evt and not _TS_RE.match(str(evt["ts"])):
        errs.append(f"ts fora do formato ISO-8601 UTC 'Z': {evt['ts']!r}")
    return errs


def _check_enums(evt: dict[str, Any], enums: _Enums) -> list[str]:
    errs: list[str] = []
    for field, allowed in (
        ("level", enums.level),
        ("component", enums.component),
        ("event", enums.event),
        ("step", enums.step),
    ):
        if field in evt and evt[field] not in allowed:
            errs.append(f"{field} invalido: {evt[field]!r}")
    return errs


def _check_conditionals(evt: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    event = evt.get("event")
    for field in _CONDITIONAL_REQUIRED.get(str(event), ()):
        if field not in evt:
            errs.append(f"event={event} exige {field!r}")
    if evt.get("step") == "custom" and "step_name" not in evt:
        errs.append("step=custom exige 'step_name'")
    return errs


def validate_event(evt: dict[str, Any], enums: _Enums) -> list[str]:
    """Retorna a lista de violacoes de um unico evento (vazia = valido)."""
    return (
        _check_envelope(evt, enums)
        + _check_enums(evt, enums)
        + _check_conditionals(evt)
    )


def validate_file(path: Path, enums: _Enums, rollout: bool = False) -> list[str]:
    problems: list[str] = []
    try:
        raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        return [f"{path}: nao foi possivel ler ({exc})"]

    for lineno, raw in enumerate(raw_lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            evt = json.loads(stripped)
        except json.JSONDecodeError as exc:
            if rollout:
                continue
            problems.append(f"{path}:{lineno}: JSON invalido ({exc.msg})")
            continue
        if not isinstance(evt, dict):
            if rollout:
                continue
            problems.append(f"{path}:{lineno}: evento nao e um objeto JSON")
            continue
        if rollout and "trace_id" not in evt:
            continue  # linha legada: fora do escopo do schema novo
        for err in validate_event(evt, enums):
            problems.append(f"{path}:{lineno}: {err}")
    return problems


def main(argv: list[str]) -> int:
    rollout = "--rollout" in argv
    files = [a for a in argv if a != "--rollout"]
    if not files:
        print(
            "uso: log_event_validator.py [--rollout] <arquivo.jsonl> ...",
            file=sys.stderr,
        )
        return 2
    enums = _Enums(_load_schema())
    all_problems: list[str] = []
    for arg in files:
        all_problems.extend(validate_file(Path(arg), enums, rollout=rollout))

    for problem in all_problems:
        print(problem, file=sys.stderr)
    print(
        f"log-event: {len(files)} arquivo(s), {len(all_problems)} violacao(oes).",
        file=sys.stderr,
    )
    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
