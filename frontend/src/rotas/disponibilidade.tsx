import { motion } from 'motion/react'
import { Ban, Check, Copy, Moon, Star, UserCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { Botao, Cartao, EstadoVazio, LinhasEsqueleto, Selecao } from '@/componentes/ui'
import {
  cursos,
  disponibilidades,
  professores,
  turmas,
  unidades,
  useDisponibilidadeEmLote,
  useModelosTurno,
  vinculos,
} from '@/lib/dados'
import { DIAS_CURTOS, hhmm, type Slot, type StatusDisponibilidade } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const ESTADOS: {
  valor: StatusDisponibilidade
  rotulo: string
  Icone: typeof Check
  classe: string
}[] = [
  {
    valor: 'DISPONIVEL',
    rotulo: 'Disponível',
    Icone: Check,
    classe: 'border-borda bg-superficie text-texto-suave',
  },
  {
    valor: 'PREFERENCIAL',
    rotulo: 'Preferencial',
    Icone: Star,
    classe: 'border-ok/40 bg-ok/10 text-ok',
  },
  {
    valor: 'INDISPONIVEL',
    rotulo: 'Indisponível',
    Icone: Ban,
    classe: 'border-erro/40 bg-erro/10 text-erro',
  },
]

/** Clicar num slot avança para o próximo estado. */
const PROXIMO: Record<StatusDisponibilidade, StatusDisponibilidade> = {
  DISPONIVEL: 'PREFERENCIAL',
  PREFERENCIAL: 'INDISPONIVEL',
  INDISPONIVEL: 'DISPONIVEL',
}

export default function Disponibilidade() {
  const unidadeId = Number(useParams().unidadeId)
  const [busca, setBusca] = useSearchParams()

  const { data: listaUnidades } = unidades.useLista()
  const unidade = listaUnidades?.find((u) => u.id === unidadeId)

  const qProfessores = professores.useLista(
    unidade ? { escopo_id: unidade.escopo_id } : undefined,
    Boolean(unidade),
  )
  const qVinculos = vinculos.useLista({ unidade_id: unidadeId })
  const qModelos = useModelosTurno(unidadeId)
  const qCursos = cursos.useLista({ unidade_id: unidadeId })
  const qTurmas = turmas.useLista()

  const idsVinculados = new Set((qVinculos.data ?? []).map((v) => v.professor_id))
  const elegiveis = (qProfessores.data ?? []).filter((p) => idsVinculados.has(p.id))

  const professorId = busca.get('professor') ? Number(busca.get('professor')) : null
  const modeloId = busca.get('turno') ? Number(busca.get('turno')) : null

  // Uma unica escrita por vez: dois `setBusca` no mesmo tick partem do mesmo
  // `busca` e o segundo descarta o primeiro.
  const definir = (mudancas: Record<string, number>) =>
    setBusca(
      (atual) => {
        const novo = new URLSearchParams(atual)
        for (const [chave, valor] of Object.entries(mudancas)) novo.set(chave, String(valor))
        return novo
      },
      { replace: true },
    )

  // Modelo padrao: o mais usado pelas turmas da unidade. Cair no primeiro em
  // ordem alfabetica mostraria um turno que talvez nem esteja em uso.
  const idsCursos = new Set((qCursos.data ?? []).map((c) => c.id))
  const usoPorModelo = new Map<number, number>()
  for (const t of qTurmas.data ?? []) {
    if (idsCursos.has(t.curso_id)) {
      usoPorModelo.set(t.modelo_turno_id, (usoPorModelo.get(t.modelo_turno_id) ?? 0) + 1)
    }
  }
  const modeloPadrao =
    [...usoPorModelo.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? qModelos.data?.[0]?.id

  useEffect(() => {
    const faltando: Record<string, number> = {}
    if (professorId === null && elegiveis.length) faltando.professor = elegiveis[0].id
    if (modeloId === null && modeloPadrao !== undefined) faltando.turno = modeloPadrao
    if (Object.keys(faltando).length) definir(faltando)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qProfessores.data, qVinculos.data, qModelos.data, qTurmas.data, qCursos.data])

  const modelo = qModelos.data?.find((mt) => mt.id === modeloId)

  if (qProfessores.isPending && !qProfessores.data) return <LinhasEsqueleto linhas={5} />

  if (!elegiveis.length) {
    return (
      <EstadoVazio
        Icone={UserCheck}
        titulo="Nenhum professor vinculado a esta unidade"
        descricao="Crie o vínculo do docente com a unidade para marcar a disponibilidade dele."
      />
    )
  }

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Disponibilidade</h1>
        <p className="text-texto-suave">
          Clique num horário para alternar entre disponível, preferencial e indisponível. O que
          não for marcado conta como disponível.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-56 flex-col gap-1.5">
          <span className="text-sm font-medium text-texto-suave">Professor</span>
          <Selecao
            valor={professorId ? String(professorId) : undefined}
            aoMudar={(v) => definir({ professor: Number(v) })}
            aria-label="Professor"
            opcoes={elegiveis.map((p) => ({ valor: String(p.id), rotulo: p.nome }))}
          />
        </label>
        <label className="flex min-w-56 flex-col gap-1.5">
          <span className="text-sm font-medium text-texto-suave">Modelo de turno</span>
          <Selecao
            valor={modeloId ? String(modeloId) : undefined}
            aoMudar={(v) => definir({ turno: Number(v) })}
            aria-label="Modelo de turno"
            opcoes={(qModelos.data ?? []).map((mt) => ({
              valor: String(mt.id),
              rotulo: mt.nome,
            }))}
          />
        </label>

        <div className="ms-auto flex flex-wrap items-center gap-3 text-xs">
          {ESTADOS.map(({ valor, rotulo, Icone, classe }) => (
            <span key={valor} className="flex items-center gap-1.5">
              <span className={cn('grid size-5 place-items-center rounded border', classe)}>
                <Icone className="size-3" aria-hidden />
              </span>
              {rotulo}
            </span>
          ))}
        </div>
      </div>

      {professorId !== null && modelo ? (
        <GradeDisponibilidade
          key={`${professorId}-${modelo.id}`}
          professorId={professorId}
          unidadeId={unidadeId}
          slots={modelo.slots}
        />
      ) : (
        <LinhasEsqueleto linhas={4} />
      )}
    </div>
  )
}

function GradeDisponibilidade({
  professorId,
  unidadeId,
  slots,
}: {
  professorId: number
  unidadeId: number
  slots: Slot[]
}) {
  const q = disponibilidades.useLista({ professor_id: professorId })
  const lote = useDisponibilidadeEmLote(professorId, unidadeId)
  const [ultimoDia, setUltimoDia] = useState<number | null>(null)

  const statusDe = new Map<number, StatusDisponibilidade>(
    (q.data ?? []).map((d) => [d.slot_id, d.status]),
  )
  const status = (slotId: number) => statusDe.get(slotId) ?? 'DISPONIVEL'

  const dias = [...new Set(slots.map((s) => s.dia_semana))].sort((a, b) => a - b)
  const ordens = [...new Set(slots.map((s) => s.ordem))].sort((a, b) => a - b)
  const slotDe = (dia: number, ordem: number) =>
    slots.find((s) => s.dia_semana === dia && s.ordem === ordem)

  const marcarDia = (dia: number, novoStatus: StatusDisponibilidade) => {
    const ids = slots.filter((s) => s.dia_semana === dia).map((s) => s.id)
    lote.mutate({ slot_ids: ids, status: novoStatus })
    setUltimoDia(dia)
  }

  const copiarDia = (destino: number) => {
    if (ultimoDia === null || ultimoDia === destino) return
    const origem = slots.filter((s) => s.dia_semana === ultimoDia)
    for (const estado of ESTADOS) {
      const ordensDoEstado = origem
        .filter((s) => status(s.id) === estado.valor)
        .map((s) => s.ordem)
      const ids = slots
        .filter((s) => s.dia_semana === destino && ordensDoEstado.includes(s.ordem))
        .map((s) => s.id)
      if (ids.length) lote.mutate({ slot_ids: ids, status: estado.valor })
    }
  }

  return (
    <Cartao className="overflow-x-auto">
      <table className="w-full min-w-[40rem] border-collapse text-sm">
        <caption className="sr-only">
          Disponibilidade do professor por dia da semana e aula
        </caption>
        <thead>
          <tr>
            <th scope="col" className="w-28 p-3 text-start font-medium text-texto-suave">
              Aula
            </th>
            {dias.map((dia) => (
              <th key={dia} scope="col" className="p-3 text-center font-medium">
                <div className="flex flex-col items-center gap-1.5">
                  {DIAS_CURTOS[dia]}
                  <span className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => marcarDia(dia, 'DISPONIVEL')}
                      title={`Liberar ${DIAS_CURTOS[dia]} inteiro`}
                      className="rounded p-1 text-texto-suave hover:bg-superficie-2"
                    >
                      <Check className="size-3.5" aria-hidden />
                      <span className="sr-only">Liberar {DIAS_CURTOS[dia]} inteiro</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => marcarDia(dia, 'INDISPONIVEL')}
                      title={`Bloquear ${DIAS_CURTOS[dia]} inteiro`}
                      className="rounded p-1 text-texto-suave hover:bg-superficie-2"
                    >
                      <Moon className="size-3.5" aria-hidden />
                      <span className="sr-only">Bloquear {DIAS_CURTOS[dia]} inteiro</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => copiarDia(dia)}
                      disabled={ultimoDia === null || ultimoDia === dia}
                      title={
                        ultimoDia === null
                          ? 'Marque um dia primeiro para poder copiar'
                          : `Copiar ${DIAS_CURTOS[ultimoDia]} para ${DIAS_CURTOS[dia]}`
                      }
                      className="rounded p-1 text-texto-suave hover:bg-superficie-2 disabled:opacity-30"
                    >
                      <Copy className="size-3.5" aria-hidden />
                      <span className="sr-only">Copiar de outro dia</span>
                    </button>
                  </span>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* O horario fica em cada celula, nao no cabecalho da linha: dias
              diferentes podem ter horarios diferentes na mesma ordem (o sabado
              da Fatec comeca as 08:00, a noite comeca as 19:00). */}
          {ordens.map((ordem) => (
            <tr key={ordem} className="border-t border-borda">
              <th scope="row" className="p-3 text-start font-medium">
                {ordem}ª aula
              </th>
              {dias.map((dia) => {
                const slot = slotDe(dia, ordem)
                if (!slot) return <td key={dia} className="p-1.5" />
                const atual = status(slot.id)
                const estado = ESTADOS.find((e) => e.valor === atual)!
                const faixa = `${hhmm(slot.inicio)}–${hhmm(slot.fim)}`
                return (
                  <td key={dia} className="p-1.5">
                    <motion.button
                      type="button"
                      whileTap={{ scale: 0.95 }}
                      onClick={() => {
                        lote.mutate({ slot_ids: [slot.id], status: PROXIMO[atual] })
                        setUltimoDia(dia)
                      }}
                      aria-label={`${DIAS_CURTOS[dia]}, ${ordem}ª aula, ${faixa}: ${estado.rotulo}. Clique para marcar como ${ESTADOS.find((e) => e.valor === PROXIMO[atual])!.rotulo.toLowerCase()}`}
                      className={cn(
                        'flex h-11 w-full items-center justify-center gap-1.5 rounded-lg border text-xs font-medium tabular-nums transition-colors',
                        estado.classe,
                      )}
                    >
                      <estado.Icone className="size-3.5 shrink-0" aria-hidden />
                      {faixa}
                    </motion.button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-borda p-3 text-xs text-texto-suave">
        Horários preferenciais viram prioridade no objetivo do solver, ponderada pela pontuação
        do docente. Horários indisponíveis são restrição rígida.
      </p>
      <Botao
        tamanho="sm"
        variante="fantasma"
        className="m-3"
        onClick={() => lote.mutate({ slot_ids: slots.map((s) => s.id), status: 'DISPONIVEL' })}
      >
        Limpar todas as marcações
      </Botao>
    </Cartao>
  )
}
