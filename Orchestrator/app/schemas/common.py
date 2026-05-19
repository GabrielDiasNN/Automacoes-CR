# pylint: disable=all
# mypy: ignore-errors
"""
Módulo de utilitários e validadores comuns para os schemas Pydantic.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# Validadores e Utilitários de Nomes e Caminhos
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9 à-úÀ-ÚçÇ_\-\[\]\(\)\.]{2,100}$")
_DANGEROUS_PATH_PATTERNS = ["..", "//", "\\\\", "%", "\x00"]


def format_dt_br(val: Any) -> Any:
    """Converte qualquer formato de data para o padrão brasileiro (DD/MM/YYYY HH:MM:SS)."""
    from ..timezone import to_br_timezone

    if val is None:
        return None

    # Se for datetime, garante que seja naive BRT antes de formatar
    if isinstance(val, datetime):
        dt = to_br_timezone(val)
        return dt.strftime("%d/%m/%Y %H:%M:%S")

    if isinstance(val, str):
        try:
            # ISO format (ex: 2023-01-01T12:00:00Z ou 2023-01-01T12:00:00)
            if "T" in val:
                # Remove Z se existir para evitar que fromisoformat force UTC aware
                clean_val = val.replace("Z", "")
                dt = datetime.fromisoformat(clean_val)
                # Se for aware, converte para naive BRT
                if dt.tzinfo is not None:
                    dt = to_br_timezone(dt)
                return dt.strftime("%d/%m/%Y %H:%M:%S")

            # SQLite format (ex: 2023-01-01 12:00:00)
            dt = datetime.strptime(val.split(".")[0], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError, AttributeError):
            return val
    return val


def _validate_safe_name(v: str) -> str:
    if not _SAFE_NAME_RE.match(v):
        raise ValueError("Nome inválido (2-100 chars, caracteres seguros).")
    return v.strip()


def _validate_script_path(v: str) -> str:
    for pattern in _DANGEROUS_PATH_PATTERNS:
        if pattern in v:
            raise ValueError(f"Caminho proibido: '{pattern}'")
    return v


def _validate_schedule(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    try:
        obj = json.loads(v.replace("'", '"'))
    except Exception:
        raise ValueError("Schedule deve ser JSON válido.")

    if not isinstance(obj, dict):
        raise ValueError("Schedule deve ser um objeto JSON.")

    normalized = normalize_schedule_payload(obj)
    return json.dumps(normalized, separators=(",", ":"))


def _normalized_time_list(times: List[dict]) -> List[dict]:
    items = []
    for item in times:
        if not isinstance(item, dict):
            raise ValueError("Cada item de times deve ser objeto com h e m.")
        hour = item.get("h")
        minute = item.get("m")
        if not isinstance(hour, int) or hour < 0 or hour > 23:
            raise ValueError("times[].h deve estar entre 0 e 23.")
        if not isinstance(minute, int) or minute < 0 or minute > 59:
            raise ValueError("times[].m deve estar entre 0 e 59.")
        items.append({"h": hour, "m": minute})
    items.sort(key=lambda x: (x["h"], x["m"]))
    uniq = []
    seen = set()
    for item in items:
        key = (item["h"], item["m"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def _normalize_days(days: Optional[List]) -> List[int]:
    if days is None:
        return []
    if not isinstance(days, list):
        raise ValueError("daysOfWeek deve ser uma lista.")
    norm = sorted(set(days))
    if any(not isinstance(day, int) or day < 0 or day > 6 for day in norm):
        raise ValueError("daysOfWeek deve conter inteiros entre 0 e 6.")
    return norm


def _ui_day_to_python_weekday(day: int) -> int:
    # Contrato UI/legado: 0=Dom, 1=Seg ... 6=Sáb
    # datetime.weekday(): 0=Seg ... 6=Dom
    return (day + 6) % 7


def normalize_schedule_payload(obj: dict) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("Schedule deve ser um objeto JSON.")
    # Legado: daysOfWeek + times/hours/minutes
    if "schedule_type" not in obj and "scheduleType" not in obj:
        days = _normalize_days(obj.get("daysOfWeek", []))
        times = obj.get("times")
        if times is not None:
            norm_times = _normalized_time_list(times)
        else:
            hours = obj.get("hours", [])
            minutes = obj.get("minutes", [0])
            if not isinstance(hours, list) or not isinstance(minutes, list):
                raise ValueError("hours e minutes devem ser listas.")
            raw_times = []
            for hour in hours:
                for minute in minutes:
                    raw_times.append({"h": hour, "m": minute})
            norm_times = _normalized_time_list(raw_times)
        if not norm_times:
            raise ValueError("times deve conter ao menos um horário válido.")
        return {
            "schedule_version": 2,
            "schedule_type": "weekly",
            "timezone": "America/Sao_Paulo",
            "days_of_week": days,
            "times": norm_times,
        }

    schedule_type = (
        str(obj.get("schedule_type") or obj.get("scheduleType") or "").lower().strip()
    )
    valid_types = {"manual", "daily", "weekly", "monthly", "interval", "once"}
    if schedule_type not in valid_types:
        raise ValueError("schedule_type inválido.")

    timezone_name = str(obj.get("timezone") or "America/Sao_Paulo")
    base = {
        "schedule_version": 2,
        "schedule_type": schedule_type,
        "timezone": timezone_name,
    }

    if schedule_type == "manual":
        return base
    if schedule_type == "interval":
        val = obj.get("interval_minutes")
        if not isinstance(val, int) or val < 1 or val > 1440:
            raise ValueError("interval_minutes deve estar entre 1 e 1440.")
        base["interval_minutes"] = val
        return base
    if schedule_type == "once":
        run_at = obj.get("run_at")
        if not isinstance(run_at, str) or not run_at.strip():
            raise ValueError("run_at é obrigatório para schedule_type=once.")
        base["run_at"] = run_at.strip()
        return base

    times = _normalized_time_list(obj.get("times") or [])
    if not times:
        raise ValueError("times deve conter ao menos um horário.")
    base["times"] = times

    if schedule_type == "daily":
        return base
    if schedule_type == "weekly":
        days = _normalize_days(obj.get("days_of_week"))
        if not days:
            raise ValueError("days_of_week é obrigatório para schedule_type=weekly.")
        base["days_of_week"] = days
        return base

    days_of_month = obj.get("days_of_month")
    if not isinstance(days_of_month, list) or not days_of_month:
        raise ValueError("days_of_month é obrigatório para schedule_type=monthly.")
    norm_month = sorted(set(days_of_month))
    if any(not isinstance(day, int) or day < 1 or day > 31 for day in norm_month):
        raise ValueError("days_of_month deve conter inteiros entre 1 e 31.")
    base["days_of_month"] = norm_month
    return base


def parse_schedule(v: Optional[str]) -> Optional[dict]:
    if not v:
        return None
    obj = json.loads(v.replace("'", '"'))
    return normalize_schedule_payload(obj)


def describe_schedule_payload(schedule: Optional[dict]) -> str:
    if not schedule:
        return "Manual"
    stype = schedule.get("schedule_type")
    if stype == "manual":
        return "Manual"
    if stype == "daily":
        times = schedule.get("times", [])
        return "Diário às " + ", ".join(f"{t['h']:02d}:{t['m']:02d}" for t in times)
    if stype == "weekly":
        day_names = {
            0: "Dom",
            1: "Seg",
            2: "Ter",
            3: "Qua",
            4: "Qui",
            5: "Sex",
            6: "Sáb",
        }
        days = schedule.get("days_of_week", [])
        times = schedule.get("times", [])
        day_label = (
            ", ".join(day_names.get(d, str(d)) for d in days)
            if days
            else "Todos os dias"
        )
        time_label = ", ".join(f"{t['h']:02d}:{t['m']:02d}" for t in times)
        return f"Semanal: {day_label} às {time_label}"
    if stype == "monthly":
        days = schedule.get("days_of_month", [])
        times = schedule.get("times", [])
        return f"Mensal dia(s) {', '.join(str(d) for d in days)} às " + ", ".join(
            f"{t['h']:02d}:{t['m']:02d}" for t in times
        )
    if stype == "interval":
        return f"A cada {schedule.get('interval_minutes', 0)} min"
    if stype == "once":
        return f"Execução única em {schedule.get('run_at', '-')}"
    return "Configurada"


def preview_next_runs(schedule: Optional[dict], count: int = 5) -> List[str]:
    if not schedule:
        return []
    from ..timezone import get_now_local

    now = get_now_local().replace(second=0, microsecond=0)
    out = []
    stype = schedule.get("schedule_type")
    if stype == "interval":
        step = int(schedule.get("interval_minutes", 1))
        start = now + timedelta(minutes=step)
        for idx in range(count):
            out.append(format_dt_br(start + timedelta(minutes=idx * step)))
        return out
    if stype == "once":
        run_at = schedule.get("run_at")
        try:
            dt = datetime.fromisoformat(str(run_at).replace("Z", ""))
            if dt >= now:
                out.append(format_dt_br(dt))
        except Exception:
            pass
        return out
    # Para cadências baseadas em horário, buscar próxima semana/mês por varredura simples.
    candidate = now
    max_scan_days = 62
    while len(out) < count and max_scan_days > 0:
        candidate += timedelta(minutes=1)
        max_scan_days -= 1 if candidate.hour == 0 and candidate.minute == 0 else 0
        times = schedule.get("times", [])
        hm = {(t["h"], t["m"]) for t in times}
        if (candidate.hour, candidate.minute) not in hm:
            continue
        if stype == "daily":
            out.append(format_dt_br(candidate))
            continue
        if stype == "weekly":
            days = set(schedule.get("days_of_week", []))
            py_days = {_ui_day_to_python_weekday(int(day)) for day in days}
            if candidate.weekday() in py_days:
                out.append(format_dt_br(candidate))
            continue
        if stype == "monthly":
            days = set(schedule.get("days_of_month", []))
            if candidate.day in days:
                out.append(format_dt_br(candidate))
    return out
