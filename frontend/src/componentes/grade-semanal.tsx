/**
 * A grade de horário: linhas por faixa de horário, colunas por turma, professor
 * ou espaço.
 *
 * As linhas são `(dia, início, fim)` e não o número da aula — a mesma unidade
 * pode ter turnos com horários diferentes, e duas "1ª aula" em horários
 * distintos não são a mesma linha.
 *
 * Com `edicao`, o bloco inteiro vira arrastável: os destinos válidos acendem em
 * verde, os que geram alerta em amarelo e os proibidos em vermelho, tudo com
 * **uma** consulta no início do arrasto.
 */
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { motion, useReducedMotion } from 'motion/react'
import { FlaskConical, Lock, LockOpen, Wifi } from 'lucide-react'
import { useState } from 'react'

import { estiloDisciplina } from '@/lib/cores'
import {
  DIAS_CURTOS,
  hhmm,
  type BlocoRef,
  type CelulaGrade,
  type DestinoPossivel,
  type TipoVisao,
  type VisaoGrade,
} from '@/lib/tipos'
import { cn } from '@/lib/utils'

const COLUNA_DE: Record<TipoVisao, (c: CelulaGrade) => number> = {
  turma: (c) => c.turma_id,
  professor: (c) => c.professor_id,
  espaco: (c) => c.espaco_id ?? -1,
}

const chaveLinha = (dia: number, inicio: string) => `${dia}-${inicio}`
const mesmoBloco = (a: BlocoRef, c: CelulaGrade) =>
  a.oferta_id === c.oferta_id && a.bloco_idx === c.bloco_idx

export type Edicao = {
  /** Destinos já avaliados pelo servidor, por `slot_id`. */
  destinos: DestinoPossivel[] | undefined
  arrastando: BlocoRef | null
  aoIniciarArrasto: (bloco: BlocoRef | null) => void
  aoSoltar: (bloco: BlocoRef, slotId: number, espacoId?: number) => void
  aoFixar: (bloco: BlocoRef, fixada: boolean) => void
}

/**
 * Horários vagos que ainda têm aula depois no mesmo dia, por `linha|coluna`.
 *
 * Duas armadilhas, ambas já cometidas aqui:
 * 1. Vago no **fim** do dia não é janela — sair mais cedo é o resultado
 *    desejado, não um defeito (spec 5.4.1).
 * 2. Só conta onde a coluna realmente tem horário: uma turma do noturno não
 *    tem janela às 07h00, ela simplesmente não tem aula de manhã.
 *
 * Por sala não existe janela nenhuma: sala vaga é sala livre.
 */
export function calcularJanelas(visao: VisaoGrade, ativo = true): Set<string> {
  const janelas = new Set<string>()
  if (!ativo || visao.tipo === 'espaco') return janelas

  const coluna = COLUNA_DE[visao.tipo]
  const ocupadas = new Set(
    visao.celulas.map((c) => `${chaveLinha(c.dia, c.inicio)}|${coluna(c)}`),
  )
  const existeSlot = new Set(
    visao.slots.map((s) => `${s.modelo_turno_id}|${chaveLinha(s.dia, s.inicio)}`),
  )
  const dias = [...new Set(visao.horarios.map((h) => h.dia))]

  // Turnos em que cada coluna de fato tem aula. A turma declara o seu
  // (`modelo_turno_id`); o professor não tem turno nenhum declarado, e sem
  // isto um docente que só leciona à noite aparecia com "janela" a manhã
  // inteira numa unidade que também usa a manhã. É o mesmo critério que o
  // PDF usa em `export/grade.py`.
  const turnosDaColuna = new Map<number, Set<number>>()
  for (const c of visao.celulas) {
    const id = coluna(c)
    const turnos = turnosDaColuna.get(id) ?? new Set<number>()
    turnos.add(c.modelo_turno_id)
    turnosDaColuna.set(id, turnos)
  }

  for (const col of visao.colunas) {
    const turnos =
      col.modelo_turno_id !== null
        ? [col.modelo_turno_id]
        : [...(turnosDaColuna.get(col.id) ?? [])]

    for (const dia of dias) {
      const doDia = visao.horarios
        .filter((h) => h.dia === dia)
        .filter((h) =>
          turnos.some((turno) => existeSlot.has(`${turno}|${chaveLinha(dia, h.inicio)}`)),
        )
      const cheias = doDia.map((h) => ocupadas.has(`${chaveLinha(dia, h.inicio)}|${col.id}`))
      const ultima = cheias.lastIndexOf(true)
      doDia.forEach((h, i) => {
        if (i < ultima && !cheias[i]) janelas.add(`${chaveLinha(dia, h.inicio)}|${col.id}`)
      })
    }
  }
  return janelas
}

export function GradeSemanal({
  visao,
  destacarJanelas = true,
  edicao,
}: {
  visao: VisaoGrade
  destacarJanelas?: boolean
  edicao?: Edicao
}) {
  const semAnimacao = useReducedMotion()
  const coluna = COLUNA_DE[visao.tipo]
  const [sobre, setSobre] = useState<number | null>(null)

  const sensores = useSensors(
    // 6 px antes de considerar arrasto: um clique continua sendo clique.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  )

  const mapa = new Map<string, CelulaGrade>()
  for (const c of visao.celulas) {
    mapa.set(`${chaveLinha(c.dia, c.inicio)}|${coluna(c)}`, c)
  }

  const slotPorPosicao = new Map(
    visao.slots.map((s) => [`${s.modelo_turno_id}|${chaveLinha(s.dia, s.inicio)}`, s.id]),
  )
  const severidadePorSlot = new Map(
    (edicao?.destinos ?? []).map((d) => [d.slot_id, d] as const),
  )

  const dias = [...new Set(visao.horarios.map((h) => h.dia))].sort((a, b) => a - b)

  const janelas = calcularJanelas(visao, destacarJanelas)

  const celulaArrastada = edicao?.arrastando
    ? visao.celulas.find((c) => mesmoBloco(edicao.arrastando!, c))
    : undefined

  /** O turno do bloco arrastado define qual `slot_id` é o destino. */
  const modeloArrastado = celulaArrastada?.modelo_turno_id

  /**
   * Em que coluna o bloco pode cair.
   *
   * Por turma e por professor, só na coluna dele: soltar na coluna de outra
   * turma seria trocar de quem é a aula, não movê-la — e todas as colunas de
   * uma linha compartilham o mesmo horário, então sem esta trava o destino
   * virava silenciosamente o próprio lugar do bloco.
   *
   * Por sala é o contrário: a coluna **é** o destino, e arrastar para outra
   * coluna troca a sala da aula.
   */
  const colunaObrigatoria =
    celulaArrastada && visao.tipo !== 'espaco' ? coluna(celulaArrastada) : null

  const aoIniciar = (evento: DragStartEvent) => {
    edicao?.aoIniciarArrasto(evento.active.data.current?.bloco ?? null)
  }
  const aoTerminar = (evento: DragEndEvent) => {
    const bloco = evento.active.data.current?.bloco as BlocoRef | undefined
    const dados = evento.over?.data.current as
      | { slotId?: number; espacoId?: number }
      | undefined
    edicao?.aoIniciarArrasto(null)
    setSobre(null)
    if (bloco && dados?.slotId !== undefined) {
      edicao?.aoSoltar(bloco, dados.slotId, dados.espacoId)
    }
  }

  const tabela = (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">
          Grade de horário por {visao.tipo}, com dias e horários nas linhas
        </caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky start-0 z-10 w-28 bg-superficie p-2 text-start text-xs font-medium text-texto-suave"
            >
              Horário
            </th>
            {visao.colunas.map((c) => (
              <th
                key={c.id}
                scope="col"
                className="min-w-40 border-s border-borda p-2 text-start align-bottom"
              >
                <span className="block truncate font-medium">{c.titulo}</span>
                {c.subtitulo && (
                  <span className="block truncate text-xs font-normal text-texto-suave">
                    {c.subtitulo}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>

        {dias.map((dia) => {
          const doDia = visao.horarios.filter((h) => h.dia === dia)
          return (
            <tbody key={dia} className="border-t-2 border-borda-forte">
              {doDia.map((h, i) => (
                <tr key={h.inicio} className="border-t border-borda">
                  <th
                    scope="row"
                    className="sticky start-0 z-10 bg-superficie p-2 text-start font-normal"
                  >
                    {i === 0 && (
                      <span className="block text-xs font-semibold">{DIAS_CURTOS[dia]}</span>
                    )}
                    <span className="block text-xs text-texto-suave tabular-nums">
                      {hhmm(h.inicio)}–{hhmm(h.fim)}
                    </span>
                  </th>

                  {visao.colunas.map((col) => {
                    const chave = `${chaveLinha(dia, h.inicio)}|${col.id}`
                    const celula = mapa.get(chave)
                    const aceita =
                      modeloArrastado !== undefined &&
                      (colunaObrigatoria === null || colunaObrigatoria === col.id)
                    const slotId = aceita
                      ? slotPorPosicao.get(`${modeloArrastado}|${chaveLinha(dia, h.inicio)}`)
                      : undefined
                    const destino = slotId !== undefined ? severidadePorSlot.get(slotId) : undefined

                    return (
                      <Celula
                        key={col.id}
                        chave={chave}
                        slotId={slotId}
                        destino={destino}
                        arrastando={Boolean(edicao?.arrastando)}
                        janela={janelas.has(chave)}
                        realcada={slotId !== undefined && sobre === slotId}
                        aoEntrar={setSobre}
                        espacoId={visao.tipo === 'espaco' ? col.id : undefined}
                      >
                        {celula ? (
                          <Aula
                            celula={celula}
                            visao={visao.tipo}
                            semAnimacao={Boolean(semAnimacao)}
                            indice={i}
                            edicao={edicao}
                          />
                        ) : janelas.has(chave) && !edicao?.arrastando ? (
                          <span className="block px-1 py-2 text-xs text-alerta">janela</span>
                        ) : null}
                      </Celula>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          )
        })}
      </table>
    </div>
  )

  if (!visao.colunas.length) {
    return <p className="p-6 text-sm text-texto-suave">Nada para mostrar nesta visão.</p>
  }
  if (!edicao) return tabela

  return (
    <DndContext sensors={sensores} onDragStart={aoIniciar} onDragEnd={aoTerminar}>
      {tabela}
      <DragOverlay dropAnimation={null}>
        {celulaArrastada && (
          <div
            style={estiloDisciplina(celulaArrastada.disciplina_sigla)}
            className="disciplina rounded-md border px-2 py-1.5 text-xs font-semibold shadow-grade"
          >
            {celulaArrastada.disciplina_sigla}
            {celulaArrastada.subturma ? ` ${celulaArrastada.subturma}` : ''}
          </div>
        )}
      </DragOverlay>
    </DndContext>
  )
}

const TOM_DESTINO: Record<string, string> = {
  livre: 'bg-ok/15 outline outline-1 outline-ok/40',
  ALERTA: 'bg-alerta/15 outline outline-1 outline-alerta/40',
  BLOQUEANTE: 'bg-erro/15 outline outline-1 outline-erro/40',
  INFO: 'bg-ok/10 outline outline-1 outline-ok/30',
}

function Celula({
  chave,
  slotId,
  espacoId,
  destino,
  arrastando,
  janela,
  realcada,
  aoEntrar,
  children,
}: {
  chave: string
  slotId: number | undefined
  espacoId: number | undefined
  destino: DestinoPossivel | undefined
  arrastando: boolean
  janela: boolean
  realcada: boolean
  aoEntrar: (slotId: number | null) => void
  children: React.ReactNode
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: chave,
    disabled: slotId === undefined || destino?.severidade === 'BLOQUEANTE',
    data: { slotId, espacoId },
  })

  const tom =
    arrastando && destino
      ? TOM_DESTINO[destino.severidade ?? 'livre']
      : arrastando && slotId !== undefined
        ? 'bg-superficie-2'
        : ''

  return (
    <td
      ref={setNodeRef}
      data-slot={slotId}
      onPointerEnter={() => arrastando && aoEntrar(slotId ?? null)}
      title={destino?.motivos?.[0]}
      className={cn(
        'border-s border-borda p-1 align-top transition-colors',
        janela && !arrastando && 'bg-alerta/10',
        tom,
        (isOver || realcada) && destino?.severidade !== 'BLOQUEANTE' && 'ring-2 ring-primaria',
      )}
    >
      {children}
    </td>
  )
}

function Aula({
  celula,
  visao,
  semAnimacao,
  indice,
  edicao,
}: {
  celula: CelulaGrade
  visao: TipoVisao
  semAnimacao: boolean
  indice: number
  edicao?: Edicao
}) {
  const bloco: BlocoRef = { oferta_id: celula.oferta_id, bloco_idx: celula.bloco_idx }
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `bloco-${celula.oferta_id}-${celula.bloco_idx}-${celula.slot_id}`,
    disabled: !edicao || celula.fixada,
    data: { bloco },
  })

  const detalhe = {
    turma: celula.professor_nome,
    professor: celula.turma_rotulo,
    espaco: `${celula.turma_rotulo} · ${celula.professor_nome}`,
  }[visao]
  const local = visao === 'espaco' ? null : (celula.espaco_nome ?? 'remota')

  return (
    <motion.div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      layout={!semAnimacao}
      initial={semAnimacao ? false : { opacity: 0, y: -6 }}
      animate={{ opacity: isDragging ? 0.35 : 1, y: 0 }}
      transition={{ delay: Math.min(indice, 8) * 0.02, duration: 0.2 }}
      style={estiloDisciplina(celula.disciplina_sigla)}
      title={`${celula.disciplina_nome} — ${celula.turma_rotulo} — ${celula.professor_nome}`}
      className={cn(
        'disciplina block w-full rounded-md border px-2 py-1.5 text-start',
        edicao && !celula.fixada && 'cursor-grab active:cursor-grabbing',
      )}
    >
      <span className="flex items-center gap-1">
        <span className="truncate text-xs font-semibold">
          {celula.disciplina_sigla}
          {celula.subturma ? ` ${celula.subturma}` : ''}
        </span>
        <span className="ms-auto flex shrink-0 items-center gap-0.5">
          {celula.remota && <Wifi className="size-3" aria-label="Aula remota" />}
          {celula.precisa_laboratorio && (
            <FlaskConical className="size-3" aria-label="Laboratório" />
          )}
          {edicao ? (
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => edicao.aoFixar(bloco, !celula.fixada)}
              aria-label={celula.fixada ? 'Liberar esta aula' : 'Fixar esta aula'}
              // `currentColor` em vez de preto: a celula ja e' escura no tema
              // escuro, e um preto translucido ali nao aparece.
              className="rounded p-0.5 hover:bg-current/15"
            >
              {celula.fixada ? (
                <Lock className="size-3" aria-hidden />
              ) : (
                <LockOpen className="size-3 opacity-40" aria-hidden />
              )}
            </button>
          ) : (
            celula.fixada && <Lock className="size-3" aria-label="Aula fixada" />
          )}
        </span>
      </span>
      <span className="block truncate text-[0.7rem] leading-tight opacity-85">{detalhe}</span>
      {local && (
        <span className="block truncate text-[0.7rem] leading-tight opacity-70">{local}</span>
      )}
    </motion.div>
  )
}

export function LegendaGrade({ edicao }: { edicao?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-texto-suave">
      <span className="flex items-center gap-1.5">
        <Wifi className="size-3.5" aria-hidden />
        aula remota (não ocupa sala)
      </span>
      <span className="flex items-center gap-1.5">
        <FlaskConical className="size-3.5" aria-hidden />
        precisa de laboratório
      </span>
      <span className="flex items-center gap-1.5">
        <Lock className="size-3.5" aria-hidden />
        fixada: não sai do lugar ao regerar
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block size-3 rounded-sm bg-alerta/25" aria-hidden />
        janela: horário vago com aula depois
      </span>
      {edicao && (
        <>
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm bg-ok/30" aria-hidden />
            destino livre
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm bg-erro/30" aria-hidden />
            destino proibido
          </span>
        </>
      )}
    </div>
  )
}
