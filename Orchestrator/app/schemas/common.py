"""
Módulo de utilitários e validadores comuns para os schemas Pydantic.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from .. import timezone
from ..timezone import to_br_timezone
from .schedule_rules import (
    first_interval_candidate,
    normalize_hhmm,
    parse_hhmm,
    ui_day_to_python_weekday,
)

# ---------------------------------------------------------------------------
# Validadores e Utilitários de Nomes e Caminhos
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9 à-úÀ-ÚçÇ_\-\[\]\(\)\.]{2,100}$")
_DANGEROUS_PATH_PATTERNS = ["..", "//", "\\\\", "%", "\x00"]


def format_dt_br(val: Any) -> Any:
    """Converte qualquer formato de data para o padrão brasileiro (DD/MM/YYYY HH:MM:SS)."""
    dt = parse_dt_br(val)
    if dt is None:
        return val
    br_dt = to_br_timezone(dt)
    if br_dt is None:
        return val
    return br_dt.strftime("%d/%m/%Y %H:%M:%S")


def parse_dt_br(val: Any) -> datetime | None:  # pylint: disable=too-many-return-statements
    """Converte datas em datetime naive no fuso do Brasil quando possível."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return to_br_timezone(val)
    if not isinstance(val, str):
        return None

    value = val.strip()
    if not value:
        return None

    try:
        br_match = re.match(
            r"^(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$",
            value,
        )
        if br_match:
            return datetime(
                int(br_match.group(3)),
                int(br_match.group(2)),
                int(br_match.group(1)),
                int(br_match.group(4) or 0),
                int(br_match.group(5) or 0),
                int(br_match.group(6) or 0),
            )

        normalized = value.replace(" ", "T")
        iso_dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if iso_dt.tzinfo is not None:
            return to_br_timezone(iso_dt)
        return iso_dt
    except (ValueError, TypeError, AttributeError):
        try:
            return datetime.strptime(value.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, AttributeError):
            return None


def _validate_safe_name(v: str) -> str:
    if not _SAFE_NAME_RE.match(v):
        raise ValueError("Nome inválido (2-100 chars, caracteres seguros).")
    return v.strip()


def _validate_script_path(v: str) -> str:
    for pattern in _DANGEROUS_PATH_PATTERNS:
        if pattern in v:
            raise ValueError(f"Caminho proibido: '{pattern}'")
    return v


def _validate_schedule(v: str | None) -> str | None:
    if not v:
        return None
    try:
        obj = json.loads(v.replace("'", '"'))
    except (ValueError, TypeError) as exc:
        raise ValueError("Schedule deve ser JSON válido.") from exc

    if not isinstance(obj, dict):
        raise ValueError("Schedule deve ser um objeto JSON.")

    normalized = normalize_schedule_payload(obj, strict=True)
    return json.dumps(normalized, separators=(",", ":"))


def _validate_schedule_tolerant(v: str | None) -> str | None:
    if not v:
        return None
    try:
        obj = json.loads(v.replace("'", '"'))
    except (ValueError, TypeError):
        return json.dumps(
            {
                "schedule_version": 2,
                "schedule_type": "manual",
                "timezone": "America/Sao_Paulo",
            },
            separators=(",", ":"),
        )

    if not isinstance(obj, dict):
        return json.dumps(
            {
                "schedule_version": 2,
                "schedule_type": "manual",
                "timezone": "America/Sao_Paulo",
            },
            separators=(",", ":"),
        )

    normalized = normalize_schedule_payload(obj, strict=False)
    return json.dumps(normalized, separators=(",", ":"))


def _normalized_time_list(times: list[dict[str, Any]]) -> list[dict[str, int]]:
    items: list[dict[str, int]] = []
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
    uniq: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in items:
        key = (item["h"], item["m"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def _normalize_days(days: list[Any] | None) -> list[int]:
    if days is None:
        return []
    if not isinstance(days, list):
        raise ValueError("daysOfWeek deve ser uma lista.")
    norm = sorted(set(days))
    if any(not isinstance(day, int) or day < 0 or day > 6 for day in norm):
        raise ValueError("daysOfWeek deve conter inteiros entre 0 e 6.")
    return norm


def _ui_day_to_python_weekday(day: int) -> int:
    return ui_day_to_python_weekday(day)


def _normalize_legacy_days(obj: dict[str, Any], strict: bool, logger: Any) -> list[int]:
    try:
        return _normalize_days(obj.get("daysOfWeek", []))
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        if strict:
            raise
        logger.warning(
            "Erro na validação do daysOfWeek legado: %s. Aplicando fallback de todos os dias.",
            str(e),
        )
        return [1, 2, 3, 4, 5]


def _normalize_legacy_times_from_hours(
    obj: dict[str, Any], strict: bool, logger: Any
) -> list[dict[str, int]]:
    hours = obj.get("hours", [])
    minutes = obj.get("minutes", [0])

    # Fallbacks preventivos se as listas vierem vazias
    if not hours:
        if strict:
            raise ValueError("times deve conter ao menos um horário válido.")
        logger.warning(
            "Lista de 'hours' vazia recebida na agenda legada. Aplicando fallback de hora 08:00."
        )
        hours = [8]
    if not minutes:
        if strict:
            raise ValueError("times deve conter ao menos um horário válido.")
        logger.warning(
            "Lista de 'minutes' vazia recebida na agenda legada. Aplicando fallback de minuto 0."
        )
        minutes = [0]

    if not isinstance(hours, list) or not isinstance(minutes, list):
        if strict:
            raise ValueError("hours e minutes devem ser listas.")
        hours = [8] if not isinstance(hours, list) else hours
        minutes = [0] if not isinstance(minutes, list) else minutes

    raw_times = []
    for hour in hours:
        for minute in minutes:
            raw_times.append({"h": hour, "m": minute})
    try:
        return _normalized_time_list(raw_times)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        if strict:
            raise
        logger.warning(
            "Erro ao normalizar horários legados: %s. Usando fallback de horário 08:00.",
            str(e),
        )
        return [{"h": 8, "m": 0}]


def _normalize_legacy_schedule(
    obj: dict[str, Any], strict: bool, logger: Any
) -> dict[str, Any]:
    days = _normalize_legacy_days(obj, strict, logger)

    times = obj.get("times")
    if times is not None:
        try:
            norm_times = _normalized_time_list(times)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            if strict:
                raise
            logger.warning(
                "Erro na validação do times legado: %s. Aplicando fallback de horário (08:00).",
                str(e),
            )
            norm_times = [{"h": 8, "m": 0}]
    else:
        norm_times = _normalize_legacy_times_from_hours(obj, strict, logger)

    if not norm_times:
        if strict:
            raise ValueError("times deve conter ao menos um horário válido.")
        logger.warning(
            "Nenhum horário válido gerado na agenda legada. Aplicando fallback de horário 08:00."
        )
        norm_times = [{"h": 8, "m": 0}]

    return {
        "schedule_version": 2,
        "schedule_type": "weekly",
        "timezone": "America/Sao_Paulo",
        "days_of_week": days if days else [1, 2, 3, 4, 5],
        "times": norm_times,
    }


def _normalize_interval_schedule(
    obj: dict[str, Any], base: dict[str, Any], strict: bool, logger: Any
) -> dict[str, Any]:
    val = obj.get("interval_minutes")
    if not isinstance(val, int) or val < 1 or val > 1440:
        if strict:
            raise ValueError("interval_minutes deve estar entre 1 e 1440.")
        logger.warning(
            "interval_minutes '%s' inválido. Usando fallback de 60 minutos.", val
        )
        val = 60
    base["interval_minutes"] = val

    # Novas propriedades de restrição de janela
    start_t = normalize_hhmm(obj.get("start_time"), "start_time", strict, logger)
    base["start_time"] = start_t

    end_t = normalize_hhmm(obj.get("end_time"), "end_time", strict, logger)
    base["end_time"] = end_t

    interval_days = obj.get("days_of_week")
    if interval_days is not None:
        try:
            base["days_of_week"] = _normalize_days(interval_days)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            if strict:
                raise
            logger.warning(
                "Erro na validação de days_of_week de intervalo restrito: %s",
                str(e),
            )
            base["days_of_week"] = None
    else:
        base["days_of_week"] = None

    anchor_t = normalize_hhmm(obj.get("anchor_time"), "anchor_time", strict, logger)
    base["anchor_time"] = anchor_t

    if start_t and end_t:
        start_h, start_m = parse_hhmm(start_t)
        end_h, end_m = parse_hhmm(end_t)
        if (start_h, start_m) > (end_h, end_m):
            if strict:
                raise ValueError("start_time não pode ser maior que end_time.")
            logger.warning(
                "Janela de intervalo inválida (%s > %s). Removendo end_time.",
                start_t,
                end_t,
            )
            base["end_time"] = None

    if base["start_time"] and not base["anchor_time"]:
        base["anchor_time"] = base["start_time"]

    return base


def _normalize_once_schedule(
    obj: dict[str, Any], base: dict[str, Any], strict: bool, logger: Any
) -> dict[str, Any]:
    run_at = obj.get("run_at")
    if not isinstance(run_at, str) or not run_at.strip():
        if strict:
            raise ValueError("run_at é obrigatório para schedule_type=once.")
        fallback_time = (timezone.get_now_local() + timedelta(hours=1)).isoformat()
        logger.warning(
            "run_at ausente para cadência única. Aplicando fallback para daqui 1 hora: %s",
            fallback_time,
        )
        run_at = fallback_time
    base["run_at"] = run_at.strip()
    return base


def _normalize_periodic_times(
    obj: dict[str, Any], strict: bool, logger: Any
) -> list[dict[str, int]]:
    try:
        times = _normalized_time_list(obj.get("times") or [])
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        if strict:
            raise
        logger.warning(
            "Erro ao ler lista 'times' moderna: %s. Aplicando fallback de horário (08:00).",
            str(e),
        )
        times = []

    if not times:
        if strict:
            raise ValueError("times deve conter ao menos um horário.")
        logger.warning(
            "Nenhum horário definido no campo 'times'. Aplicando fallback preventivo de 08:00."
        )
        times = [{"h": 8, "m": 0}]
    return times


def _normalize_weekly_schedule(
    obj: dict[str, Any], base: dict[str, Any], strict: bool, logger: Any
) -> dict[str, Any]:
    try:
        days = _normalize_days(obj.get("days_of_week"))
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        if strict:
            raise
        logger.warning(
            "Erro na validação do days_of_week semanal: %s. Aplicando fallback Segunda a Sexta.",
            str(e),
        )
        days = []
    if not days:
        if strict:
            raise ValueError("days_of_week é obrigatório para schedule_type=weekly.")
        logger.warning(
            "days_of_week ausente ou vazio para weekly. Usando fallback de Segunda a Sexta."
        )
        days = [1, 2, 3, 4, 5]
    base["days_of_week"] = days
    return base


def _normalize_monthly_schedule(
    obj: dict[str, Any], base: dict[str, Any], strict: bool, logger: Any
) -> dict[str, Any]:
    days_of_month = obj.get("days_of_month")
    if not isinstance(days_of_month, list) or not days_of_month:
        if strict:
            raise ValueError("days_of_month é obrigatório para schedule_type=monthly.")
        logger.warning(
            "days_of_month ausente ou vazio para monthly. Usando fallback de dia 1."
        )
        norm_month = [1]
    else:
        try:
            norm_month = sorted(set(days_of_month))
            if any(
                not isinstance(day, int) or day < 1 or day > 31 for day in norm_month
            ):
                raise ValueError("Contém valores fora do intervalo 1-31.")
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            if strict:
                raise
            logger.warning(
                "Erro na validação dos dias do mês: %s. Aplicando fallback de dia 1.",
                str(e),
            )
            norm_month = [1]

    base["days_of_month"] = norm_month
    return base


def _normalize_periodic_schedule(
    obj: dict[str, Any],
    base: dict[str, Any],
    schedule_type: str,
    strict: bool,
    logger: Any,
) -> dict[str, Any]:
    # Para daily, weekly e monthly, validamos 'times' com fallback preventivo
    base["times"] = _normalize_periodic_times(obj, strict, logger)

    if schedule_type == "daily":
        return base
    if schedule_type == "weekly":
        return _normalize_weekly_schedule(obj, base, strict, logger)
    return _normalize_monthly_schedule(obj, base, strict, logger)


def normalize_schedule_payload(  # pylint: disable=too-many-return-statements
    obj: dict[str, Any], strict: bool = True
) -> dict[str, Any]:
    logger = logging.getLogger("orchestrator.schemas")

    if not isinstance(obj, dict):
        if strict:
            raise ValueError("Schedule deve ser um objeto JSON.")
        logger.warning(
            "Schedule inválido recebido (esperava dict, recebeu %s). Aplicando fallback manual.",
            type(obj).__name__,
        )
        return {
            "schedule_version": 2,
            "schedule_type": "manual",
            "timezone": "America/Sao_Paulo",
        }

    # Legado: daysOfWeek + times/hours/minutes
    if "schedule_type" not in obj and "scheduleType" not in obj:
        return _normalize_legacy_schedule(obj, strict, logger)

    schedule_type = (
        str(obj.get("schedule_type") or obj.get("scheduleType") or "").lower().strip()
    )
    valid_types = {"manual", "daily", "weekly", "monthly", "interval", "once", "cron"}
    if schedule_type not in valid_types:
        if strict:
            raise ValueError("schedule_type inválido.")
        logger.warning(
            "schedule_type '%s' inválido. Aplicando fallback para 'manual'.",
            schedule_type,
        )
        schedule_type = "manual"

    timezone_name = str(obj.get("timezone") or "America/Sao_Paulo")
    base: dict[str, Any] = {
        "schedule_version": 2,
        "schedule_type": schedule_type,
        "timezone": timezone_name,
    }

    if schedule_type == "manual":
        return base
    if schedule_type == "cron":
        expr = obj.get("cron_expression")
        if not isinstance(expr, str) or not expr.strip():
            if strict:
                raise ValueError(
                    "cron_expression é obrigatório para schedule_type=cron."
                )
            logger.warning(
                "cron_expression ausente ou inválida para cadência cron. Usando fallback."
            )
            expr = "0 8 * * 1-5"
        base["cron_expression"] = expr.strip()
        return base
    if schedule_type == "interval":
        return _normalize_interval_schedule(obj, base, strict, logger)
    if schedule_type == "once":
        return _normalize_once_schedule(obj, base, strict, logger)

    return _normalize_periodic_schedule(obj, base, schedule_type, strict, logger)


def parse_schedule(v: str | None) -> dict[str, Any] | None:
    if not v:
        return None
    try:
        obj = json.loads(v.replace("'", '"'))
    except (ValueError, TypeError):
        return {
            "schedule_version": 2,
            "schedule_type": "manual",
            "timezone": "America/Sao_Paulo",
        }
    return normalize_schedule_payload(obj, strict=False)


def describe_schedule_payload(  # pylint: disable=too-many-return-statements
    schedule: dict[str, Any] | None,
) -> str:
    if not schedule:
        return "Manual"
    stype = schedule.get("schedule_type")
    if stype == "manual":
        return "Manual"
    if stype == "cron":
        return f"Cron: {schedule.get('cron_expression', '')}"
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
        min_lbl = f"A cada {schedule.get('interval_minutes', 0)} min"
        start_t = schedule.get("start_time")
        end_t = schedule.get("end_time")
        days = schedule.get("days_of_week")
        anchor_t = schedule.get("anchor_time")

        anchor_suffix = f", início da cadência às {anchor_t}" if anchor_t else ""

        if start_t or end_t or days:
            day_names = {
                0: "Dom",
                1: "Seg",
                2: "Ter",
                3: "Qua",
                4: "Qui",
                5: "Sex",
                6: "Sáb",
            }
            day_lbl = (
                ", ".join(day_names.get(d, str(d)) for d in days) if days else "Todos"
            )
            time_lbl = f"início {start_t or '00:00'}"
            if end_t:
                time_lbl += f", fim {end_t}"
            return f"{min_lbl} ({day_lbl}, {time_lbl}{anchor_suffix})"

        if anchor_t:
            return f"{min_lbl} (início da cadência às {anchor_t})"
        return min_lbl
    if stype == "once":
        return f"Execução única em {schedule.get('run_at', '-')}"
    return "Configurada"


def _preview_cron_runs(
    schedule: dict[str, Any], now: datetime, count: int
) -> list[str]:
    out: list[str] = []
    try:
        trigger = CronTrigger.from_crontab(
            schedule.get("cron_expression"),
            timezone=schedule.get("timezone", "America/Sao_Paulo"),
        )
        curr = now
        for _ in range(count):
            nxt = trigger.get_next_fire_time(None, curr)
            if not nxt:
                break
            out.append(format_dt_br(nxt))
            curr = nxt
    except (ValueError, TypeError, KeyError):
        pass
    return out


def _interval_window_runs(
    schedule: dict[str, Any], initial_candidate: datetime, step: int, count: int
) -> list[str]:
    out: list[str] = []
    start_t = schedule.get("start_time")
    end_t = schedule.get("end_time")
    days = schedule.get("days_of_week")
    py_days = {_ui_day_to_python_weekday(int(day)) for day in days} if days else None

    def is_valid_time(dt: datetime) -> bool:
        if py_days is not None and dt.weekday() not in py_days:
            return False
        if start_t:
            sh, sm = parse_hhmm(start_t)
            if dt.hour < sh or (dt.hour == sh and dt.minute < sm):
                return False
        if end_t:
            eh, em = parse_hhmm(end_t)
            if dt.hour > eh or (dt.hour == eh and dt.minute > em):
                return False
        return True

    candidate = initial_candidate
    cutoff = initial_candidate + timedelta(days=90)

    while len(out) < count and candidate < cutoff:
        if is_valid_time(candidate):
            out.append(format_dt_br(candidate))
        candidate += timedelta(minutes=step)
    return out


def _preview_interval_runs(
    schedule: dict[str, Any], now: datetime, count: int
) -> list[str]:
    step = int(schedule.get("interval_minutes", 1))
    anchor_t = schedule.get("anchor_time")
    initial_candidate = first_interval_candidate(now, step, anchor_t)

    has_window = schedule.get("start_time") or schedule.get("end_time") or schedule.get(
        "days_of_week"
    )
    if not has_window:
        return [
            format_dt_br(initial_candidate + timedelta(minutes=idx * step))
            for idx in range(count)
        ]

    return _interval_window_runs(schedule, initial_candidate, step, count)


def _preview_once_run(schedule: dict[str, Any], now: datetime) -> list[str]:
    out: list[str] = []
    run_at = schedule.get("run_at")
    try:
        dt = parse_dt_br(run_at)
        if dt is None:
            raise ValueError("run_at inválido.")
        if dt >= now:
            out.append(format_dt_br(dt))
    except (ValueError, TypeError):
        pass
    return out


def _preview_periodic_runs(
    schedule: dict[str, Any], now: datetime, count: int, stype: str | None
) -> list[str]:
    out: list[str] = []
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


def preview_next_runs(schedule: dict[str, Any] | None, count: int = 5) -> list[str]:
    if not schedule:
        return []
    now = timezone.get_now_local().replace(second=0, microsecond=0)
    stype = schedule.get("schedule_type")
    if stype == "cron":
        return _preview_cron_runs(schedule, now, count)
    if stype == "interval":
        return _preview_interval_runs(schedule, now, count)
    if stype == "once":
        return _preview_once_run(schedule, now)
    return _preview_periodic_runs(schedule, now, count, stype)
