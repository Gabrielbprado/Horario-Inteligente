import { motion } from 'motion/react'
import { Award, Eraser, RefreshCw, Sparkles, Trash2, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { Pendencias } from '@/componentes/pendencias'
import { Botao, Cartao, EstadoVazio, Etiqueta, LinhasEsqueleto, Selecao } from '@/componentes/ui'
import { estiloDisciplina } from '@/lib/cores'
import {
  atribuicoes,
  habilitacoes,
  professores,
  useAtribuirProfessor,
  useClassificacao,
  useLimparAtribuicao,
  useOfertas,
  useSugerirAtribuicao,
} from '@/lib/dados'
import type { Oferta, Violacao } from '@/lib/tipos'
import { cn } from '@/lib/utils'

export default function Atribuicao() {
  const unidadeId = Number(useParams().unidadeId)
  const filtro = { unidade_id: unidadeId }

  const qOfertas = useOfertas(filtro)
  const qClassificacao = useClassificacao(unidadeId)
  const qHabilitacoes = habilitacoes.useLista()
  const qProfessores = professores.useLista()
  const qAtribuicoes = atribuicoes.useLista()

  const sugerir = useSugerirAtribuicao(unidadeId)
  const limpar = useLimparAtribuicao(unidadeId)
  const atribuir = useAtribuirProfessor(filtro)

  const [avisos, setAvisos] = useState<Violacao[] | null>(null)

  const ofertas = qOfertas.data ?? []
  const atribuidas = ofertas.filter((o) => o.professor_id !== null).length

  // Só quem está habilitado na disciplina pode ser oferecido no seletor.
  const habilitadosPor = new Map<number, number[]>()
  for (const h of qHabilitacoes.data ?? []) {
    habilitadosPor.set(h.disciplina_id, [
      ...(habilitadosPor.get(h.disciplina_id) ?? []),
      h.professor_id,
    ])
  }
  const nomePorProfessor = new Map((qProfessores.data ?? []).map((p) => [p.id, p.nome]))
  const idAtribuicaoPorOferta = new Map(
    (qAtribuicoes.data ?? []).map((a) => [a.oferta_id, a.id]),
  )
  const classificacaoPor = new Map(
    (qClassificacao.data ?? []).map((c) => [c.professor_id, c]),
  )

  const porTurma = new Map<string, Oferta[]>()
  for (const o of ofertas) {
    const chave = `${o.curso_sigla} · ${o.turma_periodo}`
    porTurma.set(chave, [...(porTurma.get(chave) ?? []), o])
  }

  const executar = (substituir: boolean) =>
    sugerir.mutate({ substituir }, { onSuccess: (r) => setAvisos(r.avisos) })

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Atribuição de aulas</h1>
          <p className="max-w-2xl text-texto-suave">
            A sugestão percorre a lista de classificação docente como no ato de atribuição.
            Quando dois docentes podiam assumir a mesma oferta, o sistema registra quem levou e
            por qual critério.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {atribuidas > 0 && (
            <Botao
              variante="perigo"
              onClick={() => {
                limpar.mutate()
                setAvisos(null)
              }}
            >
              <Eraser className="size-4" aria-hidden />
              Limpar
            </Botao>
          )}
          {atribuidas > 0 && (
            <Botao onClick={() => executar(true)} disabled={sugerir.isPending}>
              <RefreshCw className={cn('size-4', sugerir.isPending && 'animate-spin')} aria-hidden />
              Refazer do zero
            </Botao>
          )}
          <Botao variante="primario" onClick={() => executar(false)} disabled={sugerir.isPending}>
            <Wand2 className="size-4" aria-hidden />
            Sugerir atribuição
          </Botao>
        </div>
      </header>

      {avisos && (
        <Pendencias
          violacoes={avisos}
          carregando={false}
          titulo="Resultado da atribuição"
          vazio="Nenhuma disputa: cada oferta tinha um único candidato."
        />
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          {qOfertas.isPending && !qOfertas.data ? (
            <LinhasEsqueleto linhas={6} />
          ) : !ofertas.length ? (
            <EstadoVazio
              Icone={Sparkles}
              titulo="Nenhuma oferta para atribuir"
              descricao="Cadastre as disciplinas e as turmas do curso; as ofertas são geradas junto."
            />
          ) : (
            [...porTurma.entries()].map(([turma, lista]) => (
              <section key={turma} className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <h2 className="font-medium">{turma}</h2>
                  <span className="text-xs text-texto-suave">
                    {lista.filter((o) => o.professor_id).length} de {lista.length} atribuídas
                  </span>
                </div>
                <ul className="space-y-2">
                  {lista.map((oferta) => {
                    const candidatos = (habilitadosPor.get(oferta.disciplina_id) ?? [])
                      .map((pid) => ({ pid, c: classificacaoPor.get(pid) }))
                      .filter((x) => x.c)
                      .sort((a, b) => a.c!.posicao - b.c!.posicao)
                    return (
                      <motion.li key={oferta.id} layout>
                        <Cartao className="flex flex-wrap items-center gap-3 p-3">
                          <span
                            style={estiloDisciplina(oferta.disciplina_sigla)}
                            className="disciplina shrink-0 rounded-md border px-2 py-1 text-xs font-semibold"
                          >
                            {oferta.disciplina_sigla}
                            {oferta.subturma ? ` ${oferta.subturma}` : ''}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm">
                            {oferta.disciplina_nome}
                          </span>
                          <span className="shrink-0 text-xs text-texto-suave tabular-nums">
                            {oferta.aulas_semanais} aulas
                          </span>
                          <div className="w-full sm:w-64">
                            {candidatos.length ? (
                              <Selecao
                                valor={
                                  oferta.professor_id ? String(oferta.professor_id) : undefined
                                }
                                placeholder="Sem professor"
                                aria-label={`Professor de ${oferta.disciplina_nome}`}
                                aoMudar={(v) =>
                                  atribuir.mutate({
                                    oferta_id: oferta.id,
                                    professor_id: Number(v),
                                    atribuicao_id: idAtribuicaoPorOferta.get(oferta.id) ?? null,
                                  })
                                }
                                opcoes={candidatos.map(({ pid, c }) => ({
                                  valor: String(pid),
                                  rotulo: `${c!.posicao}º · ${nomePorProfessor.get(pid) ?? pid}`,
                                }))}
                              />
                            ) : (
                              <Etiqueta tom="erro">Ninguém habilitado</Etiqueta>
                            )}
                          </div>
                          {oferta.professor_id && (
                            <button
                              type="button"
                              aria-label={`Remover professor de ${oferta.disciplina_nome}`}
                              onClick={() =>
                                atribuir.mutate({
                                  oferta_id: oferta.id,
                                  professor_id: null,
                                  atribuicao_id: idAtribuicaoPorOferta.get(oferta.id) ?? null,
                                })
                              }
                              className="rounded p-1 text-texto-suave hover:text-erro"
                            >
                              <Trash2 className="size-3.5" aria-hidden />
                            </button>
                          )}
                        </Cartao>
                      </motion.li>
                    )
                  })}
                </ul>
              </section>
            ))
          )}
        </div>

        <ListaClassificacao carregando={qClassificacao.isPending} lista={qClassificacao.data} />
      </div>
    </div>
  )
}

function ListaClassificacao({
  carregando,
  lista,
}: {
  carregando: boolean
  lista: { posicao: number; professor_nome: string; pontuacao: number; carga_max: number; aulas_atribuidas: number; tipo_contrato: string }[] | undefined
}) {
  return (
    <Cartao className="h-fit p-5 lg:sticky lg:top-20">
      <div className="flex items-center gap-2">
        <Award className="size-4.5 text-texto-suave" aria-hidden />
        <h2 className="font-medium">Classificação docente</h2>
      </div>
      <p className="mt-1 text-xs text-texto-suave">
        Ordem em que as aulas são oferecidas. A barra mostra a carga já atribuída.
      </p>

      {carregando && !lista ? (
        <div className="mt-4">
          <LinhasEsqueleto linhas={5} />
        </div>
      ) : (
        <ol className="mt-4 space-y-2.5">
          {(lista ?? []).map((c) => {
            const proporcao = c.carga_max ? c.aulas_atribuidas / c.carga_max : 0
            return (
              <li key={c.posicao}>
                <div className="flex items-baseline gap-2 text-sm">
                  <span className="w-5 shrink-0 text-xs text-texto-suave tabular-nums">
                    {c.posicao}º
                  </span>
                  <span className="min-w-0 flex-1 truncate">{c.professor_nome}</span>
                  <span className="shrink-0 text-xs tabular-nums">
                    {c.pontuacao.toLocaleString('pt-BR', { minimumFractionDigits: 1 })}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 ps-7">
                  <div
                    className="h-1.5 flex-1 overflow-hidden rounded-full bg-superficie-2"
                    role="img"
                    aria-label={`${c.aulas_atribuidas} de ${c.carga_max} aulas`}
                  >
                    <motion.div
                      className={cn(
                        'h-full rounded-full',
                        proporcao >= 1 ? 'bg-alerta' : 'bg-primaria',
                      )}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(100, proporcao * 100)}%` }}
                      transition={{ duration: 0.35, ease: 'easeOut' }}
                    />
                  </div>
                  <span className="shrink-0 text-xs text-texto-suave tabular-nums">
                    {c.aulas_atribuidas}/{c.carga_max}
                  </span>
                  {c.tipo_contrato === 'DETERMINADO' && (
                    <Etiqueta className="shrink-0">temp.</Etiqueta>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Cartao>
  )
}
