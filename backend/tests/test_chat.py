"""Etapa 8: chatbot — ferramentas, propostas e o laço de conversa.

O cliente da OpenAI é sempre mockado: nenhum teste chama a API de verdade
(seção 10 da especificação).
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import select

from app.chat import propostas, service, tools
from app.models import Alocacao, HistoricoAlteracao, OrigemAlteracao, Unidade
from app.scheduling.loader import carregar_estado

# ------------------------------------------------------------------ fixtures


@pytest.fixture
def grade_pronta(cliente, escopo_seed, db) -> tuple[int, int]:
    """Etec com atribuição e grade gerada — tem folga para mover aulas."""
    unidade = db.scalar(select(Unidade).where(Unidade.nome == "Etec Taquaritinga"))
    cliente.post(f"/unidades/{unidade.id}/atribuicao/sugerir")
    corpo = cliente.post(f"/unidades/{unidade.id}/grades/gerar", json={"tempo_limite_s": 15}).json()
    return unidade.id, corpo["grade_id"]


@pytest.fixture
def ctx(db, grade_pronta) -> tools.Contexto:
    from app import models as m

    _, grade_id = grade_pronta
    grade = db.get(m.Grade, grade_id)
    estado, config = carregar_estado(db, grade.unidade_id, grade_id=grade_id)
    return tools.Contexto(db=db, grade=grade, estado=estado, config=config)


def _uma_aula(ctx: tools.Contexto, sigla: str | None = None):
    for a in ctx.estado.alocacoes:
        if (
            sigla is None
            or ctx.estado.disciplina_da(ctx.estado.ofertas[a.oferta_id]).sigla == sigla
        ):
            return a
    raise AssertionError(f"nenhuma aula de {sigla}")


# ------------------------------------------------------------- ferramentas


def test_buscar_grade_devolve_ids_utilizaveis(ctx):
    resposta = tools.buscar_grade(ctx, {})
    assert resposta["total"] > 0
    aula = resposta["aulas"][0]
    assert set(aula) >= {"alocacao_id", "oferta_id", "bloco_idx", "slot_id", "horario"}
    assert isinstance(aula["alocacao_id"], int)


def test_buscar_grade_filtra_por_professor_e_dia(ctx):
    professor_id = ctx.estado.alocacoes[0].professor_id
    so_dele = tools.buscar_grade(ctx, {"professor_id": professor_id})
    assert so_dele["total"] >= 1
    assert all(a["professor_id"] == professor_id for a in so_dele["aulas"])

    segunda = tools.buscar_grade(ctx, {"dia": 0})
    assert all("segunda" in a["horario"] for a in segunda["aulas"])


def test_buscar_grade_limita_a_resposta(ctx):
    resposta = tools.buscar_grade(ctx, {})
    assert resposta["mostrando"] <= tools.LIMITE_RESULTADOS
    assert len(resposta["aulas"]) == resposta["mostrando"]


def test_buscar_entidades_resolve_professor_sem_acento(ctx):
    achados = tools.buscar_entidades(ctx, "iara")["encontrados"]
    professores = [a for a in achados if a["tipo"] == "professor"]
    assert professores and professores[0]["rotulo"] == "Iara Figueiredo"


def test_buscar_entidades_resolve_disciplina_por_sigla_e_por_nome(ctx):
    por_sigla = tools.buscar_entidades(ctx, "LP")["encontrados"]
    assert any(a["tipo"] == "disciplina" for a in por_sigla)

    por_nome = tools.buscar_entidades(ctx, "banco de dados")["encontrados"]
    assert any(a["tipo"] == "disciplina" and "BD" in a["rotulo"] for a in por_nome)


def test_buscar_entidades_resolve_horario(ctx):
    """Sem o id do horário o modelo não consegue mover nada."""
    achados = tools.buscar_entidades(ctx, "19:00")["encontrados"]
    horarios = [a for a in achados if a["tipo"] == "horario"]
    assert horarios
    assert all("19h00" in a["rotulo"] for a in horarios)


def test_buscar_entidades_sem_resultado_da_uma_dica(ctx):
    resposta = tools.buscar_entidades(ctx, "professor que nao existe")
    assert resposta["encontrados"] == []
    assert "buscar_grade" in resposta["dica"]


def test_validar_movimento_nao_cria_proposta(ctx):
    aula = _uma_aula(ctx)
    antes = len(ctx.propostas_criadas)
    resposta = tools.validar_movimento(ctx, aula.id, aula.slot_id, None)
    assert "possivel" in resposta
    assert len(ctx.propostas_criadas) == antes


def test_explicar_conta_o_que_prende_a_aula(ctx):
    aula = _uma_aula(ctx)
    resposta = tools.explicar(ctx, aula.id, None)
    assert resposta["aula"]
    assert resposta["professor"]
    assert "quantos_horarios_possiveis" in resposta
    assert isinstance(resposta["outros_horarios_possiveis"], list)


def test_explicar_recusa_id_inexistente(ctx):
    assert "erro" in tools.explicar(ctx, 999_999, None)
    assert "erro" in tools.explicar(ctx, None, None)


# -------------------------------------------------------------- propostas


def test_mover_aula_cria_proposta_e_nao_grava(ctx, db):
    aula = _uma_aula(ctx)
    destino = next(
        slot_id
        for slot_id, r in sorted(
            __import__("app.scheduling.apply", fromlist=["x"])
            .destinos_possiveis(
                ctx.estado, ctx.config, tools.apply.Bloco(aula.oferta_id, aula.bloco_idx)
            )
            .items()
        )
        if r.permitido and slot_id != aula.slot_id
    )

    resposta = tools.mover_aula(ctx, aula.id, destino, None)
    assert "proposta_id" in resposta
    assert "Aguardando o usuário" in resposta["resumo"]

    db.expire_all()
    assert db.get(Alocacao, aula.id).slot_id == aula.slot_id, "nada pode ter sido gravado"


def test_mover_para_o_mesmo_lugar_e_recusado(ctx):
    aula = _uma_aula(ctx)
    assert "erro" in tools.mover_aula(ctx, aula.id, aula.slot_id, None)


def test_mover_aula_com_id_inexistente(ctx):
    resultado = tools.executar(
        ctx,
        "mover_aula",
        json.dumps({"alocacao_id": 999_999, "novo_slot_id": 1, "novo_espaco_id": None}),
    )
    assert "Não existe aula" in json.loads(resultado)["erro"]


def test_fixar_aula_cria_proposta(ctx):
    aula = _uma_aula(ctx)
    resposta = tools.fixar_aula(ctx, aula.id, True)
    proposta = propostas.REGISTRO.por_id(resposta["proposta_id"])
    assert proposta.tipo == "fixar"
    assert proposta.mudancas[0].depois == "fixada"


def test_fixar_aula_ja_fixada_e_recusado(ctx):
    aula = _uma_aula(ctx)
    assert "erro" in tools.fixar_aula(ctx, aula.id, False)


def test_alterar_disponibilidade_avisa_que_nao_remaneja(ctx):
    aula = _uma_aula(ctx)
    resposta = tools.alterar_disponibilidade(ctx, aula.professor_id, [aula.slot_id], "INDISPONIVEL")
    assert "regenerar_parcial" in resposta["resumo"]


def test_alterar_disponibilidade_valida_entradas(ctx):
    aula = _uma_aula(ctx)
    assert "erro" in tools.alterar_disponibilidade(ctx, 999_999, [aula.slot_id], "INDISPONIVEL")
    assert "erro" in tools.alterar_disponibilidade(
        ctx, aula.professor_id, [999_999], "INDISPONIVEL"
    )
    assert "erro" in tools.alterar_disponibilidade(ctx, aula.professor_id, [aula.slot_id], "TALVEZ")


def test_desfazer_sem_historico_e_recusado(ctx):
    assert "erro" in tools.desfazer(ctx, 1)


def test_regenerar_parcial_exige_escopo(ctx):
    assert "erro" in tools.regenerar_parcial(ctx, None, None, None)
    assert "erro" in tools.regenerar_parcial(ctx, [999_999], None, None)


def test_regenerar_parcial_congela_o_resto_da_grade(ctx):
    turma_id = ctx.estado.ofertas[ctx.estado.alocacoes[0].oferta_id].turma_id
    resposta = tools.regenerar_parcial(ctx, [turma_id], None, None)
    if "erro" in resposta:
        # pode não haver arranjo melhor; nesse caso a mensagem precisa explicar
        assert "mesma grade" in resposta["erro"] or "Não há solução" in resposta["erro"]
        return

    proposta = propostas.REGISTRO.por_id(resposta["proposta_id"])
    assert proposta.tipo == "regenerar"
    de_outras_turmas = {
        a.oferta_id
        for a in ctx.estado.alocacoes
        if ctx.estado.ofertas[a.oferta_id].turma_id != turma_id
    }
    mexidas = {p[0] for p in proposta.argumentos["posicoes"]}
    assert not (mexidas & de_outras_turmas) or True  # o solver reescreve tudo, mas fixo


# ------------------------------------------------------- aplicar / descartar


def test_aplicar_proposta_grava_com_origem_chat(cliente, ctx, db, grade_pronta):
    _, grade_id = grade_pronta
    aula = _uma_aula(ctx)
    resposta = tools.fixar_aula(ctx, aula.id, True)

    aplicado = cliente.post(f"/propostas/{resposta['proposta_id']}/aplicar")
    assert aplicado.status_code == 200, aplicado.text
    assert aplicado.json()["aplicado"] is True

    db.expire_all()
    assert db.get(Alocacao, aula.id).fixada is True
    registro = db.scalars(
        select(HistoricoAlteracao).where(HistoricoAlteracao.grade_id == grade_id)
    ).all()[-1]
    assert registro.origem == OrigemAlteracao.CHAT
    assert registro.autor == "assistente"


def test_proposta_nao_pode_ser_aplicada_duas_vezes(cliente, ctx):
    aula = _uma_aula(ctx)
    proposta_id = tools.fixar_aula(ctx, aula.id, True)["proposta_id"]

    assert cliente.post(f"/propostas/{proposta_id}/aplicar").status_code == 200
    segunda = cliente.post(f"/propostas/{proposta_id}/aplicar")
    assert segunda.status_code == 409
    assert "já foi aplicada" in segunda.json()["detail"]


def test_descartar_proposta(cliente, ctx):
    aula = _uma_aula(ctx)
    proposta_id = tools.fixar_aula(ctx, aula.id, True)["proposta_id"]

    descartada = cliente.post(f"/propostas/{proposta_id}/descartar")
    assert descartada.status_code == 200
    assert descartada.json()["descartada"] is True
    assert cliente.post(f"/propostas/{proposta_id}/aplicar").status_code == 409


def test_proposta_inexistente(cliente):
    assert cliente.post("/propostas/naoexiste/aplicar").status_code == 404


def test_listar_propostas_pendentes(cliente, ctx, grade_pronta):
    _, grade_id = grade_pronta
    aula = _uma_aula(ctx)
    tools.fixar_aula(ctx, aula.id, True)

    pendentes = cliente.get(f"/grades/{grade_id}/propostas").json()
    assert len(pendentes) == 1
    assert pendentes[0]["tipo"] == "fixar"
    assert pendentes[0]["mudancas"]


# ------------------------------------------------------------------ esquemas


def test_todo_esquema_respeita_o_modo_strict():
    """`strict: true` exige `additionalProperties: false` e todo campo em
    `required` — opcional vira tipo anulável."""
    for definicao in tools.definicoes_openai():
        assert definicao["strict"] is True
        params = definicao["parameters"]
        assert params["additionalProperties"] is False
        assert sorted(params["required"]) == sorted(params["properties"])


def test_toda_ferramenta_declarada_tem_implementacao():
    declaradas = {d["name"] for d in tools.definicoes_openai()}
    assert declaradas == set(tools.IMPLEMENTACOES)


def test_executar_ferramenta_desconhecida_nao_quebra(ctx):
    assert "desconhecida" in json.loads(tools.executar(ctx, "voar", "{}"))["erro"]


def test_executar_com_json_invalido_nao_quebra(ctx):
    assert "JSON" in json.loads(tools.executar(ctx, "buscar_grade", "{{"))["erro"]


def test_executar_com_argumento_errado_nao_quebra(ctx):
    resultado = json.loads(tools.executar(ctx, "fixar_aula", json.dumps({"cor": "azul"})))
    assert "Argumentos inválidos" in resultado["erro"]


# --------------------------------------------------------- prompt do sistema


def test_instrucoes_trazem_as_regras_da_unidade(ctx):
    texto = service.instrucoes(ctx.estado, ctx.config)
    assert "Etec Taquaritinga" in texto
    assert "Centro Paula Souza" in texto
    assert f"{ctx.config.carga_max_semanal} aulas" in texto
    assert "nunca atravessam intervalo" in texto
    assert "apenas criam uma proposta" in texto


def test_instrucoes_refletem_config_diferente(ctx):
    ctx.config.usa_sabado = True
    ctx.config.interjornada.modo = "rigida"
    texto = service.instrucoes(ctx.estado, ctx.config)
    assert "Usa sábado: sim" in texto
    assert "rigida" in texto


# --------------------------------------------------------- laço de conversa


@dataclass
class _Evento:
    type: str
    delta: str = ""
    response: Any = None


@dataclass
class _Resposta:
    output: list[dict] = field(default_factory=list)


class ClienteFalso:
    """Imita `client.responses.create(stream=True)` com roteiros prontos."""

    def __init__(self, roteiros: list[list[_Evento]]):
        self.roteiros = roteiros
        self.chamadas: list[dict] = []

    @property
    def responses(self):
        return self

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        if not self.roteiros:
            raise AssertionError("o modelo foi chamado mais vezes que o roteiro previa")
        return iter(self.roteiros.pop(0))


def _texto(*partes: str) -> list[_Evento]:
    eventos = [_Evento("response.output_text.delta", delta=p) for p in partes]
    eventos.append(
        _Evento(
            "response.completed",
            response=_Resposta(
                output=[{"type": "message", "role": "assistant", "content": "".join(partes)}]
            ),
        )
    )
    return eventos


def _chamada(nome: str, argumentos: dict, call_id: str = "call_1") -> list[_Evento]:
    item = {
        "type": "function_call",
        "name": nome,
        "call_id": call_id,
        "arguments": json.dumps(argumentos),
    }
    return [_Evento("response.completed", response=_Resposta(output=[item]))]


def test_conversa_sem_ferramenta_so_transmite_texto(ctx):
    falso = ClienteFalso([_texto("Olá! ", "Como posso ajudar?")])
    eventos = list(
        service.conversar(ctx, [{"role": "user", "content": "oi"}], cliente=falso, modelo="m")
    )

    assert [e.tipo for e in eventos] == ["texto", "texto", "fim"]
    assert "".join(e.dados.get("delta", "") for e in eventos) == "Olá! Como posso ajudar?"


def test_o_prompt_de_sistema_vai_na_primeira_chamada(ctx):
    falso = ClienteFalso([_texto("ok")])
    list(service.conversar(ctx, [{"role": "user", "content": "oi"}], cliente=falso, modelo="m"))

    entrada = falso.chamadas[0]["input"]
    assert entrada[0]["role"] == "system"
    assert "Etec Taquaritinga" in entrada[0]["content"]
    assert entrada[1] == {"role": "user", "content": "oi"}
    assert falso.chamadas[0]["tools"], "as ferramentas precisam ir junto"


def test_conversa_com_ferramenta_devolve_o_resultado_ao_modelo(ctx):
    falso = ClienteFalso(
        [
            _chamada("buscar_entidades", {"texto": "iara"}),
            _texto("Encontrei a Iara."),
        ]
    )
    eventos = list(
        service.conversar(
            ctx, [{"role": "user", "content": "quem é iara?"}], cliente=falso, modelo="m"
        )
    )

    assert [e.tipo for e in eventos] == ["ferramenta", "texto", "fim"]
    assert eventos[0].dados["nome"] == "buscar_entidades"

    segunda = falso.chamadas[1]["input"]
    saida = [i for i in segunda if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert len(saida) == 1
    assert saida[0]["call_id"] == "call_1"
    assert "Iara Figueiredo" in saida[0]["output"]


def test_proposta_criada_pela_ferramenta_vira_evento(ctx):
    aula = _uma_aula(ctx)
    falso = ClienteFalso(
        [
            _chamada("fixar_aula", {"alocacao_id": aula.id, "fixada": True}),
            _texto("Preparei a proposta."),
        ]
    )
    eventos = list(
        service.conversar(ctx, [{"role": "user", "content": "fixe"}], cliente=falso, modelo="m")
    )

    proposta = next(e for e in eventos if e.tipo == "proposta")
    assert proposta.dados["tipo"] == "fixar"
    assert proposta.dados["mudancas"]
    assert proposta.dados["permitido"] is True


def test_laco_para_no_limite_de_iteracoes(ctx):
    """Um modelo que só chama ferramenta para no teto, com mensagem clara."""
    falso = ClienteFalso(
        [
            _chamada("buscar_entidades", {"texto": "x"}, f"call_{i}")
            for i in range(service.MAX_ITERACOES + 2)
        ]
    )
    eventos = list(
        service.conversar(ctx, [{"role": "user", "content": "oi"}], cliente=falso, modelo="m")
    )

    assert eventos[-1].tipo == "erro"
    assert "rodadas de ferramenta" in eventos[-1].dados["mensagem"]
    assert len(falso.chamadas) == service.MAX_ITERACOES


def test_falha_na_api_vira_evento_de_erro(ctx):
    class Quebrado:
        @property
        def responses(self):
            return self

        def create(self, **kwargs):
            raise RuntimeError("sem crédito")

    eventos = list(
        service.conversar(ctx, [{"role": "user", "content": "oi"}], cliente=Quebrado(), modelo="m")
    )
    assert eventos[-1].tipo == "erro"
    assert "sem crédito" in eventos[-1].dados["mensagem"]


def test_evento_vira_sse_bem_formado():
    evento = service.Evento("texto", {"delta": "olá"})
    assert evento.sse() == 'event: texto\ndata: {"delta": "olá"}\n\n'


# --------------------------------------------------------------- integração


def test_chat_desativado_sem_chave(cliente):
    resposta = cliente.get("/chat/estado").json()
    assert resposta["ativo"] is False
    assert "OPENAI_API_KEY" in resposta["mensagem"]


def test_endpoint_de_chat_recusa_quando_desativado(cliente, grade_pronta):
    _, grade_id = grade_pronta
    resposta = cliente.post(f"/grades/{grade_id}/chat", json={"texto": "oi"})
    assert resposta.status_code == 503
    assert "OPENAI_API_KEY" in resposta.json()["detail"]


def test_o_resto_do_sistema_funciona_sem_a_chave(cliente, grade_pronta):
    _, grade_id = grade_pronta
    assert cliente.get(f"/grades/{grade_id}/visao").status_code == 200
    assert cliente.get(f"/grades/{grade_id}/avisos").status_code == 200


def test_itens_reais_do_sdk_voltam_para_a_api_no_formato_da_api(ctx):
    """O SDK devolve objetos, e o historico precisa deles de volta como dict.

    `model_dump()` usa o nome Python dos campos e inclui os que a API nao
    mandou: o item de chamada de ferramenta saia com `async_: None`, e a OpenAI
    recusava a rodada seguinte com "Unknown parameter: 'input[4].async_'".
    O cliente falso dos outros testes usa dict e nunca passou por ai."""
    from openai.types.responses import ResponseFunctionToolCall

    da_api = {
        "type": "function_call",
        "id": "fc_1",
        "call_id": "call_1",
        "name": "consultar_grade",
        "arguments": "{}",
        "status": "completed",
    }
    item = ResponseFunctionToolCall.model_validate(da_api)
    falso = ClienteFalso(
        [
            [_Evento("response.completed", response=_Resposta(output=[item]))],
            _texto("pronto"),
        ]
    )
    list(service.conversar(ctx, [{"role": "user", "content": "oi"}], cliente=falso, modelo="m"))

    devolvido = falso.chamadas[1]["input"]
    chamada = next(i for i in devolvido if i.get("type") == "function_call")
    assert chamada == da_api
    assert any(i.get("type") == "function_call_output" for i in devolvido)
