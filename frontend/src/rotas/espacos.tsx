import { motion } from 'motion/react'
import { DoorOpen, FlaskConical, Plus, Trash2, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
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
import { cursos, disciplinas, espacos } from '@/lib/dados'
import { ehProvisorio } from '@/lib/recursos'
import type { TipoEspaco } from '@/lib/tipos'
import { cn } from '@/lib/utils'

export default function Espacos() {
  const unidadeId = Number(useParams().unidadeId)
  const filtro = { unidade_id: unidadeId }

  const q = espacos.useLista(filtro)
  const criar = espacos.useCriar(filtro, 'espaço')
  const apagar = espacos.useApagar(filtro, 'espaço')
  const [dialogo, setDialogo] = useState(false)

  // Quais tipos de laboratorio a matriz exige e a unidade nao tem?
  const qCursos = cursos.useLista(filtro)
  const qDisciplinas = disciplinas.useLista()
  const idsCursos = new Set((qCursos.data ?? []).map((c) => c.id))
  const exigidos = new Set(
    (qDisciplinas.data ?? [])
      .filter((d) => idsCursos.has(d.curso_id) && d.precisa_laboratorio)
      .map((d) => (d.tipo_laboratorio ?? '').toLowerCase())
      .filter(Boolean),
  )
  const existentes = new Set(
    (q.data ?? [])
      .filter((e) => e.tipo === 'LABORATORIO')
      .map((e) => (e.tipo_laboratorio ?? '').toLowerCase()),
  )
  const faltando = [...exigidos].filter((t) => !existentes.has(t))

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Salas e laboratórios</h1>
          <p className="text-texto-suave">
            Disciplinas remotas não consomem espaço; as demais precisam de um compatível e com
            capacidade suficiente.
          </p>
        </div>
        <Botao variante="primario" onClick={() => setDialogo(true)}>
          <Plus className="size-4" aria-hidden />
          Novo espaço
        </Botao>
      </header>

      {faltando.length > 0 && (
        <div className="flex items-start gap-3 rounded-grade border border-alerta/40 bg-alerta/5 p-4 text-sm">
          <TriangleAlert className="mt-0.5 size-4.5 shrink-0 text-alerta" aria-hidden />
          <p>
            A matriz exige laboratório de{' '}
            <strong>{faltando.join(', ')}</strong> e esta unidade não tem nenhum. O solver vai
            recusar a geração da grade até que exista pelo menos um.
          </p>
        </div>
      )}

      {q.isPending && !q.data ? (
        <LinhasEsqueleto linhas={3} />
      ) : !q.data?.length ? (
        <EstadoVazio
          Icone={DoorOpen}
          titulo="Nenhum espaço cadastrado"
          descricao="Cadastre as salas e os laboratórios que a unidade pode usar nas aulas presenciais."
          acao={
            <Botao variante="primario" onClick={() => setDialogo(true)}>
              <Plus className="size-4" aria-hidden />
              Cadastrar espaço
            </Botao>
          }
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((e, i) => (
            <motion.li
              key={e.id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i, 10) * 0.03, duration: 0.2 }}
            >
              <Cartao className={cn('p-4', ehProvisorio(e.id) && 'opacity-60')}>
                <div className="flex items-start justify-between gap-2">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-superficie-2 text-texto-suave">
                    {e.tipo === 'LABORATORIO' ? (
                      <FlaskConical className="size-4.5" aria-hidden />
                    ) : (
                      <DoorOpen className="size-4.5" aria-hidden />
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => apagar.mutate(e.id)}
                    aria-label={`Excluir ${e.nome}`}
                    className="rounded p-0.5 text-texto-suave hover:text-erro"
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                  </button>
                </div>
                <p className="mt-3 font-medium">{e.nome}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <Etiqueta>{e.tipo === 'LABORATORIO' ? 'Laboratório' : 'Sala'}</Etiqueta>
                  {e.tipo_laboratorio && <Etiqueta tom="ok">{e.tipo_laboratorio}</Etiqueta>}
                  <span className="text-xs text-texto-suave tabular-nums">
                    {e.capacidade} lugares
                  </span>
                </div>
              </Cartao>
            </motion.li>
          ))}
        </ul>
      )}

      <DialogoEspaco
        aberto={dialogo}
        tiposConhecidos={[...exigidos, ...existentes]}
        aoFechar={() => setDialogo(false)}
        aoSalvar={(dados) => {
          criar.mutate({ unidade_id: unidadeId, ...dados })
          setDialogo(false)
        }}
      />
    </div>
  )
}

function DialogoEspaco({
  aberto,
  tiposConhecidos,
  aoFechar,
  aoSalvar,
}: {
  aberto: boolean
  tiposConhecidos: string[]
  aoFechar: () => void
  aoSalvar: (d: {
    nome: string
    tipo: TipoEspaco
    tipo_laboratorio: string | null
    capacidade: number
  }) => void
}) {
  const [nome, setNome] = useState('')
  const [tipo, setTipo] = useState<TipoEspaco>('SALA')
  const [tipoLab, setTipoLab] = useState('')
  const [capacidade, setCapacidade] = useState(40)

  return (
    <Dialogo aberto={aberto} aoFechar={aoFechar} titulo="Novo espaço">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!nome.trim()) return
          aoSalvar({
            nome: nome.trim(),
            tipo,
            tipo_laboratorio: tipo === 'LABORATORIO' ? tipoLab.trim() || null : null,
            capacidade,
          })
          setNome('')
        }}
        className="space-y-5"
      >
        <Campo rotulo="Nome" dica="Ex.: Laboratório 2, Sala 14">
          <Entrada value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />
        </Campo>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Tipo">
            <Selecao
              valor={tipo}
              aoMudar={setTipo}
              aria-label="Tipo de espaço"
              opcoes={[
                { valor: 'SALA', rotulo: 'Sala de aula' },
                { valor: 'LABORATORIO', rotulo: 'Laboratório' },
              ]}
            />
          </Campo>
          <Campo rotulo="Capacidade">
            <Entrada
              type="number"
              min={1}
              value={capacidade}
              onChange={(e) => setCapacidade(Number(e.target.value))}
            />
          </Campo>
        </div>
        {tipo === 'LABORATORIO' && (
          <Campo
            rotulo="Tipo de laboratório"
            dica="Precisa bater com o que a disciplina exige."
          >
            <Entrada
              value={tipoLab}
              onChange={(e) => setTipoLab(e.target.value)}
              list="tipos-lab"
              placeholder="informática"
            />
            <datalist id="tipos-lab">
              {[...new Set(tiposConhecidos)].map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </Campo>
        )}
        <div className="flex justify-end gap-2">
          <Botao type="button" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" variante="primario">
            Criar
          </Botao>
        </div>
      </form>
    </Dialogo>
  )
}
