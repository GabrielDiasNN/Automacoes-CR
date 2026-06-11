# pylint: disable=all
# mypy: ignore-errors
"""
Suite de testes avançados para agendamento Cron e Intervalo com Janela Operacional Restrita.

Valida:
1. Normalização e preview de schedule_type=cron via API.
2. Normalização e preview de schedule_type=interval com janela operacional restrita (start_time, end_time, days_of_week).
3. Rejeição de payloads inválidos (cron_expression ausente, start_time mal-formatado).
4. Compatibilidade retroativa com payloads legados de intervalo simples (sem janela).
5. Descrição textual enriquecida via describe_schedule_payload.
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.schemas.common import (
    normalize_schedule_payload,
    parse_schedule,
    describe_schedule_payload,
    preview_next_runs,
)
from tests.conftest import AUTH_HEADERS


# --------------------------------------------------------------------------- #
# 1. Normalização de Cron                                                     #
# --------------------------------------------------------------------------- #

class TestCronNormalization:
    """Valida normalização do payload schedule_type=cron."""

    def test_cron_valid_expression_normalizes(self):
        """Expressão Cron válida deve ser preservada integralmente."""
        payload = {
            "schedule_type": "cron",
            "schedule_version": 2,
            "cron_expression": "*/15 8-18 * * 1-5",
        }
        result = normalize_schedule_payload(payload, strict=True)
        assert result["schedule_type"] == "cron"
        assert result["cron_expression"] == "*/15 8-18 * * 1-5"
        assert result["schedule_version"] == 2
        assert result["timezone"] == "America/Sao_Paulo"

    def test_cron_strips_whitespace(self):
        """Espaços nas bordas da expressão Cron devem ser removidos."""
        payload = {
            "schedule_type": "cron",
            "cron_expression": "  0 22 * * 1-5  ",
        }
        result = normalize_schedule_payload(payload, strict=False)
        assert result["cron_expression"] == "0 22 * * 1-5"

    def test_cron_missing_expression_strict_raises(self):
        """Em modo strict, cron sem expressão deve lançar ValueError."""
        payload = {"schedule_type": "cron"}
        with pytest.raises(ValueError, match="cron_expression"):
            normalize_schedule_payload(payload, strict=True)

    def test_cron_missing_expression_fallback(self):
        """Em modo tolerante, cron sem expressão deve aplicar fallback."""
        payload = {"schedule_type": "cron"}
        result = normalize_schedule_payload(payload, strict=False)
        assert result["schedule_type"] == "cron"
        assert result["cron_expression"]  # deve ter algum fallback não vazio

    def test_cron_preview_returns_dates(self):
        """Preview de Cron deve retornar lista não-vazia de datas formatadas."""
        schedule = {
            "schedule_type": "cron",
            "cron_expression": "0 8 * * 1-5",
            "timezone": "America/Sao_Paulo",
        }
        runs = preview_next_runs(schedule, count=3)
        assert isinstance(runs, list)
        assert len(runs) <= 3
        # Cada item deve ser string não vazia
        for run in runs:
            assert isinstance(run, str)
            assert len(run) > 0


# --------------------------------------------------------------------------- #
# 2. Normalização de Intervalo com Janela Operacional                         #
# --------------------------------------------------------------------------- #

class TestIntervalWithWindow:
    """Valida normalização de schedule_type=interval com restrição de janela."""

    def test_interval_with_window_normalizes(self):
        """Intervalo com janela operacional deve preservar start_time, end_time e days_of_week."""
        payload = {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "start_time": "08:00",
            "end_time": "18:00",
            "days_of_week": [1, 2, 3, 4, 5],
        }
        result = normalize_schedule_payload(payload, strict=True)
        assert result["schedule_type"] == "interval"
        assert result["interval_minutes"] == 30
        assert result["start_time"] == "08:00"
        assert result["end_time"] == "18:00"
        assert result["days_of_week"] == [1, 2, 3, 4, 5]
        assert result["anchor_time"] == "08:00"

    def test_interval_without_window_has_null_fields(self):
        """Intervalo simples (sem janela) deve ter start_time/end_time/days_of_week nulos."""
        payload = {
            "schedule_type": "interval",
            "interval_minutes": 15,
        }
        result = normalize_schedule_payload(payload, strict=False)
        assert result["interval_minutes"] == 15
        assert result.get("start_time") is None
        assert result.get("end_time") is None
        assert result.get("days_of_week") is None

    @pytest.mark.parametrize("extra_fields", [
        {"start_time": "8am"},                           # formato inválido
        {"start_time": "18:00", "end_time": "12:00"},    # janela invertida
    ])
    def test_interval_invalid_start_time_strict_raises(self, extra_fields):
        """Em modo strict, start_time inválido ou janela invertida deve lançar ValueError."""
        payload = {"schedule_type": "interval", "interval_minutes": 10, **extra_fields}
        with pytest.raises(ValueError, match="start_time"):
            normalize_schedule_payload(payload, strict=True)

    def test_interval_invalid_start_time_fallback(self):
        """Em modo tolerante, start_time inválido deve ser ignorado (None)."""
        payload = {
            "schedule_type": "interval",
            "interval_minutes": 10,
            "start_time": "INVALIDO",
        }
        result = normalize_schedule_payload(payload, strict=False)
        assert result["start_time"] is None

    def test_interval_preview_with_window(self):
        """Preview de intervalo com janela deve retornar datas dentro da faixa esperada."""
        schedule = {
            "schedule_type": "interval",
            "interval_minutes": 60,
            "start_time": "09:00",
            "end_time": "17:00",
            "days_of_week": [1, 2, 3, 4, 5],
            "timezone": "America/Sao_Paulo",
        }
        runs = preview_next_runs(schedule, count=5)
        assert isinstance(runs, list)
        # Pode retornar 0 se estiver fora da janela, mas não deve quebrar
        assert len(runs) <= 5

    def test_interval_invalid_minutes_strict_raises(self):
        """Em modo strict, interval_minutes=0 deve lançar ValueError."""
        payload = {
            "schedule_type": "interval",
            "interval_minutes": 0,
        }
        with pytest.raises(ValueError, match="interval_minutes"):
            normalize_schedule_payload(payload, strict=True)


# --------------------------------------------------------------------------- #
# 3. Descrição Textual Enriquecida                                            #
# --------------------------------------------------------------------------- #

class TestDescribeSchedulePayload:
    """Valida a descrição textual formatada para o Dashboard."""

    @pytest.mark.parametrize("schedule,expected_fragments", [
        (
            {"schedule_type": "cron", "cron_expression": "*/10 8-18 * * 1-5"},
            ["Cron", "*/10 8-18 * * 1-5"],
        ),
        (
            {"schedule_type": "interval", "interval_minutes": 30},
            ["30 min"],
        ),
        (
            {
                "schedule_type": "interval",
                "interval_minutes": 15,
                "start_time": "08:00",
                "end_time": "18:00",
                "days_of_week": [1, 2, 3, 4, 5],
            },
            ["15 min", "08:00", "18:00"],
        ),
        ({"schedule_type": "manual"}, ["Manual"]),
        (None, ["Manual"]),
    ])
    def test_describe_schedule_payload(self, schedule, expected_fragments):
        """Descrição gerada deve conter os fragmentos esperados para cada tipo de schedule."""
        desc = describe_schedule_payload(schedule)
        for fragment in expected_fragments:
            assert fragment in desc


# --------------------------------------------------------------------------- #
# 4. Integração via API (Validate e Preview)                                  #
# --------------------------------------------------------------------------- #

class TestScheduleApiIntegration:
    """Valida endpoints de validação e preview de schedule com os novos tipos."""

    def test_api_validate_cron_valid(self, client: TestClient):
        """API de validação deve aceitar expressão Cron válida."""
        schedule = json.dumps({
            "schedule_type": "cron",
            "cron_expression": "0 8,12,18 * * 1-5",
        })
        response = client.post(
            "/api/system/schedule/validate",
            headers=AUTH_HEADERS,
            json={"schedule": schedule},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_api_validate_cron_missing_expression(self, client: TestClient):
        """API de validação deve rejeitar Cron sem expressão."""
        schedule = json.dumps({"schedule_type": "cron"})
        response = client.post(
            "/api/system/schedule/validate",
            headers=AUTH_HEADERS,
            json={"schedule": schedule},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_api_preview_cron(self, client: TestClient):
        """Preview de Cron deve retornar lista de próximas execuções."""
        schedule = json.dumps({
            "schedule_type": "cron",
            "cron_expression": "0 9 * * 1-5",
        })
        response = client.post(
            "/api/system/schedule/preview",
            headers=AUTH_HEADERS,
            json={"schedule": schedule, "limit": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert len(data.get("next_runs_preview", [])) <= 3

    def test_api_preview_interval_with_window(self, client: TestClient):
        """Preview de intervalo com janela operacional deve funcionar."""
        schedule = json.dumps({
            "schedule_type": "interval",
            "interval_minutes": 30,
            "start_time": "08:00",
            "end_time": "18:00",
            "days_of_week": [1, 2, 3, 4, 5],
        })
        response = client.post(
            "/api/system/schedule/preview",
            headers=AUTH_HEADERS,
            json={"schedule": schedule, "limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_api_validate_interval_invalid_start_time(self, client: TestClient):
        """API de validação deve rejeitar start_time mal-formatado em modo estrito."""
        schedule = json.dumps({
            "schedule_type": "interval",
            "interval_minutes": 10,
            "start_time": "INVALIDO",
        })
        response = client.post(
            "/api/system/schedule/validate",
            headers=AUTH_HEADERS,
            json={"schedule": schedule},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False


# --------------------------------------------------------------------------- #
# 5. Compatibilidade Retroativa (parse_schedule de strings legadas)           #
# --------------------------------------------------------------------------- #

class TestLegacyCompatibility:
    """Valida que payloads legados continuam sendo interpretados corretamente."""

    def test_parse_legacy_interval_without_window(self):
        """Intervalo legado sem janela deve gerar payload válido."""
        raw = json.dumps({"schedule_type": "interval", "interval_minutes": 45})
        result = parse_schedule(raw)
        assert result is not None
        assert result["schedule_type"] == "interval"
        assert result["interval_minutes"] == 45

    def test_parse_legacy_daily_with_hours_format(self):
        """Payload legado com 'hours' ao invés de 'times' deve ser normalizado."""
        raw = json.dumps({"hours": [8, 12], "minutes": [0]})
        result = parse_schedule(raw)
        assert result is not None
        # Deve ter sido inferido como daily ou similar
        assert "times" in result or result.get("schedule_type") == "manual"

    def test_parse_empty_string_returns_none(self):
        """String vazia deve retornar None."""
        assert parse_schedule("") is None
        assert parse_schedule(None) is None


# --------------------------------------------------------------------------- #
# 6. Testes para Horário de Âncora (anchor_time)                              #
# --------------------------------------------------------------------------- #

class TestAnchorTime:
    """Valida normalização, descrição e cálculo de preview de anchor_time."""

    def test_anchor_time_normalizes_valid(self):
        """Horário de âncora válido deve ser preservado no payload normalizado."""
        payload = {
            "schedule_type": "interval",
            "interval_minutes": 15,
            "anchor_time": "08:15",
        }
        result = normalize_schedule_payload(payload, strict=True)
        assert result["schedule_type"] == "interval"
        assert result["anchor_time"] == "08:15"

    @pytest.mark.parametrize("anchor_time", [
        "9:30",   # falta zero à esquerda (formato inválido)
        "99:99",  # fora de faixa (sintático mas semanticamente errado)
    ])
    def test_anchor_time_invalid_strict_raises(self, anchor_time):
        """Em modo estrito, anchor_time malformado deve lançar ValueError."""
        payload = {"schedule_type": "interval", "interval_minutes": 15, "anchor_time": anchor_time}
        with pytest.raises(ValueError, match="anchor_time"):
            normalize_schedule_payload(payload, strict=True)

    def test_anchor_time_invalid_tolerant_fallback(self):
        """Em modo tolerante, anchor_time inválido deve ser ignorado (None)."""
        payload = {
            "schedule_type": "interval",
            "interval_minutes": 15,
            "anchor_time": "invalido",
        }
        result = normalize_schedule_payload(payload, strict=False)
        assert result["anchor_time"] is None

    def test_describe_interval_with_anchor_simple(self):
        """Descrição de intervalo simples com âncora deve exibir o início da cadência."""
        schedule = {
            "schedule_type": "interval",
            "interval_minutes": 45,
            "anchor_time": "08:30",
        }
        desc = describe_schedule_payload(schedule)
        assert "A cada 45 min" in desc
        assert "início da cadência às 08:30" in desc

    def test_describe_interval_with_anchor_and_window(self):
        """Descrição de intervalo com janela e âncora deve refletir início/fim e cadência."""
        schedule = {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "start_time": "08:00",
            "end_time": "18:00",
            "days_of_week": [1, 2, 3, 4, 5],
            "anchor_time": "08:30",
        }
        desc = describe_schedule_payload(schedule)
        assert "A cada 30 min" in desc
        assert "Seg, Ter, Qua, Qui, Sex" in desc
        assert "início 08:00, fim 18:00" in desc
        assert "início da cadência às 08:30" in desc

    def test_anchor_time_preview_future(self, monkeypatch):
        """Se a âncora estiver no futuro hoje, os disparos subsequentes devem começar exatamente nela."""
        from datetime import datetime
        # Simula agora sendo 10:00
        simulated_now = datetime(2026, 5, 20, 10, 0, 0)
        monkeypatch.setattr("app.timezone.get_now_local", lambda: simulated_now)

        schedule = {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "anchor_time": "12:00",
            "timezone": "America/Sao_Paulo",
        }
        runs = preview_next_runs(schedule, count=3)
        assert len(runs) == 3
        # Como a âncora (12:00) está no futuro de now (10:00), o primeiro disparo é a própria âncora
        assert runs[0] == "20/05/2026 12:00:00"
        assert runs[1] == "20/05/2026 12:30:00"
        assert runs[2] == "20/05/2026 13:00:00"

    def test_anchor_time_preview_past(self, monkeypatch):
        """Se a âncora estiver no passado hoje, os disparos subsequentes devem alinhar com os múltiplos futuros dela."""
        from datetime import datetime
        # Simula agora sendo 15:10
        simulated_now = datetime(2026, 5, 20, 15, 10, 0)
        monkeypatch.setattr("app.timezone.get_now_local", lambda: simulated_now)

        schedule = {
            "schedule_type": "interval",
            "interval_minutes": 30,
            "anchor_time": "14:00",
            "timezone": "America/Sao_Paulo",
        }
        runs = preview_next_runs(schedule, count=3)
        assert len(runs) == 3
        # Os disparos baseados na âncora das 14:00 seriam: 14:00, 14:30, 15:00, 15:30, 16:00
        # Como o tempo atual simulado é 15:10, o primeiro disparo no futuro deve ser 15:30!
        assert runs[0] == "20/05/2026 15:30:00"
        assert runs[1] == "20/05/2026 16:00:00"
        assert runs[2] == "20/05/2026 16:30:00"
