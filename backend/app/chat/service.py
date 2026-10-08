"""O laço de conversa com a OpenAI (Responses API com function calling).

A chave e o nome do modelo vêm do ambiente e ficam **só aqui no backend**. Sem
`OPENAI_API_KEY` e `OPENAI_MODEL`, o resto do sistema funciona normalmente e a
tela de chat avisa que está desligado.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.chat import propostas, tools
from app.config import get_settings
from app.scheduling.domain import DIAS, GradeState
from app.schemas import ConfigRegras

log = logging.getLogger(__name__)

MAX_ITERACOES = 8
"""Teto de rodadas de ferramenta por mensagem (seção 6.3 da spec)."""

TIMEOUT_S = 90.0


class ChatDesativado(Exception):
    pass


def disponivel() -> bool:
    return get_settings().chat_enabled


# ------------------------------------------------------------ system prompt


def instrucoes(estado: GradeState, config: ConfigRegras) -> str:
    """As regras da unidade entram no prompt: o assistente não pode prometer o
    que a configuração proíbe."""
    interjornada = (
        "não verificada"
        if config.interjornada.modo == "off"
        else f"{config.interjornada.horas} h ({config.interjornada.modo})"
    )
    limite = (
        "desligado"
        if not config.limite_diario.ativo
        else (
            f"{config.limite_diario.max_consecutivas} consecutivas / "
            f"{config.limite_diario.max_intercaladas} por dia"
        )
    )
    dias_com_aula = sorted({s.dia for s in estado.slots.values()})

    return f"""
Você é o assistente de horários de {estado.unidade_nome}, uma unidade do
Centro Paula Souza. Ajuda a coordenação a ajustar uma grade já gerada.

REGRAS DESTA UNIDADE
- Carga máxima semanal: {config.carga_max_semanal} aulas.
- Interjornada (CLT art. 66): {interjornada}.
- Limite diário de aulas: {limite}.
- Usa sábado: {"sim" if config.usa_sabado else "não"}.
- Dias com aula: {", ".join(DIAS[d] for d in dias_com_aula)}.
- Regra de atribuição: {config.atribuicao.regra}.
- Aulas geminadas de um mesmo bloco nunca atravessam intervalo.
- Disciplina remota ocupa o horário da turma, mas não usa sala.

COMO TRABALHAR
1. Nunca invente ids. Use `buscar_entidades` para transformar nomes citados
   ("Luciana", "DSM 2", "quinta 20h50") em ids, e `buscar_grade` para ver as
   aulas existentes.
2. Antes de propor um movimento, use `validar_movimento` para saber o que ele
   quebra. Se quebrar regra rígida, diga isso em vez de propor às cegas.
3. As ferramentas que mudam a grade **apenas criam uma proposta**. Quem aplica é
   o usuário, clicando no cartão. Nunca diga que já alterou a grade; diga que
   preparou a proposta e o que ela faz.
4. Uma proposta por pedido. Se o usuário pedir várias coisas, proponha a
   primeira e pergunte se segue.
5. Se não der para fazer o que foi pedido, explique o motivo concreto (qual
   regra, qual professor, qual horário) e ofereça a alternativa mais próxima.

COMO RESPONDER
- Português do Brasil, curto e direto. Duas ou três frases bastam.
- Cite horários como o sistema mostra ("terça 20h50–22h30").
- Não repita o cartão de proposta em texto: a tela já mostra o antes e o depois.
""".strip()


# ------------------------------------------------------------------ eventos


@dataclass(slots=True)
class Evento:
    """Um evento SSE para a tela."""

    tipo: str
    """texto | ferramenta | proposta | fim | erro"""
    dados: dict[str, Any] = field(default_factory=dict)

    def sse(self) -> str:
        corpo = json.dumps(self.dados, ensure_ascii=False, default=str)
        return f"event: {self.tipo}\ndata: {corpo}\n\n"


def _proposta_para_evento(proposta: propostas.Proposta) -> dict:
    return {
        "id": proposta.id,
        "tipo": proposta.tipo,
        "descricao": proposta.descricao,
        "permitido": proposta.permitido,
        "mudancas": [
            {"rotulo": mud.rotulo, "antes": mud.antes, "depois": mud.depois}
            for mud in proposta.mudancas
        ],
        "violacoes": [
            {"tipo": v.tipo, "severidade": v.severidade.value, "mensagem": v.mensagem}
            for v in proposta.violacoes
        ],
    }


# --------------------------------------------------------------------- laço


def criar_cliente():
    """Importado aqui dentro para o pacote `openai` não ser exigido em quem só
    roda o resto do sistema."""
    from openai import OpenAI

    cfg = get_settings()
    if not cfg.chat_enabled:
        raise ChatDesativado(
            "Chat desativado: configure OPENAI_API_KEY e OPENAI_MODEL no servidor."
        )
    return OpenAI(api_key=cfg.openai_api_key)


def conversar(
    ctx: tools.Contexto,
    mensagens: list[dict],
    *,
    cliente=None,
    modelo: str | None = None,
) -> Iterator[Evento]:
    """Roda a conversa e vai emitindo eventos.

    `mensagens` é o histórico no formato da Responses API: itens com `role` e
    `content`. Devolve texto em pedaços, avisa cada ferramenta chamada e emite
    as propostas criadas.
    """
    cfg = get_settings()
    cliente = cliente or criar_cliente()
    modelo = modelo or cfg.openai_model

    entrada: list[dict] = [
        {"role": "system", "content": instrucoes(ctx.estado, ctx.config)},
        *mensagens,
    ]
    comeco = time.monotonic()

    for iteracao in range(MAX_ITERACOES):
        if time.monotonic() - comeco > TIMEOUT_S:
            yield Evento("erro", {"mensagem": "A consulta demorou demais e foi interrompida."})
            return

        try:
            fluxo = cliente.responses.create(
                model=modelo,
                input=entrada,
                tools=tools.definicoes_openai(),
                stream=True,
            )
        except Exception as erro:  # pragma: no cover - falha de rede/credencial
            log.exception("falha ao falar com a OpenAI")
            yield Evento("erro", {"mensagem": f"Não foi possível falar com o modelo: {erro}"})
            return

        chamadas: list[dict] = []
        saida: list[dict] = []
        for evento in fluxo:
            tipo = getattr(evento, "type", "")
            if tipo == "response.output_text.delta":
                yield Evento("texto", {"delta": evento.delta})
            elif tipo == "response.completed":
                saida = [_como_dict(item) for item in evento.response.output]
                chamadas = [i for i in saida if i.get("type") == "function_call"]

        entrada.extend(saida)

        if not chamadas:
            yield Evento("fim", {"iteracoes": iteracao + 1})
            return

        for chamada in chamadas:
            nome = chamada.get("name", "")
            yield Evento("ferramenta", {"nome": nome})
            antes = len(ctx.propostas_criadas)
            resultado = tools.executar(ctx, nome, chamada.get("arguments", "{}"))
            entrada.append(
                {
                    "type": "function_call_output",
                    "call_id": chamada.get("call_id"),
                    "output": resultado,
                }
            )
            for proposta in ctx.propostas_criadas[antes:]:
                yield Evento("proposta", _proposta_para_evento(proposta))

    yield Evento(
        "erro",
        {
            "mensagem": (
                f"O assistente usou as {MAX_ITERACOES} rodadas de ferramenta sem "
                "concluir. Tente pedir uma coisa de cada vez."
            )
        },
    )


def _como_dict(item: Any) -> dict:
    """A Responses API devolve objetos; o histórico precisa deles como dict,
    **no formato em que a API os mandou** — eles voltam para ela na rodada
    seguinte.

    `to_dict()` do SDK faz isso: nomes da API e só os campos que vieram.
    `model_dump()` puro usa o nome Python (`async_` em vez de `async`) e inclui
    campos vazios, e a OpenAI recusa a requisição com "Unknown parameter".
    """
    if isinstance(item, dict):
        return item
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if hasattr(item, "model_dump"):
        return item.model_dump(by_alias=True, exclude_unset=True)
    return dict(item)  # pragma: no cover - formato inesperado
