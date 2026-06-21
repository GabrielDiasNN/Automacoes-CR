from datetime import datetime

import pytz


def get_now_local() -> datetime:
    """
    Retorna o datetime atual no fuso horario de Brasilia (GMT-3).
    Garante explicitamente que o fuso usado e America/Sao_Paulo,
    independentemente de como o SO esta configurado, e retorna naive.
    Isso previne regressoes de fuso horario.
    """
    tz_br = pytz.timezone("America/Sao_Paulo")
    return datetime.now(tz_br).replace(tzinfo=None)


def to_br_timezone(dt: datetime) -> datetime:
    """
    Garante que o datetime seja naive e em Brasilia.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt

    # Se aware, converte para local e remove tzinfo
    tz_br = pytz.timezone("America/Sao_Paulo")
    dt_br = dt.astimezone(tz_br)
    return dt_br.replace(tzinfo=None)
