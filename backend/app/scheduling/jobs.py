"""Execucao do solver em segundo plano, com progresso.

O usuario nao espera numa tela de carregando: o solver roda fora da requisicao e
a tela consulta `GET /grades/{id}/progresso`, que devolve a melhor solucao
encontrada ate' agora para ser desenhada ao vivo (secao 11.2 da spec).

Sem Celery: o solver e' CPU-bound e o caso real e' uma unidade gerando uma grade
por vez (DECISOES.md D11). O registro de jobs vive em memoria e e' limitado.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import uuid4

from app import models as m
from app.db import SessionLocal
from app.scheduling.avisos import avisos_da_grade, gravar_avisos
from app.scheduling.diagnose import diagnosticar
from app.scheduling.loader import carregar_estado
from app.scheduling.solver import Alocado, Parametros, Solucao, resolver

log = logging.getLogger(__name__)

fabrica_de_sessao = SessionLocal
"""Como o job abre a sua propria sessao. O job roda fora da requisicao, entao
nao pode reaproveitar a sessao dela. Os testes trocam esta fabrica pela do banco
de teste."""

MAX_JOBS = 50
"""Quantos jobs ficam no historico em memoria antes de o mais antigo sair."""


@dataclass(slots=True)
class Job:
    id: str
    grade_id: int
    unidade_id: int
    status: str = "na fila"
    """na fila | executando | concluido | inviavel | erro"""
    solucoes: int = 0
    objetivo: int | None = None
    limite_inferior: int | None = None
    tempo_s: float = 0.0
    mensagem: str | None = None
    diagnostico: dict | None = None
    metricas: dict = field(default_factory=dict)
    parcial: list[Alocado] = field(default_factory=list)
    """Melhor solucao ate' agora, para a grade se desenhar ao vivo."""
    criado_em: datetime = field(default_factory=datetime.now)

    @property
    def terminado(self) -> bool:
        return self.status in ("concluido", "inviavel", "erro")


class _Registro:
    """Mapa de jobs com limite de tamanho e acesso protegido por lock."""

    def __init__(self, maximo: int = MAX_JOBS):
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._maximo = maximo

    def criar(self, grade_id: int, unidade_id: int) -> Job:
        job = Job(id=uuid4().hex[:12], grade_id=grade_id, unidade_id=unidade_id)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self._maximo:
                self._jobs.popitem(last=False)
        return job

    def por_id(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def da_grade(self, grade_id: int) -> Job | None:
        """O job mais recente de uma grade."""
        with self._lock:
            for job in reversed(self._jobs.values()):
                if job.grade_id == grade_id:
                    return job
        return None


REGISTRO = _Registro()


def executar(job_id: str, params: Parametros) -> None:
    """Roda o solver e grava o resultado. Chamado fora da requisicao."""
    job = REGISTRO.por_id(job_id)
    if job is None:  # pragma: no cover - job expirado do registro
        return
    job.status = "executando"

    try:
        with fabrica_de_sessao() as db:
            estado, config = carregar_estado(db, job.unidade_id, grade_id=job.grade_id)

            def progresso(parcial: Solucao) -> None:
                job.solucoes += 1
                job.objetivo = parcial.objetivo
                job.limite_inferior = parcial.limite_inferior
                job.tempo_s = parcial.tempo_s
                job.parcial = parcial.alocacoes

            solucao = resolver(estado, config, params, aviso=progresso)
            job.tempo_s = solucao.tempo_s
            job.metricas = solucao.metricas

            if not solucao.viavel:
                diag = diagnosticar(estado, config, params)
                job.mensagem = diag.mensagem
                job.diagnostico = {
                    "mensagem": diag.mensagem,
                    "culpados": diag.culpados,
                    "acoes": diag.acoes,
                }
                if params.resolver_avisos and diag.culpados:
                    # "Resolver avisos" entrega o que da': solta so' os grupos
                    # que o diagnostico provou impossiveis e resolve de novo.
                    # A grade sai sem todos os outros avisos, e `mensagem`
                    # diz qual ficou.
                    relaxados = replace(
                        params,
                        relaxar=frozenset((c["tipo"], c["id"]) for c in diag.culpados),
                    )
                    solucao = resolver(estado, config, relaxados, aviso=progresso)
                    job.tempo_s = solucao.tempo_s
                    job.metricas = solucao.metricas
                if not solucao.viavel:
                    # So' agora: a tela para de consultar quando `terminado`, e
                    # antes o diagnostico chegava depois da ultima consulta.
                    job.status = "inviavel"
                    return

            _gravar(db, job, solucao, estado, config)
            job.status = "concluido"
            job.objetivo = solucao.objetivo
            job.limite_inferior = solucao.limite_inferior
            job.parcial = solucao.alocacoes

    except Exception as erro:  # pragma: no cover - rede de seguranca do job
        log.exception("falha ao gerar a grade %s", job.grade_id)
        job.status = "erro"
        job.mensagem = f"Erro ao gerar a grade: {erro}"
        job.diagnostico = {"traceback": traceback.format_exc()}


def _gravar(db, job: Job, solucao: Solucao, estado, config) -> None:
    """Substitui as alocacoes da grade e regrava os avisos."""
    from app.scheduling.domain import AlocacaoInfo

    fixadas = {(a.oferta_id, a.bloco_idx, a.slot_id) for a in estado.alocacoes if a.fixada}

    for antiga in db.query(m.Alocacao).filter(m.Alocacao.grade_id == job.grade_id):
        db.delete(antiga)
    db.flush()

    for a in solucao.alocacoes:
        db.add(
            m.Alocacao(
                grade_id=job.grade_id,
                oferta_id=a.oferta_id,
                professor_id=a.professor_id,
                slot_id=a.slot_id,
                espaco_id=a.espaco_id,
                bloco_idx=a.bloco_idx,
                fixada=(a.oferta_id, a.bloco_idx, a.slot_id) in fixadas,
            )
        )
    db.flush()

    # O validador precisa enxergar o que acabou de ser gravado.
    estado.alocacoes = [
        AlocacaoInfo(
            id=0,
            oferta_id=a.oferta_id,
            professor_id=a.professor_id,
            slot_id=a.slot_id,
            espaco_id=a.espaco_id,
            bloco_idx=a.bloco_idx,
            fixada=(a.oferta_id, a.bloco_idx, a.slot_id) in fixadas,
        )
        for a in solucao.alocacoes
    ]
    violacoes = avisos_da_grade(estado, config)
    gravar_avisos(db, job.grade_id, violacoes)

    grade = db.get(m.Grade, job.grade_id)
    if grade is not None:
        grade.score = {
            "objetivo": solucao.objetivo,
            "limite_inferior": solucao.limite_inferior,
            "tempo_s": round(solucao.tempo_s, 2),
            **solucao.metricas,
        }
        grade.status = (
            m.StatusGrade.AGUARDANDO_CIENCIA
            if any(v.severidade == m.Severidade.ALERTA for v in violacoes)
            else m.StatusGrade.RASCUNHO
        )
    db.commit()


def executar_sincrono(grade_id: int, unidade_id: int, params: Parametros) -> Job:
    """Mesma execucao, sem segundo plano. Usada nos testes e no chat."""
    job = REGISTRO.criar(grade_id, unidade_id)
    executar(job.id, params)
    return job
