from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    atribuicao,
    cadastros,
    chat,
    edicao,
    exportar,
    grades,
    importar,
    turnos,
    validacao,
    versoes,
)
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Horario Inteligente",
        version="0.1.0",
        description="Geracao de grades de horario para unidades do Centro Paula Souza.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/saude", tags=["saude"])
    def saude() -> dict:
        return {"status": "ok", "chat_habilitado": settings.chat_enabled}

    app.include_router(turnos.router)
    app.include_router(validacao.router)
    app.include_router(atribuicao.router)
    app.include_router(grades.router)
    app.include_router(edicao.router)
    app.include_router(chat.router)
    app.include_router(exportar.router)
    app.include_router(versoes.router)
    app.include_router(importar.router)
    for router in cadastros.ROUTERS:
        app.include_router(router)

    return app


app = create_app()
