"""Fabrica de routers CRUD.

Onze entidades de cadastro tem exatamente o mesmo comportamento
(listar/criar/ler/atualizar/apagar). Uma fabrica evita onze copias do mesmo
arquivo; o que muda entre elas entra por parametro, e o que e' especifico de uma
entidade entra pelos ganchos `apos_criar` / `apos_atualizar` / `antes_apagar`.
"""

# Sem `from __future__ import annotations`: `entrada` e `parcial` sao parametros de
# funcao usados como anotacao de rota, e o FastAPI precisa da classe real, nao de uma
# string adiada.
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessaoDb
from app.models import Base as ModeloBase

HTTP_422 = 422
"""O alias do Starlette para 422 mudou de nome entre versoes; usamos o numero."""

Gancho = Callable[[Session, Any], None]


def buscar_ou_404(db: Session, modelo: type[ModeloBase], id_: int, rotulo: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{rotulo} {id_} nao encontrado(a).")
    return obj


def _traduzir_integridade(erro: IntegrityError, rotulo: str) -> HTTPException:
    texto = str(erro.orig).lower()
    if "unique" in texto or "duplicate" in texto:
        return HTTPException(
            status.HTTP_409_CONFLICT, f"Ja existe um(a) {rotulo.lower()} com esses dados."
        )
    if "foreign key" in texto or "violates foreign key" in texto:
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"Nao foi possivel salvar: {rotulo.lower()} depende de um registro inexistente "
            "ou ainda e' usado(a) por outros registros.",
        )
    return HTTPException(status.HTTP_400_BAD_REQUEST, f"Nao foi possivel salvar {rotulo.lower()}.")


@contextmanager
def gravando(db: Session, rotulo: str) -> Iterator[None]:
    """Envolve escrita + commit.

    Cobre o `flush` de proposito: o INSERT sai no flush, entao uma violacao de
    unicidade estoura antes do commit e viraria 500 se so o commit fosse protegido.
    """
    try:
        yield
        db.commit()
    except IntegrityError as erro:
        db.rollback()
        raise _traduzir_integridade(erro, rotulo) from erro


def router_crud(
    *,
    prefixo: str,
    rotulo: str,
    modelo: type[ModeloBase],
    leitura: type[BaseModel],
    entrada: type[BaseModel],
    parcial: type[BaseModel],
    filtros: Sequence[str] = (),
    ordem: Sequence[str] = ("id",),
    apos_criar: Gancho | None = None,
    apos_atualizar: Gancho | None = None,
    antes_apagar: Gancho | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefixo, tags=[prefixo.strip("/")])
    colunas_filtro = {nome: getattr(modelo, nome) for nome in filtros}
    doc_filtros = ", ".join(f"`{f}`" for f in filtros) or "nenhum"

    @router.get(
        "",
        response_model=list[leitura],
        summary=f"Listar {rotulo.lower()}",
        description=f"Filtros aceitos por query string: {doc_filtros}.",
    )
    def listar(
        request: Request,
        db: SessaoDb,
        limite: int = Query(default=500, ge=1, le=5000),
        deslocamento: int = Query(default=0, ge=0),
    ):
        consulta = select(modelo)
        for chave, valor in request.query_params.items():
            if chave in ("limite", "deslocamento"):
                continue
            coluna = colunas_filtro.get(chave)
            if coluna is None:
                raise HTTPException(
                    HTTP_422,
                    f"Filtro {chave!r} nao existe aqui. Disponiveis: {doc_filtros}.",
                )
            try:
                consulta = consulta.where(coluna == int(valor))
            except ValueError:
                raise HTTPException(
                    HTTP_422,
                    f"O filtro {chave!r} espera um numero inteiro.",
                ) from None
        consulta = consulta.order_by(*(getattr(modelo, c) for c in ordem))
        return db.scalars(consulta.offset(deslocamento).limit(limite)).all()

    @router.post(
        "",
        response_model=leitura,
        status_code=status.HTTP_201_CREATED,
        summary=f"Criar {rotulo.lower()}",
    )
    def criar(dados: entrada, db: SessaoDb):  # type: ignore[valid-type]
        obj = modelo(**dados.model_dump(exclude_unset=False))
        with gravando(db, rotulo):
            db.add(obj)
            db.flush()
            if apos_criar:
                apos_criar(db, obj)
        db.refresh(obj)
        return obj

    @router.get("/{id_}", response_model=leitura, summary=f"Ler {rotulo.lower()}")
    def ler(id_: int, db: SessaoDb):
        return buscar_ou_404(db, modelo, id_, rotulo)

    @router.patch("/{id_}", response_model=leitura, summary=f"Atualizar {rotulo.lower()}")
    def atualizar(id_: int, dados: parcial, db: SessaoDb):  # type: ignore[valid-type]
        obj = buscar_ou_404(db, modelo, id_, rotulo)
        with gravando(db, rotulo):
            for campo, valor in dados.model_dump(exclude_unset=True).items():
                setattr(obj, campo, valor)
            db.flush()
            if apos_atualizar:
                apos_atualizar(db, obj)
        db.refresh(obj)
        return obj

    @router.delete(
        "/{id_}", status_code=status.HTTP_204_NO_CONTENT, summary=f"Apagar {rotulo.lower()}"
    )
    def apagar(id_: int, db: SessaoDb):
        obj = buscar_ou_404(db, modelo, id_, rotulo)
        if antes_apagar:
            antes_apagar(db, obj)
        with gravando(db, rotulo):
            db.delete(obj)

    return router
