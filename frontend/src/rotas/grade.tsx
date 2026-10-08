import { useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  ArrowLeft,
  Bot,
  CircleCheck,
  Download,
  DoorOpen,
  History,
  Printer,
  Send,
  Undo2,
  Users,
  UsersRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { GradeSemanal, LegendaGrade, type Edicao } from '@/componentes/grade-semanal'
import { PainelAvisos } from '@/componentes/painel-avisos'
import { PainelChat } from '@/componentes/painel-chat'
import { DialogoExportar } from '@/componentes/exportar'
import { Botao, Cartao, Etiqueta, GradeEsqueleto } from '@/componentes/ui'
import {
  opcoesVisao,
  useAvisos,
  useDesfazer,
  useDestinos,
  useFixarBloco,
  useGrades,
  useHistorico,
  useMoverBloco,
  usePublicar,
  useVisao,
} from '@/lib/dados'
import type { BlocoRef, TipoVisao } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const VISOES: { valor: TipoVisao; rotulo: string; Icone: typeof Users }[] = [
  { valor: 'turma', rotulo: 'Por turma', Icone: Users },
  { valor: 'professor', rotulo: 'Por professor', Icone: UsersRound },
  { valor: 'espaco', rotulo: 'Por sala', Icone: DoorOpen },
]

export default function DetalheGrade() {
  const { unidadeId: unidadeParam, gradeId: gradeParam } = useParams()
  const unidadeId = Number(unidadeParam)
  const gradeId = Number(gradeParam)
  const [busca, setBusca] = useSearchParams()
  const cliente = useQueryClient()

  const tipo = (busca.get('visao') as TipoVisao) ?? 'turma'
  const qVisao = useVisao(gradeId, tipo)
  const qGrades = useGrades(unidadeId)
  const qAvisos = useAvisos(gradeId)
  const publicar = usePublicar(gradeId)
  const [festa, setFesta] = useState(false)
  const [chatAberto, setChatAberto] = useState(false)
  const [exportando, setExportando] = useState(false)

  const [arrastando, setArrastando] = useState<BlocoRef | null>(null)
  const qDestinos = useDestinos(gradeId, arrastando)
  const mover = useMoverBloco(gradeId, tipo)
  const fixar = useFixarBloco(gradeId, tipo)
  const desfazer = useDesfazer(gradeId)
  const qHistorico = useHistorico(gradeId)

  const edicao: Edicao = {
    destinos: qDestinos.data,
    arrastando,
    aoIniciarArrasto: setArrastando,
    aoSoltar: (bloco, slotId, espacoId) =>
      mover.mutate({ ...bloco, slot_inicial: slotId, espaco_id: espacoId }),
    aoFixar: (bloco, fixada) => fixar.mutate({ ...bloco, fixada }),
  }

  const podeDesfazer = (qHistorico.data ?? []).some((r) => !r.desfeito)

  const grade = qGrades.data?.find((g) => g.id === gradeId)
  const avisos = qAvisos.data ?? []
  const bloqueado =
    avisos.some((a) => a.severidade === 'BLOQUEANTE') ||
    avisos.some((a) => a.severidade === 'ALERTA' && !a.ciente)

  // As outras visões chegam prontas: trocar de aba não mostra carregando.
  useEffect(() => {
    for (const v of VISOES) {
      if (v.valor !== tipo) cliente.prefetchQuery(opcoesVisao(gradeId, v.valor))
    }
  }, [gradeId, tipo, cliente])

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <Link
            to={`/unidades/${unidadeId}/grades`}
            className="nao-imprimir inline-flex items-center gap-1 text-sm text-texto-suave hover:text-texto"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            Todas as grades
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              {grade?.nome ?? 'Grade'}
            </h1>
            {grade?.status === 'PUBLICADA' && (
              <Etiqueta tom="ok" Icone={CircleCheck}>
                Publicada
              </Etiqueta>
            )}
          </div>
          {grade && (
            <p className="text-sm text-texto-suave">
              {grade.score?.janela_turma ?? 0} janela(s) de turma ·{' '}
              {grade.score?.janela_professor ?? 0} de professor · gerada em{' '}
              {grade.score?.tempo_s ?? '—'} s
            </p>
          )}
        </div>

        <div className="nao-imprimir flex flex-wrap gap-2">
          <Botao
            disabled={!podeDesfazer || desfazer.isPending}
            onClick={() => desfazer.mutate(1)}
            title={podeDesfazer ? undefined : 'Nada para desfazer nesta grade'}
          >
            <Undo2 className="size-4" aria-hidden />
            Desfazer
          </Botao>
          <Botao onClick={() => window.print()}>
            <Printer className="size-4" aria-hidden />
            Imprimir
          </Botao>
          <Botao onClick={() => setExportando(true)}>
            <Download className="size-4" aria-hidden />
            Exportar
          </Botao>
          <Botao
            onClick={() => setChatAberto((aberto) => !aberto)}
            aria-expanded={chatAberto}
          >
            <Bot className="size-4" aria-hidden />
            Assistente
          </Botao>
          {grade?.status !== 'PUBLICADA' && (
            <Botao
              variante="primario"
              disabled={bloqueado || publicar.isPending}
              title={
                bloqueado
                  ? 'Resolva os impedimentos e registre ciência nos alertas'
                  : undefined
              }
              onClick={() =>
                publicar.mutate(undefined, {
                  onSuccess: () => setFesta(true),
                })
              }
            >
              <Send className="size-4" aria-hidden />
              Publicar grade
            </Botao>
          )}
        </div>
      </header>

      <nav className="nao-imprimir flex flex-wrap gap-2" aria-label="Visão da grade">
        {VISOES.map(({ valor, rotulo, Icone }) => (
          <button
            key={valor}
            type="button"
            onClick={() => setBusca({ visao: valor }, { replace: true })}
            onMouseEnter={() => cliente.prefetchQuery(opcoesVisao(gradeId, valor))}
            aria-current={valor === tipo ? 'page' : undefined}
            className={cn(
              'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors',
              valor === tipo
                ? 'border-primaria bg-primaria-suave font-medium text-primaria'
                : 'border-borda bg-superficie text-texto-suave hover:bg-superficie-2',
            )}
          >
            <Icone className="size-4" aria-hidden />
            {rotulo}
          </button>
        ))}
      </nav>

      <Cartao className="overflow-hidden">
        {qVisao.isPending && !qVisao.data ? (
          <GradeEsqueleto />
        ) : qVisao.data ? (
          <GradeSemanal visao={qVisao.data} edicao={edicao} />
        ) : null}
      </Cartao>

      <LegendaGrade edicao />

      <div className="nao-imprimir grid gap-6 lg:grid-cols-[1fr_20rem]">
        <PainelAvisos
          gradeId={gradeId}
          unidadeId={unidadeId}
          jaResolvida={Boolean(grade?.parametros_solver?.resolver_avisos)}
        />
        <Historico registros={qHistorico.data} />
      </div>

      <DialogoExportar
        gradeId={gradeId}
        aberto={exportando}
        aoFechar={() => setExportando(false)}
      />
      <PainelChat
        gradeId={gradeId}
        aberto={chatAberto}
        aoFechar={() => setChatAberto(false)}
      />
      <Confete ativo={festa} aoTerminar={() => setFesta(false)} />
    </div>
  )
}

function Historico({
  registros,
}: {
  registros: { id: number; descricao: string; origem: string; timestamp: string; desfeito: boolean }[] | undefined
}) {
  if (!registros?.length) return null
  return (
    <Cartao className="h-fit p-5">
      <div className="flex items-center gap-2">
        <History className="size-4.5 text-texto-suave" aria-hidden />
        <h2 className="font-medium">Alterações</h2>
      </div>
      <ol className="mt-3 space-y-2 text-sm">
        {registros.slice(0, 12).map((r) => (
          <li key={r.id} className={cn('flex gap-2', r.desfeito && 'opacity-50 line-through')}>
            <span className="shrink-0 text-xs text-texto-suave tabular-nums">
              {new Date(r.timestamp).toLocaleTimeString('pt-BR', {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
            <span className="min-w-0 flex-1">{r.descricao}</span>
            {r.origem === 'CHAT' && (
              <Etiqueta className="shrink-0">chat</Etiqueta>
            )}
          </li>
        ))}
      </ol>
    </Cartao>
  )
}

/** Confete discreto ao publicar (seção 11.1). Sem dependência: 24 divs. */
function Confete({ ativo, aoTerminar }: { ativo: boolean; aoTerminar: () => void }) {
  const semAnimacao = useReducedMotion()
  useEffect(() => {
    if (!ativo) return
    const t = setTimeout(aoTerminar, 1800)
    return () => clearTimeout(t)
  }, [ativo, aoTerminar])

  if (semAnimacao) return null

  return (
    <AnimatePresence>
      {ativo && (
        <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden" aria-hidden>
          {Array.from({ length: 24 }, (_, i) => (
            <motion.span
              key={i}
              initial={{ opacity: 1, y: '45vh', x: `${45 + (i % 8) * 1.5}vw`, scale: 1 }}
              animate={{
                opacity: 0,
                y: `${20 + (i % 5) * 12}vh`,
                x: `${10 + ((i * 37) % 80)}vw`,
                rotate: (i % 2 ? 1 : -1) * 320,
                scale: 0.6,
              }}
              exit={{ opacity: 0 }}
              transition={{ duration: 1.4, ease: 'easeOut', delay: (i % 6) * 0.04 }}
              className="absolute size-2 rounded-[2px]"
              style={{ background: `oklch(0.7 0.18 ${(i * 47) % 360})` }}
            />
          ))}
        </div>
      )}
    </AnimatePresence>
  )
}
