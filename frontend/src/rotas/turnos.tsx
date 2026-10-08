import { motion } from 'motion/react'
import { Clock, Coffee, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  Botao,
  Campo,
  Cartao,
  Dialogo,
  Entrada,
  EstadoVazio,
  Etiqueta,
  LinhasEsqueleto,
  Selecao,
} from '@/componentes/ui'
import { api, jsonBody } from '@/lib/api'
import {
  opcoesModelosTurno,
  unidades,
  useModelosTurno,
  usePresetsTurno,
  useSubstituirModeloTurno,
} from '@/lib/dados'
import { DIAS_CURTOS, hhmm, type ModeloTurno, type Slot } from '@/lib/tipos'
import { cn } from '@/lib/utils'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

/** Cores alternadas por bloco: o intervalo aparece como troca de cor. */
const CORES_BLOCO = [
  'bg-primaria-suave text-primaria border-primaria/25',
  'bg-superficie-2 text-texto border-borda',
]

export default function Turnos() {
  const unidadeId = Number(useParams().unidadeId)
  const cliente = useQueryClient()

  const { data: listaUnidades } = unidades.useLista()
  const unidade = listaUnidades?.find((u) => u.id === unidadeId)
  const { data: modelos, isPending } = useModelosTurno(unidadeId)
  const { data: presets = [] } = usePresetsTurno(unidade?.tipo)

  const [selecionado, setSelecionado] = useState<number | null>(null)
  const [dialogoNovo, setDialogoNovo] = useState(false)

  useEffect(() => {
    if (selecionado === null && modelos?.length) setSelecionado(modelos[0].id)
  }, [modelos, selecionado])

  const modelo = modelos?.find((mt) => mt.id === selecionado) ?? null

  async function criarDoPreset(chave: string, nome: string) {
    setDialogoNovo(false)
    try {
      const criado = await api<ModeloTurno>('/modelos-turno', {
        method: 'POST',
        body: jsonBody({ unidade_id: unidadeId, nome, preset_origem: chave }),
      })
      cliente.setQueryData<ModeloTurno[]>(opcoesModelosTurno(unidadeId).queryKey, (l) => [
        ...(l ?? []),
        criado,
      ])
      setSelecionado(criado.id)
      toast.success('Modelo de turno criado')
    } catch (erro) {
      toast.error('Não foi possível criar o modelo', { description: (erro as Error).message })
    }
  }

  async function apagar(id: number) {
    const anterior = cliente.getQueryData<ModeloTurno[]>(opcoesModelosTurno(unidadeId).queryKey)
    cliente.setQueryData<ModeloTurno[]>(opcoesModelosTurno(unidadeId).queryKey, (l) =>
      (l ?? []).filter((mt) => mt.id !== id),
    )
    setSelecionado(null)
    try {
      await api<void>(`/modelos-turno/${id}`, { method: 'DELETE' })
      toast.success('Modelo de turno excluído')
    } catch (erro) {
      cliente.setQueryData(opcoesModelosTurno(unidadeId).queryKey, anterior)
      setSelecionado(id)
      toast.error('Não foi possível excluir', { description: (erro as Error).message })
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Modelos de turno</h1>
          <p className="text-texto-suave">
            A semana de aulas da unidade. Aulas do mesmo bloco são geminadas — um bloco nunca
            atravessa intervalo.
          </p>
        </div>
        <Botao variante="primario" onClick={() => setDialogoNovo(true)}>
          <Plus className="size-4" aria-hidden />
          Novo modelo
        </Botao>
      </header>

      {isPending && !modelos ? (
        <LinhasEsqueleto linhas={3} />
      ) : !modelos?.length ? (
        <EstadoVazio
          Icone={Clock}
          titulo="Nenhum modelo de turno"
          descricao="Comece a partir de um preset (Fatec noturno, Etec técnico, ETIM) e ajuste os horários."
          acao={
            <Botao variante="primario" onClick={() => setDialogoNovo(true)}>
              <Plus className="size-4" aria-hidden />
              Criar a partir de um preset
            </Botao>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {modelos.map((mt) => (
              <button
                key={mt.id}
                type="button"
                onClick={() => setSelecionado(mt.id)}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-sm transition-colors',
                  mt.id === selecionado
                    ? 'border-primaria bg-primaria-suave font-medium text-primaria'
                    : 'border-borda bg-superficie text-texto-suave hover:bg-superficie-2',
                )}
              >
                {mt.nome}
                <span className="ms-2 text-xs text-texto-suave">{mt.slots.length} aulas</span>
              </button>
            ))}
          </div>

          {modelo && (
            <EditorSemana
              key={modelo.id}
              modelo={modelo}
              unidadeId={unidadeId}
              aoApagar={() => apagar(modelo.id)}
            />
          )}
        </>
      )}

      <DialogoNovoModelo
        aberto={dialogoNovo}
        presets={presets}
        aoFechar={() => setDialogoNovo(false)}
        aoCriar={criarDoPreset}
      />
    </div>
  )
}

// ------------------------------------------------------------------- editor

function EditorSemana({
  modelo,
  unidadeId,
  aoApagar,
}: {
  modelo: ModeloTurno
  unidadeId: number
  aoApagar: () => void
}) {
  const [rascunho, setRascunho] = useState<ModeloTurno>(modelo)
  const salvar = useSubstituirModeloTurno(unidadeId)

  useEffect(() => setRascunho(modelo), [modelo])

  const alterado = useMemo(
    () => JSON.stringify(rascunho) !== JSON.stringify(modelo),
    [rascunho, modelo],
  )

  const dias = useMemo(
    () => [...new Set(rascunho.slots.map((s) => s.dia_semana))].sort((a, b) => a - b),
    [rascunho],
  )

  const mudarSlot = (id: number, campo: keyof Slot, valor: string | number) =>
    setRascunho((r) => ({
      ...r,
      slots: r.slots.map((s) => (s.id === id ? { ...s, [campo]: valor } : s)),
    }))

  const removerSlot = (id: number) =>
    setRascunho((r) => {
      const alvo = r.slots.find((s) => s.id === id)!
      const restantes = r.slots.filter((s) => s.id !== id)
      // renumera o dia para as ordens continuarem sem furo
      let ordem = 0
      return {
        ...r,
        slots: restantes.map((s) =>
          s.dia_semana === alvo.dia_semana ? { ...s, ordem: ++ordem } : s,
        ),
      }
    })

  const adicionarSlot = (dia: number) =>
    setRascunho((r) => {
      const doDia = r.slots.filter((s) => s.dia_semana === dia)
      const ultimo = doDia.at(-1)
      return {
        ...r,
        slots: [
          ...r.slots,
          {
            id: -Date.now(),
            modelo_turno_id: r.id,
            dia_semana: dia,
            ordem: doDia.length + 1,
            inicio: ultimo?.fim ?? '19:00:00',
            fim: ultimo ? somarMinutos(ultimo.fim, 50) : '19:50:00',
            bloco_id: ultimo?.bloco_id ?? 1,
          },
        ],
      }
    })

  return (
    <Cartao className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-borda p-4">
        <Entrada
          value={rascunho.nome}
          onChange={(e) => setRascunho((r) => ({ ...r, nome: e.target.value }))}
          aria-label="Nome do modelo"
          className="max-w-xs font-medium"
        />
        {rascunho.preset_origem && <Etiqueta>preset {rascunho.preset_origem}</Etiqueta>}
        <div className="ms-auto flex items-center gap-2">
          <Botao variante="perigo" tamanho="sm" onClick={aoApagar}>
            <Trash2 className="size-4" aria-hidden />
            Excluir
          </Botao>
          <Botao
            variante="primario"
            tamanho="sm"
            disabled={!alterado || salvar.isPending}
            onClick={() => salvar.mutate(rascunho)}
          >
            <Save className="size-4" aria-hidden />
            {alterado ? 'Salvar alterações' : 'Salvo'}
          </Botao>
        </div>
      </div>

      {/* Borda por celula em vez de `gap-px` com fundo: a sobra da ultima linha
          da grade nao vira um bloco colorido quando os dias nao preenchem tudo. */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3">
        {dias.map((dia) => {
          const doDia = rascunho.slots
            .filter((s) => s.dia_semana === dia)
            .sort((a, b) => a.ordem - b.ordem)
          return (
            <div key={dia} className="border-b border-e border-borda bg-superficie p-4">
              <h3 className="text-sm font-medium">{DIAS_CURTOS[dia]}</h3>
              <ul className="mt-3 space-y-1.5">
                {doDia.map((slot, i) => {
                  const anterior = doDia[i - 1]
                  const temIntervalo = anterior && anterior.fim !== slot.inicio
                  return (
                    <li key={slot.id}>
                      {temIntervalo && (
                        <div className="my-1.5 flex items-center gap-2 text-xs text-texto-suave">
                          <Coffee className="size-3" aria-hidden />
                          intervalo {hhmm(anterior.fim)}–{hhmm(slot.inicio)}
                          <span className="h-px flex-1 bg-borda" />
                        </div>
                      )}
                      <motion.div
                        layout
                        className={cn(
                          'flex items-center gap-1.5 rounded-lg border px-2 py-1.5 text-sm',
                          CORES_BLOCO[(slot.bloco_id - 1) % CORES_BLOCO.length],
                        )}
                      >
                        <span className="w-4 shrink-0 text-xs text-texto-suave tabular-nums">
                          {slot.ordem}
                        </span>
                        <input
                          type="time"
                          value={hhmm(slot.inicio)}
                          onChange={(e) => mudarSlot(slot.id, 'inicio', `${e.target.value}:00`)}
                          aria-label={`Início da ${slot.ordem}ª aula de ${DIAS_CURTOS[dia]}`}
                          className="bg-transparent tabular-nums outline-none"
                        />
                        <span aria-hidden>–</span>
                        <input
                          type="time"
                          value={hhmm(slot.fim)}
                          onChange={(e) => mudarSlot(slot.id, 'fim', `${e.target.value}:00`)}
                          aria-label={`Fim da ${slot.ordem}ª aula de ${DIAS_CURTOS[dia]}`}
                          className="bg-transparent tabular-nums outline-none"
                        />
                        <input
                          type="number"
                          min={1}
                          value={slot.bloco_id}
                          onChange={(e) =>
                            mudarSlot(slot.id, 'bloco_id', Math.max(1, Number(e.target.value)))
                          }
                          aria-label={`Bloco da ${slot.ordem}ª aula de ${DIAS_CURTOS[dia]}`}
                          title="Bloco: aulas com o mesmo número são geminadas"
                          className="ms-auto w-10 rounded border border-current/20 bg-transparent px-1 text-center text-xs tabular-nums outline-none"
                        />
                        <button
                          type="button"
                          onClick={() => removerSlot(slot.id)}
                          aria-label={`Remover ${slot.ordem}ª aula de ${DIAS_CURTOS[dia]}`}
                          className="rounded p-0.5 opacity-60 hover:opacity-100"
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </button>
                      </motion.div>
                    </li>
                  )
                })}
              </ul>
              <Botao
                tamanho="sm"
                variante="fantasma"
                className="mt-2 w-full justify-center"
                onClick={() => adicionarSlot(dia)}
              >
                <Plus className="size-3.5" aria-hidden />
                Aula
              </Botao>
            </div>
          )
        })}
      </div>
    </Cartao>
  )
}

function somarMinutos(hora: string, minutos: number): string {
  const [h, m] = hora.split(':').map(Number)
  const total = h * 60 + m + minutos
  const hh = String(Math.floor(total / 60) % 24).padStart(2, '0')
  const mm = String(total % 60).padStart(2, '0')
  return `${hh}:${mm}:00`
}

function DialogoNovoModelo({
  aberto,
  presets,
  aoFechar,
  aoCriar,
}: {
  aberto: boolean
  presets: { chave: string; nome: string }[]
  aoFechar: () => void
  aoCriar: (chave: string, nome: string) => void
}) {
  const [chave, setChave] = useState<string>()
  const [nome, setNome] = useState('')

  const presetEscolhido = presets.find((p) => p.chave === chave)

  return (
    <Dialogo
      aberto={aberto}
      aoFechar={aoFechar}
      titulo="Novo modelo de turno"
      descricao="Escolha um preset como ponto de partida; todos os horários continuam editáveis."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (chave) aoCriar(chave, nome.trim() || (presetEscolhido?.nome ?? 'Novo turno'))
        }}
        className="space-y-5"
      >
        <Campo rotulo="Preset">
          <Selecao
            valor={chave}
            aoMudar={setChave}
            aria-label="Preset de turno"
            opcoes={presets.map((p) => ({ valor: p.chave, rotulo: p.nome }))}
          />
        </Campo>
        <Campo rotulo="Nome" dica="Em branco usa o nome do preset.">
          <Entrada
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder={presetEscolhido?.nome}
          />
        </Campo>
        <div className="flex justify-end gap-2">
          <Botao type="button" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" variante="primario" disabled={!chave}>
            Criar
          </Botao>
        </div>
      </form>
    </Dialogo>
  )
}
