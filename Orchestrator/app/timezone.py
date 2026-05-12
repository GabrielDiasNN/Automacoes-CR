from datetime import datetime, timedelta

def get_now_local() -> datetime:
    """
    Retorna o datetime atual ajustado para Brasilia (18:xx).
    O SQLAlchemy/SQLite no Windows tende a tratar o horario local como UTC,
    causando uma exibicao de +3h (21:xx). Esta funcao compensa essa diferenca.
    """
    return datetime.now() - timedelta(hours=3)


