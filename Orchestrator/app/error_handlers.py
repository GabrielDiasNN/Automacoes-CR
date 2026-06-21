# mypy: ignore-errors
"""Global FastAPI exception handlers (Pilar R — Resiliência)."""

import logging
import time

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _get_correlation_id(request: Request) -> str:
    return getattr(request.state, "request_id", "SYSTEM")


def _build_error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    action_hint: str,
    detail: object | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": message,
        "action_hint": action_hint,
        "correlation_id": _get_correlation_id(request),
    }
    if detail is not None:
        payload["detail"] = detail
    return payload


def register_exception_handlers(app: FastAPI, logger: logging.Logger) -> None:
    """Attach standardised JSON error handlers to the FastAPI application."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail if exc.detail is not None else "Falha de requisição."
        message = detail if isinstance(detail, str) else "Falha de requisição."
        action_hint = "Revisar os dados da requisição e tentar novamente."
        code = "bad_request"
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            code = "access_denied"
            action_hint = "Validar a API Key e repetir a chamada."
        elif exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "resource_not_found"
            action_hint = "Verificar identificador e existência do recurso solicitado."
        elif exc.status_code == status.HTTP_409_CONFLICT:
            code = "conflict"
            action_hint = "Resolver conflito operacional e tentar novamente."
        elif exc.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
            code = "validation_error"
            action_hint = "Corrigir os campos inválidos enviados na requisição."

        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_payload(
                request,
                code=code,
                message=message,
                action_hint=action_hint,
                detail=detail,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        errors = []
        for item in exc.errors():
            ctx = item.get("ctx")
            if isinstance(ctx, dict) and "error" in ctx:
                ctx = {**ctx, "error": str(ctx["error"])}
                item = {**item, "ctx": ctx}
            errors.append(item)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_build_error_payload(
                request,
                code="validation_error",
                message="Payload inválido para este endpoint.",
                action_hint="Corrigir os campos obrigatórios e formatos antes de reenviar.",
                detail=jsonable_encoder(errors),
            ),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Captura qualquer erro não tratado e devolve JSON padronizado (Pilar R)."""
        error_id = str(int(time.time()))
        correlation_id = _get_correlation_id(request)
        logger.error(
            "Unhandled Error [%s] correlation_id=%s: %s",
            error_id,
            correlation_id,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=_build_error_payload(
                request,
                code="internal_error",
                message="Ocorreu um erro interno no servidor.",
                action_hint="Consultar logs da API com o correlation_id antes de nova tentativa.",
                detail={
                    "error_id": error_id,
                    "type": type(exc).__name__,
                },
            ),
        )
