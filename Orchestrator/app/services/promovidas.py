"""Servicos de leitura snapshot-first de consultas promovidas e automacoes (nunca abre Oracle)."""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .domain_errors import DomainRuleError

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SAFE_PNG_RE = re.compile(r"^[A-Za-z0-9._-]+\.png$")
_TZ_BR = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class _ArquivosAutomacao:
    """Arquivos locais de resultado, estado e cards de uma automacao."""

    result_file: str | None = None
    state_file: str | None = None
    cards_manifest: str | None = None
    cards_dirs: tuple[str, ...] = ("images", "cards")


@dataclass(frozen=True)
class _AutomacaoSnapshotSpec:
    """Especificacao de leitura snapshot-first de uma automacao standalone."""

    slug: str
    codigo: str
    nome: str
    titulo: str
    setor: str
    pasta: str
    arquivos: _ArquivosAutomacao


_AUTOMACOES_SPECS: tuple[_AutomacaoSnapshotSpec, ...] = (
    _AutomacaoSnapshotSpec(
        slug="obs-paradas-fase",
        codigo="OBP-04",
        nome="OBs Paradas Fase",
        titulo="OBs Paradas por Fase (Beneficiamento)",
        setor="Beneficiamento & Fases",
        pasta="OBs Paradas Fase",
        arquivos=_ArquivosAutomacao(
            result_file="obs_result.json",
            cards_manifest="phase_cards.json",
            cards_dirs=("images",),
        ),
    ),
    _AutomacaoSnapshotSpec(
        slug="obs-fluxo-sem-tingimento",
        codigo="OFST-06",
        nome="OBs Fluxo Sem Tingimento",
        titulo="OBs Fluxo 204 Prontas p/ Montagem (Dep. 95)",
        setor="Expedição & Tinturaria",
        pasta="OBs Fluxo Sem Tingimento",
        arquivos=_ArquivosAutomacao(
            result_file="ofst_result.json",
            cards_manifest="cards_manifest.json",
            cards_dirs=(".",),
        ),
    ),
    _AutomacaoSnapshotSpec(
        slug="obs-restricao-branco",
        codigo="ORB-07",
        nome="OBs Restrição Branco",
        titulo="OBs Restrição Branco com Peça Disponível",
        setor="Expedição & Tinturaria",
        pasta="OBs Restricao Branco",
        arquivos=_ArquivosAutomacao(
            result_file="orb_result.json",
            cards_manifest="cards_manifest.json",
            cards_dirs=(".",),
        ),
    ),
    _AutomacaoSnapshotSpec(
        slug="receitas-bloqueadas",
        codigo="RB-01",
        nome="Receitas Bloqueadas",
        titulo="Receitas Bloqueadas no Laboratório",
        setor="Tinturaria & Receitas",
        pasta="Receitas Bloqueadas",
        arquivos=_ArquivosAutomacao(
            result_file="rb_result.json",
            state_file="receitas_state.json",
            cards_dirs=("cards",),
        ),
    ),
    _AutomacaoSnapshotSpec(
        slug="receitas-emitidas",
        codigo="RE-03",
        nome="Receitas Emitidas",
        titulo="Receitas Emitidas para Produção",
        setor="Tinturaria & Receitas",
        pasta="Receitas Emitidas",
        arquivos=_ArquivosAutomacao(
            result_file="re_result.json",
            state_file="receitas_state.json",
            cards_dirs=(),
        ),
    ),
    _AutomacaoSnapshotSpec(
        slug="montagem-terceirizados",
        codigo="MT-02",
        nome="Montagem de Terceirizados",
        titulo="Validação de NFs — Montagem de Terceirizados",
        setor="Comercial & Expedição",
        pasta="Montagem de Terceirizados",
        arquivos=_ArquivosAutomacao(
            state_file=".cache_erros.json",
            cards_dirs=(),
        ),
    ),
)

_AUTOMACOES_POR_SLUG: dict[str, _AutomacaoSnapshotSpec] = {
    spec.slug: spec for spec in _AUTOMACOES_SPECS
}


def _validar_slug(slug: str) -> str:
    limpo = (slug or "").strip()
    if not _SLUG_RE.match(limpo):
        raise DomainRuleError(400, f"Slug de consulta promovida invalido: {slug!r}")
    return limpo


def _promovidas_dir(project_root: Path) -> Path:
    return project_root / "Consultas Promovidas"


def _snapshots_dir(project_root: Path) -> Path:
    return _promovidas_dir(project_root) / "snapshots"


def _idade_minutos(generated_at: str | None) -> float | None:
    if not generated_at:
        return None
    try:
        dt = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # Automacoes standalone gravam datetime.now().isoformat() em horario local (BRT).
        dt = dt.replace(tzinfo=_TZ_BR)
    dt_utc = dt.astimezone(UTC)
    return round(max((datetime.now(UTC) - dt_utc).total_seconds() / 60.0, 0.0), 1)


def _ler_json_seguro(arquivo: Path) -> Any:
    if not arquivo.is_file():
        return None
    try:
        return json.loads(arquivo.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _ler_snapshot_latest(project_root: Path, slug: str) -> dict[str, Any] | None:
    if not _SLUG_RE.match((slug or "").strip()):
        return None
    latest_dir = (_snapshots_dir(project_root) / "latest").resolve()
    alvo = (latest_dir / f"{slug}.json").resolve()
    try:
        alvo.relative_to(latest_dir)
    except ValueError:
        return None
    dados = _ler_json_seguro(alvo)
    return dados if isinstance(dados, dict) else None


def _int_seguro(valor: Any, padrao: int = 0) -> int:
    if isinstance(valor, bool):
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _float_seguro(valor: Any) -> float:
    if isinstance(valor, bool):
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _kpis_seguros(valor: Any) -> dict[str, Any]:
    if isinstance(valor, dict):
        return dict(valor)
    if isinstance(valor, str):
        try:
            parsed: Any = json.loads(valor)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _validar_card_em_dirs(
    pasta: Path, allowed_dirs: tuple[str, ...], img_rel: str
) -> str | None:
    """Valida que um caminho do manifesto aponta para um PNG seguro em ``allowed_dirs``."""
    rel_norm = img_rel.strip().replace("\\", "/")
    fname = Path(rel_norm).name
    if not fname or not _SAFE_PNG_RE.match(fname):
        return None
    pasta_resolved = pasta.resolve()
    try:
        alvo = (pasta_resolved / rel_norm).resolve()
        alvo.relative_to(pasta_resolved)
    except (OSError, ValueError):
        return None
    if not alvo.is_file():
        return None
    for rel_dir in allowed_dirs:
        dir_resolved = (pasta_resolved / rel_dir).resolve()
        if alvo == dir_resolved / fname:
            return fname
    return None


def _validar_card_manifesto(
    pasta: Path, spec: _AutomacaoSnapshotSpec, img_rel: str
) -> str | None:
    """Valida que um caminho do manifesto aponta para um PNG seguro dentro de ``cards_dirs``."""
    return _validar_card_em_dirs(pasta, spec.arquivos.cards_dirs, img_rel)


def _coletar_cards_manifesto(
    pasta: Path, manifest_file: str, allowed_dirs: tuple[str, ...]
) -> list[dict[str, str]]:
    """Le cards declarados em ``manifest_file`` validando cada PNG contra ``allowed_dirs``."""
    raw = _ler_json_seguro(pasta / manifest_file)
    if not isinstance(raw, list):
        return []
    cards: list[dict[str, str]] = []
    seen_files: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        fname = _validar_card_em_dirs(
            pasta, allowed_dirs, str(entry.get("image_path") or "")
        )
        if not fname or fname in seen_files:
            continue
        seen_files.add(fname)
        cards.append(
            {
                "key": str(entry.get("phase_key") or fname),
                "title": str(entry.get("phase_display") or fname),
                "filename": fname,
                "caption": str(entry.get("caption") or ""),
            }
        )
    return cards


def _coletar_cards_automacao(
    pasta: Path, spec: _AutomacaoSnapshotSpec
) -> list[dict[str, str]]:
    """Lista cards PNG disponiveis de uma automacao (manifesto exclusivo ou diretorio)."""
    if spec.arquivos.cards_manifest:
        return _coletar_cards_manifesto(
            pasta, spec.arquivos.cards_manifest, spec.arquivos.cards_dirs
        )

    cards: list[dict[str, str]] = []
    seen_files: set[str] = set()
    for rel_dir in spec.arquivos.cards_dirs:
        sub = pasta / rel_dir
        if not sub.is_dir():
            continue
        for png in sorted(sub.glob("*.png"), key=lambda p: p.name.lower()):
            if png.name in seen_files or not _SAFE_PNG_RE.match(png.name):
                continue
            seen_files.add(png.name)
            cards.append(
                {
                    "key": png.stem,
                    "title": png.stem.replace("_", " ").title(),
                    "filename": png.name,
                    "caption": "",
                }
            )
    return cards


def _kpis_linhas_automacao(
    slug: str, rows: list[dict[str, Any]], result: dict[str, Any]
) -> dict[str, Any]:
    if slug == "obs-paradas-fase" and rows:
        return {
            "count": len(rows),
            "sum:KG_PARADO": round(
                sum(_float_seguro(r.get("QT_KILOS_REAL")) for r in rows), 1
            ),
            "max:DIAS_PARADO": round(
                max(_float_seguro(r.get("DIAS_PARADO")) for r in rows), 1
            ),
            "fases": len(
                {str(r.get("FASE_ATUAL") or "") for r in rows if r.get("FASE_ATUAL")}
            ),
        }
    kpis: dict[str, Any] = {"count": len(rows)}
    rc = result.get("record_counts")
    if isinstance(rc, dict) and "read" in rc:
        kpis["lidos"] = _int_seguro(rc.get("read"))
    return kpis


def _extrair_linhas_automacao(
    pasta: Path, spec: _AutomacaoSnapshotSpec
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None, int]:
    """Extrai (rows, kpis, generated_at, excecoes_count) de uma automacao local."""
    res_f = spec.arquivos.result_file
    st_f = spec.arquivos.state_file
    result_raw = _ler_json_seguro(pasta / res_f) if res_f else None
    state_raw = _ler_json_seguro(pasta / st_f) if st_f else None
    result = result_raw if isinstance(result_raw, dict) else {}
    state = state_raw if isinstance(state_raw, dict) else {}

    rows: list[dict[str, Any]] = []
    generated_at: str | None = None
    kpis: dict[str, Any] = {}
    excecoes = 0

    if isinstance(result.get("rows"), list):
        rows = [r for r in result["rows"] if isinstance(r, dict)]
        generated_at = str(result.get("extracted_at") or "") or None
        excecoes = len(rows)
        kpis = _kpis_linhas_automacao(spec.slug, rows, result)
    elif isinstance(state.get("records"), list):
        rows = [r for r in state["records"] if isinstance(r, dict)]
        generated_at = str(state.get("updated_at") or "") or None
        excecoes = len(rows)
        kpis = {"count": len(rows)}
        rc = result.get("record_counts")
        if isinstance(rc, dict):
            if "new" in rc:
                kpis["novos"] = _int_seguro(rc.get("new"))
            if "changed" in rc:
                kpis["alterados"] = _int_seguro(rc.get("changed"))
    elif spec.slug == "montagem-terceirizados":
        itens = state.get("itens")
        if isinstance(itens, dict):
            rows = [
                {"CHAVE": str(k), **(v if isinstance(v, dict) else {"DETALHE": str(v)})}
                for k, v in itens.items()
            ]
        generated_at = str(state.get("timestamp") or "") or None
        excecoes = len(rows)
        kpis = {"count": len(rows)}
    elif isinstance(result.get("record_counts"), dict):
        lidos = _int_seguro(result["record_counts"].get("read"))
        generated_at = str(state.get("updated_at") or "") or None
        kpis = {"count": lidos, "lidos": lidos}

    return rows, kpis, generated_at, excecoes


def _montar_resumo_automacao(
    project_root: Path, spec: _AutomacaoSnapshotSpec
) -> dict[str, Any] | None:
    pasta = project_root / spec.pasta
    if not pasta.is_dir():
        return None
    manifest = _ler_json_seguro(pasta / "automation.manifest.json")
    manifest_name = manifest.get("name") if isinstance(manifest, dict) else None
    auto_name = str(manifest_name) if manifest_name else spec.nome
    rows, kpis, generated_at, excecoes = _extrair_linhas_automacao(pasta, spec)
    cards = _coletar_cards_automacao(pasta, spec)
    has_snapshot = generated_at is not None or bool(rows) or bool(cards) or bool(kpis)
    total_rows = len(rows) if rows else _int_seguro(kpis.get("count"), 0)
    return {
        "slug": spec.slug,
        "codigo": spec.codigo,
        "nome": spec.nome,
        "titulo": spec.titulo,
        "origem": "automacao",
        "setor": spec.setor,
        "automation_name": auto_name,
        "modo": "producao",
        "destinos": ["whatsapp", "dashboard"],
        "has_snapshot": has_snapshot,
        "generated_at": generated_at,
        "age_minutes": _idade_minutos(generated_at),
        "total_rows": total_rows,
        "excecoes_count": excecoes,
        "cards_count": len(cards),
        "kpis": kpis,
    }


def _obter_snapshot_automacao(
    project_root: Path, spec: _AutomacaoSnapshotSpec
) -> dict[str, Any]:
    pasta = project_root / spec.pasta
    if not pasta.is_dir():
        raise DomainRuleError(
            404, f"Diretorio da automacao '{spec.slug}' nao encontrado."
        )
    manifest = _ler_json_seguro(pasta / "automation.manifest.json")
    manifest_name = manifest.get("name") if isinstance(manifest, dict) else None
    auto_name = str(manifest_name) if manifest_name else spec.nome
    rows, kpis, generated_at, excecoes = _extrair_linhas_automacao(pasta, spec)
    cards = _coletar_cards_automacao(pasta, spec)
    columns = list(dict.fromkeys(k for r in rows for k in r))
    return {
        "slug": spec.slug,
        "codigo": spec.codigo,
        "nome": spec.nome,
        "titulo": spec.titulo,
        "origem": "automacao",
        "setor": spec.setor,
        "automation_name": auto_name,
        "modo": "producao",
        "generated_at": generated_at or "",
        "age_minutes": _idade_minutos(generated_at),
        "total_rows": len(rows) if rows else _int_seguro(kpis.get("count"), 0),
        "excecoes_count": excecoes,
        "kpis": kpis,
        "columns": columns,
        "rows": rows,
        "cards": cards,
    }


def _setor_por_owner(owner_area: str | None) -> str:
    texto = (owner_area or "").lower()
    if "rama" in texto or "acabamento" in texto:
        return "Acabamento & Ramas"
    if "tinturaria" in texto or "receita" in texto or "quimic" in texto:
        return "Tinturaria & Receitas"
    if "qualidade" in texto or "montagem" in texto:
        return "Qualidade & Montagem"
    if "comercial" in texto or "faturamento" in texto or "loja" in texto:
        return "Comercial & Expedição"
    return "Beneficiamento & PCP"


def _coletar_cards_promovida(pasta: Path) -> list[dict[str, str]]:
    """Lista cards PNG declarados em ``cards_manifest.json`` na pasta da consulta."""
    if not pasta.is_dir():
        return []
    return _coletar_cards_manifesto(pasta, "cards_manifest.json", (".",))


def _montar_item_promovida(project_root: Path, pasta: Path) -> dict[str, Any] | None:
    cfg = _ler_json_seguro(pasta / "promocao.json")
    if not isinstance(cfg, dict):
        return None
    manifest_raw = _ler_json_seguro(pasta / "automation.manifest.json")
    manifest = manifest_raw if isinstance(manifest_raw, dict) else {}
    slug = str(cfg.get("slug") or pasta.name).strip()
    if not _SLUG_RE.match(slug):
        return None
    snap = _ler_snapshot_latest(project_root, slug)
    cards = _coletar_cards_promovida(pasta)
    painel_raw = cfg.get("painel")
    painel: dict[str, Any] = painel_raw if isinstance(painel_raw, dict) else {}
    destinos = (
        list(cfg["destinos"])
        if isinstance(cfg.get("destinos"), list)
        else ["dashboard"]
    )
    generated_at = (
        str(snap["generated_at"]) if snap and snap.get("generated_at") else None
    )
    return {
        "slug": slug,
        "codigo": str(manifest.get("id") or slug.upper()),
        "nome": str(cfg.get("nome") or slug),
        "titulo": str(painel.get("titulo") or cfg.get("nome") or slug),
        "origem": "promovida",
        "setor": _setor_por_owner(str(manifest.get("owner_area") or "")),
        "automation_name": str(manifest.get("name") or cfg.get("nome") or slug),
        "modo": str(cfg.get("modo") or "sombra"),
        "destinos": destinos,
        "has_snapshot": snap is not None,
        "generated_at": generated_at,
        "age_minutes": _idade_minutos(generated_at),
        "total_rows": _int_seguro(snap.get("total_rows"), 0) if snap else 0,
        "excecoes_count": _int_seguro(snap.get("excecoes_count"), 0) if snap else 0,
        "cards_count": len(cards),
        "kpis": _kpis_seguros(snap.get("kpis")) if snap else {},
    }


def listar_promocoes(
    project_root: Path, *, include_automacoes: bool = True
) -> list[dict[str, Any]]:
    """Lista promocoes configuradas e (opcionalmente) snapshots das 6 automacoes."""
    itens: list[dict[str, Any]] = []

    if include_automacoes:
        for spec in _AUTOMACOES_SPECS:
            resumo = _montar_resumo_automacao(project_root, spec)
            if resumo is not None:
                itens.append(resumo)

    base = _promovidas_dir(project_root)
    if not base.is_dir():
        return itens

    for pasta in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if (
            not pasta.is_dir()
            or pasta.name in {"snapshots"}
            or pasta.name.startswith(".")
        ):
            continue
        item = _montar_item_promovida(project_root, pasta)
        if item is not None:
            itens.append(item)
    return itens


def obter_ultimo_snapshot(project_root: Path, slug: str) -> dict[str, Any]:
    """Retorna o snapshot JSON mais recente de ``slug`` ou levanta DomainRuleError(404)."""
    slug_ok = _validar_slug(slug)
    if slug_ok in _AUTOMACOES_POR_SLUG:
        return _obter_snapshot_automacao(project_root, _AUTOMACOES_POR_SLUG[slug_ok])

    snap = _ler_snapshot_latest(project_root, slug_ok)
    if snap is None:
        raise DomainRuleError(
            404, f"Snapshot nao encontrado para a consulta promovida '{slug_ok}'."
        )
    snap["age_minutes"] = _idade_minutos(
        str(snap["generated_at"]) if snap.get("generated_at") else None
    )
    snap.setdefault("origem", "promovida")
    cards_locais = _coletar_cards_promovida(_promovidas_dir(project_root) / slug_ok)
    if cards_locais:
        snap["cards"] = cards_locais
    else:
        snap.setdefault("cards", [])
    return snap


def resolver_card_png(project_root: Path, slug: str, filename: str) -> Path:
    """Resolve com seguranca o caminho de um card PNG de uma automacao/consulta."""
    slug_ok = _validar_slug(slug)
    fname = (filename or "").strip()
    if not _SAFE_PNG_RE.match(fname):
        raise DomainRuleError(400, "Nome de arquivo PNG invalido.")

    spec = _AUTOMACOES_POR_SLUG.get(slug_ok)
    if spec is not None:
        pasta = (project_root / spec.pasta).resolve()
        for rel_dir in spec.arquivos.cards_dirs:
            candidato = (pasta / rel_dir / fname).resolve()
            try:
                candidato.relative_to(pasta)
            except ValueError as exc:
                raise DomainRuleError(
                    400, "Caminho de card fora do escopo permitido."
                ) from exc
            if candidato.is_file():
                return candidato
        raise DomainRuleError(404, f"Card '{fname}' nao encontrado para '{slug_ok}'.")

    pasta_promovida = (_promovidas_dir(project_root) / slug_ok).resolve()
    if not pasta_promovida.is_dir():
        raise DomainRuleError(404, f"Cards indisponiveis para '{slug_ok}'.")
    candidato = (pasta_promovida / fname).resolve()
    try:
        candidato.relative_to(pasta_promovida)
    except ValueError as exc:
        raise DomainRuleError(400, "Caminho de card fora do escopo permitido.") from exc
    if candidato.is_file():
        return candidato

    raise DomainRuleError(404, f"Card '{fname}' nao encontrado para '{slug_ok}'.")


def obter_historico(
    project_root: Path, slug: str, *, limit: int = 30
) -> list[dict[str, Any]]:
    """Retorna historico resumido de execucoes da promocao a partir de ``promovidas.db``."""
    slug_ok = _validar_slug(slug)
    db_path = _snapshots_dir(project_root) / "promovidas.db"
    if not db_path.is_file():
        return []
    db_uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        with contextlib.closing(sqlite3.connect(db_uri, uri=True, timeout=5.0)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT slug, generated_at, modo, total_rows, excecoes_count, kpis_json
                  FROM snapshots_historico
                 WHERE slug = ?
                 ORDER BY generated_at DESC
                 LIMIT ?
                """,
                (slug_ok, limit),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise DomainRuleError(
            503, "Historico de snapshots temporariamente indisponivel."
        ) from exc
    except sqlite3.Error as exc:
        raise DomainRuleError(
            503, "Falha ao consultar historico de snapshots."
        ) from exc
    return [
        {
            "slug": str(r["slug"]),
            "generated_at": str(r["generated_at"]),
            "modo": str(r["modo"]),
            "total_rows": _int_seguro(r["total_rows"], 0),
            "excecoes_count": _int_seguro(r["excecoes_count"], 0),
            "kpis": _kpis_seguros(r["kpis_json"]),
        }
        for r in rows
    ]
