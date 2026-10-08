import { AnimatePresence, motion } from 'motion/react'
import {
  CalendarCheck,
  CircleCheck,
  Copy,
  GitCompare,
  Lightbulb,
  Loader2,
  Sparkles,
  TriangleAlert,
  Trash2,
  Wand2,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useGeracao } from '@/componentes/geracao'
import { Pendencias } from '@/componentes/pendencias'
import {
  Botao,
  Campo,
  Cartao,
  Dialogo,
  Entrada,
  EstadoVazio,
  Etiqueta,
  Interruptor,
  CartoesEsqueleto,
  Selecao,
} from '@/componentes/ui'
import {
  unidades,
  useApagarGrade,
  useDuplicarGrade,
  useGerarGrade,
  useGrades,
  usePreValidacao,
} from '@/lib/dados'
import { ehProvisorio } from '@/lib/recursos'
import type { Grade, StatusGrade } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const ROTULO_STATUS: Record<StatusGrade, { texto: string; tom: 'neutro' | 'alerta' | 'ok' }> = {
  RASCUNHO: { texto: 'Rascunho', tom: 'neutro' },
  AGUARDANDO_CIENCIA: { texto: 'Aguardando ciência', tom: 'alerta' },
  PUBLICADA: { texto: 'Publicada', tom: 'ok' },
}

const METRICAS: { chave: string; rotulo: string }[] = [
  { chave: 'janela_turma', rotulo: 'Janelas de turma' },
  { chave: 'janela_professor', rotulo: 'Janelas de professor' },
  { chave: 'nao_concentradas', rotulo: 'Não concentradas' },
  { chave: 'dias_professor', rotulo: 'Idas à unidade' },
  { chave: 'tempo_s', rotulo: 'Tempo (s)' },
]

export default function Grades() {
  const unidadeId = Number(useParams().unidadeId)
  const [busca, setBusca] = useSearchParams()

  const { data: listaUnidades } = unidades.useLista()
  const unidade = listaUnidades?.find((u) => u.id === unidadeId)
  const qGrades = useGrades(unidadeId)
  const qPendencias = usePreValidacao(unidadeId)
  const gerar = useGerarGrade(unidadeId)
  const apagar = useApagarGrade(unidadeId)
  const duplicar = useDuplicarGrade(unidadeId)
  const { acompanhar, atual, progresso } = useGeracao()

  const [dialogo, setDialogo] = useState<{ partirDe: number | null } | null>(null)

  const impedimentos = (qPendencias.data ?? []).filter((v) => v.severidade === 'BLOQUEANTE')
  const pronta = impedimentos.length === 0
  const selecionada = busca.get('grade') ? Number(busca.get('grade')) : null

  const iniciar = (params: Record<string, unknown>) => {
    setDialogo(null)
    gerar.mutate(params, {
      onSuccess: ({ grade_id }) => {
        acompanhar({ gradeId: grade_id, unidadeId })
        setBusca({ grade: String(grade_id) }, { replace: true })
      },
    })
  }


  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Grades de horário</h1>
          <p className="max-w-2xl text-texto-suave">
            O solver roda em segundo plano: você continua usando o sistema e acompanha pela
            pílula no topo.
          </p>
        </div>
        <Botao
          variante="primario"
          disabled={!pronta || gerar.isPending}
          onClick={() => setDialogo({ partirDe: null })}
          title={pronta ? undefined : 'Resolva as pendências da unidade primeiro'}
        >
          <Wand2 className="size-4" aria-hidden />
          Gerar grade de horário
        </Botao>
      </header>

      {!pronta && (
        <Pendencias
          violacoes={impedimentos}
          carregando={qPendencias.isPending}
          titulo="Resolva antes de gerar"
          vazio=""
        />
      )}

      {atual && progresso && !progresso.terminado && <PainelProgresso />}

      {atual && progresso?.terminado && progresso.status !== 'concluido' && (
        <PainelInviavel />
      )}

      {qGrades.isPending && !qGrades.data ? (
        <CartoesEsqueleto />
      ) : !qGrades.data?.length ? (
        <EstadoVazio
          Icone={CalendarCheck}
          titulo="Nenhuma grade ainda"
          descricao={
            pronta
              ? 'Gere a primeira grade: o solver distribui as aulas respeitando todas as regras da unidade.'
              : 'Resolva as pendências acima e a geração fica liberada.'
          }
          acao={
            pronta ? (
              <Botao variante="primario" onClick={() => setDialogo({ partirDe: null })}>
                <Wand2 className="size-4" aria-hidden />
                Gerar grade
              </Botao>
            ) : undefined
          }
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence initial={false}>
            {qGrades.data.map((grade, i) => (
              <motion.li
                key={grade.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0, transition: { delay: Math.min(i, 6) * 0.03 } }}
                exit={{ opacity: 0, scale: 0.97 }}
              >
                <CartaoGrade
                  grade={grade}
                  unidadeId={unidadeId}
                  selecionada={grade.id === selecionada}
                  aoSelecionar={() => setBusca({ grade: String(grade.id) }, { replace: true })}
                  aoRegerar={() => setDialogo({ partirDe: grade.id })}
                  aoApagar={() => apagar.mutate(grade.id)}
                  aoDuplicar={() => duplicar.mutate({ gradeId: grade.id })}
                  podeComparar={(qGrades.data?.length ?? 0) > 1}
                />
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}

      <DialogoGerar
        aberto={dialogo !== null}
        partirDe={dialogo?.partirDe ?? null}
        padraoObjetivo={unidade?.config_regras.modo_objetivo ?? 'ponderado'}
        aoFechar={() => setDialogo(null)}
        aoGerar={iniciar}
      />
    </div>
  )
}

// ------------------------------------------------------------------- painéis

function PainelProgresso() {
  const { progresso } = useGeracao()
  if (!progresso) return null

  const janelas = progresso.metricas?.janela_turma
  const gap =
    progresso.objetivo !== null && progresso.limite_inferior !== null
      ? progresso.objetivo - progresso.limite_inferior
      : null

  return (
    <Cartao className="p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Loader2 className="size-4.5 shrink-0 animate-spin text-primaria" aria-hidden />
        <h2 className="font-medium">Procurando a melhor grade…</h2>
        <span className="text-sm text-texto-suave tabular-nums">
          {progresso.tempo_s.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s
        </span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Medida
          rotulo="Soluções encontradas"
          valor={progresso.solucoes}
          detalhe="cada uma melhor que a anterior"
        />
        <Medida
          rotulo="Janelas de turma"
          valor={janelas ?? '—'}
          detalhe="o critério de maior peso"
        />
        <Medida
          rotulo="Distância do ótimo"
          valor={gap === null ? '—' : gap}
          detalhe={gap === 0 ? 'provado ótimo' : 'diferença para o limite inferior'}
        />
      </div>
      <p className="mt-4 text-xs text-texto-suave">
        Pode sair desta tela: o solver continua e a pílula no topo avisa quando terminar.
      </p>
    </Cartao>
  )
}

function PainelInviavel() {
  const { progresso } = useGeracao()
  const diagnostico = progresso?.diagnostico
  if (!progresso || !diagnostico) return null

  return (
    <Cartao className="border-erro/35 bg-erro/5 p-5">
      <div className="flex items-start gap-3">
        <TriangleAlert className="mt-0.5 size-5 shrink-0 text-erro" aria-hidden />
        <div className="space-y-3">
          <div>
            <h2 className="font-medium">Não há grade possível com os dados atuais</h2>
            <p className="mt-1 text-sm">{diagnostico.mensagem ?? progresso.mensagem}</p>
          </div>

          {!!diagnostico.culpados?.length && (
            <div className="flex flex-wrap gap-1.5">
              {diagnostico.culpados.map((c) => (
                <Etiqueta key={`${c.tipo}-${c.nome}`} tom="erro">
                  {c.nome}
                </Etiqueta>
              ))}
            </div>
          )}

          {!!diagnostico.acoes?.length && (
            <div>
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <Lightbulb className="size-4" aria-hidden />O que costuma resolver
              </p>
              <ul className="mt-1.5 list-disc space-y-0.5 ps-5 text-sm text-texto-suave">
                {diagnostico.acoes.map((a) => (
                  <li key={a.chave}>{a.descricao}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Cartao>
  )
}

const Medida = ({
  rotulo,
  valor,
  detalhe,
}: {
  rotulo: string
  valor: number | string
  detalhe: string
}) => (
  <div>
    <p className="text-sm text-texto-suave">{rotulo}</p>
    <motion.p
      key={String(valor)}
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="text-2xl font-semibold tracking-tight tabular-nums"
    >
      {valor}
    </motion.p>
    <p className="text-xs text-texto-suave">{detalhe}</p>
  </div>
)

function CartaoGrade({
  grade,
  unidadeId,
  selecionada,
  aoSelecionar,
  aoRegerar,
  aoApagar,
  aoDuplicar,
  podeComparar,
}: {
  grade: Grade
  unidadeId: number
  selecionada: boolean
  aoSelecionar: () => void
  aoRegerar: () => void
  aoApagar: () => void
  aoDuplicar: () => void
  podeComparar: boolean
}) {
  const status = ROTULO_STATUS[grade.status]
  const navegar = useNavigate()
  // Cartao otimista da copia: ainda sem id do servidor, entao nada nele abre.
  const salvando = ehProvisorio(grade.id)

  return (
    <Cartao
      className={cn(
        'h-full cursor-pointer p-4 transition-colors',
        selecionada && 'border-primaria',
        salvando && 'pointer-events-none opacity-60',
      )}
      aria-busy={salvando || undefined}
      onClick={aoSelecionar}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <Link
            to={`/unidades/${unidadeId}/grades/${grade.id}`}
            className="font-medium hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {grade.nome}
          </Link>
          <p className="mt-0.5 text-xs text-texto-suave">
            {new Date(grade.criada_em).toLocaleString('pt-BR', {
              dateStyle: 'short',
              timeStyle: 'short',
            })}
          </p>
        </div>
        <Etiqueta tom={status.tom} Icone={grade.status === 'PUBLICADA' ? CircleCheck : undefined}>
          {status.texto}
        </Etiqueta>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {METRICAS.map(({ chave, rotulo }) => (
          <div key={chave} className="flex justify-between gap-2">
            <dt className="text-texto-suave">{rotulo}</dt>
            <dd className="tabular-nums">{grade.score?.[chave] ?? '—'}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4 flex flex-wrap gap-2">
        <Botao
          tamanho="sm"
          variante="primario"
          onClick={(e) => {
            e.stopPropagation()
            navegar(`/unidades/${unidadeId}/grades/${grade.id}`)
          }}
        >
          <CalendarCheck className="size-3.5" aria-hidden />
          Abrir
        </Botao>
        <Botao
          tamanho="sm"
          onClick={(e) => {
            e.stopPropagation()
            aoRegerar()
          }}
        >
          <Sparkles className="size-3.5" aria-hidden />
          Regerar
        </Botao>
        <Botao
          tamanho="sm"
          aria-label={`Duplicar ${grade.nome}`}
          title="Cria uma versão com as mesmas aulas para experimentar"
          onClick={(e) => {
            e.stopPropagation()
            aoDuplicar()
          }}
        >
          <Copy className="size-3.5" aria-hidden />
        </Botao>
        <Botao
          tamanho="sm"
          variante="perigo"
          className="ms-auto"
          aria-label={`Excluir ${grade.nome}`}
          onClick={(e) => {
            e.stopPropagation()
            aoApagar()
          }}
        >
          <Trash2 className="size-3.5" aria-hidden />
        </Botao>
      </div>

      {podeComparar && (
        <Link
          to={`/unidades/${unidadeId}/comparar?primeira=${grade.id}`}
          onClick={(e) => e.stopPropagation()}
          className="mt-2 inline-flex items-center gap-1.5 text-xs text-texto-suave hover:text-primaria hover:underline"
        >
          <GitCompare className="size-3.5" aria-hidden />
          Comparar com outra versão
        </Link>
      )}
    </Cartao>
  )
}

// ------------------------------------------------------------------- diálogo

function DialogoGerar({
  aberto,
  partirDe,
  padraoObjetivo,
  aoFechar,
  aoGerar,
}: {
  aberto: boolean
  partirDe: number | null
  padraoObjetivo: 'ponderado' | 'lexicografico'
  aoFechar: () => void
  aoGerar: (params: Record<string, unknown>) => void
}) {
  const [tempo, setTempo] = useState(60)
  const [modo, setModo] = useState<'ponderado' | 'lexicografico'>(padraoObjetivo)
  const [manterFixadas, setManterFixadas] = useState(true)

  return (
    <Dialogo
      aberto={aberto}
      aoFechar={aoFechar}
      titulo={partirDe ? 'Regerar a grade' : 'Gerar grade de horário'}
      descricao={
        partirDe
          ? 'As aulas com cadeado são mantidas e a grade anterior entra como ponto de partida.'
          : 'O solver roda em segundo plano; você pode continuar usando o sistema.'
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          aoGerar({
            tempo_limite_s: tempo,
            modo_objetivo: modo,
            manter_fixadas: manterFixadas,
            partir_de: partirDe,
          })
        }}
        className="space-y-5"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo
            rotulo="Tempo limite (segundos)"
            dica="O solver devolve a melhor solução encontrada até acabar o tempo."
          >
            <Entrada
              type="number"
              min={1}
              max={900}
              value={tempo}
              onChange={(e) => setTempo(Number(e.target.value))}
              autoFocus
            />
          </Campo>
          <Campo
            rotulo="Objetivo"
            dica="Lexicográfico otimiza um critério por vez, na ordem das regras."
          >
            <Selecao
              valor={modo}
              aoMudar={setModo}
              aria-label="Modo do objetivo"
              opcoes={[
                { valor: 'ponderado', rotulo: 'Soma ponderada' },
                { valor: 'lexicografico', rotulo: 'Lexicográfico' },
              ]}
            />
          </Campo>
        </div>

        <Interruptor
          marcado={manterFixadas}
          aoMudar={setManterFixadas}
          rotulo="Respeitar as aulas fixadas com cadeado"
        />

        <div className="flex justify-end gap-2">
          <Botao type="button" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" variante="primario">
            <Wand2 className="size-4" aria-hidden />
            Gerar
          </Botao>
        </div>
      </form>
    </Dialogo>
  )
}
