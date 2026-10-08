import { AnimatePresence, motion } from 'motion/react'
import {
  BookOpen,
  FlaskConical,
  GraduationCap,
  Layers,
  LayoutGrid,
  Plus,
  Split,
  Trash2,
  Users,
  Wifi,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useParams } from 'react-router-dom'

import {
  Botao,
  Campo,
  Cartao,
  Dialogo,
  Entrada,
  EstadoVazio,
  Etiqueta,
  Interruptor,
  LinhasEsqueleto,
  Selecao,
} from '@/componentes/ui'
import { estiloDisciplina } from '@/lib/cores'
import { cursos, disciplinas, turmas, useAplicarBlocosDoCurso, useModelosTurno } from '@/lib/dados'
import { ehProvisorio } from '@/lib/recursos'
import type { Disciplina, ModalidadeCurso, ModoDivisao } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const MODALIDADES: { valor: ModalidadeCurso; rotulo: string }[] = [
  { valor: 'CST', rotulo: 'Superior tecnológico (Fatec)' },
  { valor: 'TECNICO_MODULAR', rotulo: 'Técnico modular (Etec)' },
  { valor: 'ETIM', rotulo: 'ETIM (médio integrado)' },
  { valor: 'MTEC', rotulo: 'M-Tec' },
]

export default function Cursos() {
  const unidadeId = Number(useParams().unidadeId)
  const [busca, setBusca] = useSearchParams()

  const qCursos = cursos.useLista({ unidade_id: unidadeId })
  const criarCurso = cursos.useCriar({ unidade_id: unidadeId }, 'curso')
  const apagarCurso = cursos.useApagar({ unidade_id: unidadeId }, 'curso')

  const selecionado = busca.get('curso') ? Number(busca.get('curso')) : null
  const escolher = (id: number | null) =>
    setBusca(id === null ? {} : { curso: String(id) }, { replace: true })

  const [dialogo, setDialogo] = useState(false)

  useEffect(() => {
    if (selecionado === null && qCursos.data?.length) escolher(qCursos.data[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qCursos.data])

  const curso = qCursos.data?.find((c) => c.id === selecionado)

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Cursos e turmas</h1>
          <p className="text-texto-suave">
            A matriz curricular de cada período vira automaticamente as ofertas das turmas.
          </p>
        </div>
        <Botao variante="primario" onClick={() => setDialogo(true)}>
          <Plus className="size-4" aria-hidden />
          Novo curso
        </Botao>
      </header>

      {qCursos.isPending && !qCursos.data ? (
        <LinhasEsqueleto linhas={3} />
      ) : !qCursos.data?.length ? (
        <EstadoVazio
          Icone={GraduationCap}
          titulo="Nenhum curso nesta unidade"
          descricao="Cadastre o curso, depois as disciplinas de cada período e as turmas."
          acao={
            <Botao variante="primario" onClick={() => setDialogo(true)}>
              <Plus className="size-4" aria-hidden />
              Criar curso
            </Botao>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
          <nav className="space-y-1.5">
            {qCursos.data.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => escolher(c.id)}
                className={cn(
                  'w-full rounded-lg border px-3 py-2.5 text-start text-sm transition-colors',
                  c.id === selecionado
                    ? 'border-primaria bg-primaria-suave text-primaria'
                    : 'border-borda bg-superficie hover:bg-superficie-2',
                  ehProvisorio(c.id) && 'opacity-60',
                )}
              >
                <span className="font-medium">{c.sigla}</span>
                <span className="mt-0.5 block truncate text-xs text-texto-suave">{c.nome}</span>
              </button>
            ))}
          </nav>

          <AnimatePresence mode="wait">
            {curso && (
              <motion.div
                key={curso.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="space-y-6"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-lg font-semibold tracking-tight">{curso.nome}</h2>
                  <Etiqueta>
                    {MODALIDADES.find((mo) => mo.valor === curso.modalidade)?.rotulo}
                  </Etiqueta>
                  <Botao
                    tamanho="sm"
                    variante="perigo"
                    className="ms-auto"
                    onClick={() => {
                      apagarCurso.mutate(curso.id)
                      escolher(null)
                    }}
                  >
                    <Trash2 className="size-4" aria-hidden />
                    Excluir curso
                  </Botao>
                </div>

                <PainelDisciplinas cursoId={curso.id} />
                <PainelTurmas cursoId={curso.id} unidadeId={unidadeId} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      <DialogoCurso
        aberto={dialogo}
        aoFechar={() => setDialogo(false)}
        aoSalvar={(dados) => {
          criarCurso.mutate({ unidade_id: unidadeId, ...dados })
          setDialogo(false)
        }}
      />
    </div>
  )
}

// -------------------------------------------------------------- disciplinas

function PainelDisciplinas({ cursoId }: { cursoId: number }) {
  const filtro = { curso_id: cursoId }
  const q = disciplinas.useLista(filtro)
  const criar = disciplinas.useCriar(filtro, 'disciplina')
  const atualizar = disciplinas.useAtualizar(filtro, 'disciplina')
  const apagar = disciplinas.useApagar(filtro, 'disciplina')
  const [dialogo, setDialogo] = useState<Disciplina | 'nova' | null>(null)

  const porPeriodo = new Map<string, Disciplina[]>()
  for (const d of q.data ?? []) {
    porPeriodo.set(d.periodo, [...(porPeriodo.get(d.periodo) ?? []), d])
  }
  const padrao = valorComum(q.data ?? [])

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-3">
        <BookOpen className="size-4.5 text-texto-suave" aria-hidden />
        <h3 className="font-medium">Matriz curricular</h3>
        <Botao
          tamanho="sm"
          variante="fantasma"
          className="ms-auto"
          onClick={() => setDialogo('nova')}
        >
          <Plus className="size-4" aria-hidden />
          Disciplina
        </Botao>
      </div>

      {(q.data?.length ?? 0) > 0 && (
        // A `key` reinicia os campos quando o valor em vigor muda (outro curso,
        // ou depois de aplicar), sem um effect para sincronizar estado.
        <BlocosDoCurso
          key={`${cursoId}:${padrao.tamanho_bloco}:${padrao.max_blocos_por_dia}:${padrao.concentrar_no_dia}`}
          cursoId={cursoId}
          atual={padrao}
        />
      )}

      {q.isPending && !q.data ? (
        <LinhasEsqueleto linhas={2} />
      ) : !q.data?.length ? (
        <Cartao className="p-6 text-sm text-texto-suave">
          Nenhuma disciplina. Cadastre a matriz para o sistema gerar as ofertas das turmas.
        </Cartao>
      ) : (
        [...porPeriodo.entries()]
          .sort(([a], [b]) => a.localeCompare(b, 'pt-BR'))
          .map(([periodo, lista]) => (
            <div key={periodo} className="space-y-2">
              <div className="flex items-baseline gap-2">
                <h4 className="text-sm font-medium text-texto-suave">{periodo}</h4>
                <span className="text-xs text-texto-suave">
                  {lista.reduce((t, d) => t + d.aulas_semanais, 0)} aulas/semana
                </span>
              </div>
              <ul className="grid gap-2 sm:grid-cols-2">
                {lista.map((d) => (
                  <motion.li key={d.id} layout>
                    <button
                      type="button"
                      onClick={() => setDialogo(d)}
                      style={estiloDisciplina(d.sigla)}
                      className={cn(
                        'disciplina flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-start text-sm',
                        ehProvisorio(d.id) && 'opacity-60',
                      )}
                    >
                      <span className="font-semibold">{d.sigla}</span>
                      <span className="truncate opacity-90">{d.nome}</span>
                      <span className="ms-auto flex shrink-0 items-center gap-1.5">
                        {d.modalidade === 'REMOTA' && (
                          <Wifi className="size-3.5" aria-label="Aula remota" />
                        )}
                        {d.precisa_laboratorio && (
                          <FlaskConical
                            className="size-3.5"
                            aria-label={`Laboratório de ${d.tipo_laboratorio}`}
                          />
                        )}
                        {d.divisao_turma && (
                          <Split
                            className="size-3.5"
                            aria-label={`Divisão de turma ${d.modo_divisao}`}
                          />
                        )}
                        {d.concentrar_no_dia && (
                          <Layers
                            className="size-3.5"
                            aria-label="Aulas concentradas no mesmo dia"
                          />
                        )}
                        <span className="text-xs tabular-nums opacity-80">
                          {d.aulas_semanais}a
                        </span>
                      </span>
                    </button>
                  </motion.li>
                ))}
              </ul>
            </div>
          ))
      )}

      <DialogoDisciplina
        alvo={dialogo}
        cursoId={cursoId}
        padrao={padrao}
        aoFechar={() => setDialogo(null)}
        aoSalvar={(dados) => {
          if (dialogo === 'nova') criar.mutate(dados)
          else if (dialogo) atualizar.mutate({ id: dialogo.id, ...dados })
          setDialogo(null)
        }}
        aoApagar={() => {
          if (dialogo && dialogo !== 'nova') apagar.mutate(dialogo.id)
          setDialogo(null)
        }}
      />
    </section>
  )
}

type ValorComum = {
  tamanho_bloco: number | null
  max_blocos_por_dia: number | null
  concentrar_no_dia: boolean | null
}

/** O valor que todas as disciplinas compartilham, ou null quando divergem. */
function valorComum(lista: Disciplina[]): ValorComum {
  const unico = <K extends keyof ValorComum>(chave: K): Disciplina[K] | null => {
    const valores = new Set(lista.map((d) => d[chave]))
    return valores.size === 1 ? [...valores][0] : null
  }
  return {
    tamanho_bloco: unico('tamanho_bloco'),
    max_blocos_por_dia: unico('max_blocos_por_dia'),
    concentrar_no_dia: unico('concentrar_no_dia'),
  }
}

/**
 * Blocos no nível do curso: a escola decide "aulas geminadas, até dois blocos
 * por dia" para o curso inteiro, e cada disciplina continua editável como
 * exceção. Grava em todas de uma vez.
 */
function BlocosDoCurso({ cursoId, atual }: { cursoId: number; atual: ValorComum }) {
  const aplicar = useAplicarBlocosDoCurso(cursoId)
  const [tamanho, setTamanho] = useState<string>(String(atual.tamanho_bloco ?? ''))
  const [porDia, setPorDia] = useState<string>(String(atual.max_blocos_por_dia ?? ''))
  // null = as disciplinas divergem e o usuário ainda não escolheu.
  const [concentrar, setConcentrar] = useState<boolean | null>(atual.concentrar_no_dia)

  const misto =
    atual.tamanho_bloco === null ||
    atual.max_blocos_por_dia === null ||
    atual.concentrar_no_dia === null
  const mudouConcentrar = concentrar !== null && concentrar !== atual.concentrar_no_dia
  const mudou =
    (tamanho !== '' && Number(tamanho) !== atual.tamanho_bloco) ||
    (porDia !== '' && Number(porDia) !== atual.max_blocos_por_dia) ||
    mudouConcentrar

  return (
    <Cartao className="flex flex-wrap items-start gap-4 p-4">
      <div className="flex min-w-56 flex-1 items-start gap-2 pt-1">
        <LayoutGrid className="mt-0.5 size-4 shrink-0 text-texto-suave" aria-hidden />
        <div>
          <p className="text-sm font-medium">Blocos do curso</p>
          <p className="text-xs text-texto-suave">
            Vale para todas as disciplinas.{' '}
            {misto ? 'Hoje as disciplinas divergem.' : 'Edite uma disciplina para abrir exceção.'}
          </p>
        </div>
      </div>
      <Campo rotulo="Tamanho do bloco" dica="Aulas seguidas, sem intervalo no meio" className="w-36">
        <Entrada
          type="number"
          min={1}
          max={8}
          value={tamanho}
          placeholder={atual.tamanho_bloco === null ? 'misto' : undefined}
          onChange={(e) => setTamanho(e.target.value)}
        />
      </Campo>
      <Campo rotulo="Blocos por dia" dica="2 = até 4 aulas no dia" className="w-36">
        <Entrada
          type="number"
          min={1}
          max={8}
          value={porDia}
          placeholder={atual.max_blocos_por_dia === null ? 'misto' : undefined}
          onChange={(e) => setPorDia(e.target.value)}
        />
      </Campo>
      <div className="w-56 space-y-1 pt-7">
        <Interruptor
          marcado={concentrar ?? false}
          aoMudar={setConcentrar}
          rotulo="Concentrar no mesmo dia"
        />
        <p className="text-xs text-texto-suave">
          {concentrar === null
            ? 'Misto: algumas disciplinas concentram, outras não.'
            : 'As aulas da semana no mesmo dia e seguidas. Se não couberem todas, o sistema concentra o máximo e espalha o resto.'}
        </p>
      </div>
      <Botao
        variante="primario"
        className="mt-7"
        disabled={!mudou || aplicar.isPending}
        onClick={() =>
          aplicar.mutate({
            ...(tamanho !== '' ? { tamanho_bloco: Number(tamanho) } : {}),
            ...(porDia !== '' ? { max_blocos_por_dia: Number(porDia) } : {}),
            ...(mudouConcentrar ? { concentrar_no_dia: concentrar } : {}),
          })
        }
      >
        Aplicar a todas as disciplinas
      </Botao>
    </Cartao>
  )
}

// -------------------------------------------------------------------- turmas

function PainelTurmas({ cursoId, unidadeId }: { cursoId: number; unidadeId: number }) {
  const filtro = { curso_id: cursoId }
  const q = turmas.useLista(filtro)
  const criar = turmas.useCriar(filtro, 'turma')
  const apagar = turmas.useApagar(filtro, 'turma')
  const { data: modelos = [] } = useModelosTurno(unidadeId)
  const qDisciplinas = disciplinas.useLista({ curso_id: cursoId })
  const [dialogo, setDialogo] = useState(false)

  const aulasDoPeriodo = (periodo: string) =>
    (qDisciplinas.data ?? [])
      .filter((d) => d.periodo === periodo)
      .reduce((t, d) => t + d.aulas_semanais, 0)

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-3">
        <Users className="size-4.5 text-texto-suave" aria-hidden />
        <h3 className="font-medium">Turmas</h3>
        <Botao
          tamanho="sm"
          variante="fantasma"
          className="ms-auto"
          onClick={() => setDialogo(true)}
        >
          <Plus className="size-4" aria-hidden />
          Turma
        </Botao>
      </div>

      {!q.data?.length ? (
        <Cartao className="p-6 text-sm text-texto-suave">Nenhuma turma neste curso.</Cartao>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((t) => {
            const modelo = modelos.find((mt) => mt.id === t.modelo_turno_id)
            const aulas = aulasDoPeriodo(t.periodo)
            const cabe = !modelo || aulas <= modelo.slots.length
            return (
              <motion.li key={t.id} layout>
                <Cartao className={cn('p-4', ehProvisorio(t.id) && 'opacity-60')}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-medium">{t.periodo}</p>
                    <button
                      type="button"
                      onClick={() => apagar.mutate(t.id)}
                      aria-label={`Excluir turma ${t.periodo}`}
                      className="rounded p-0.5 text-texto-suave hover:text-erro"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </button>
                  </div>
                  <p className="mt-0.5 text-sm text-texto-suave">
                    {t.turno} · {t.qtd_alunos} alunos
                  </p>
                  <p className="mt-2 text-xs text-texto-suave">
                    {modelo?.nome ?? 'Sem modelo de turno'}
                  </p>
                  <p className="mt-1 text-xs">
                    {cabe ? (
                      <span className="text-texto-suave tabular-nums">
                        {aulas} de {modelo?.slots.length ?? '?'} horários ocupados
                      </span>
                    ) : (
                      <span className="text-erro tabular-nums">
                        {aulas} aulas não cabem em {modelo!.slots.length} horários
                      </span>
                    )}
                  </p>
                </Cartao>
              </motion.li>
            )
          })}
        </ul>
      )}

      <DialogoTurma
        aberto={dialogo}
        modelos={modelos}
        periodosConhecidos={[...new Set((qDisciplinas.data ?? []).map((d) => d.periodo))]}
        aoFechar={() => setDialogo(false)}
        aoSalvar={(dados) => {
          criar.mutate({ curso_id: cursoId, ...dados })
          setDialogo(false)
        }}
      />
    </section>
  )
}

// ------------------------------------------------------------------ dialogos

function DialogoCurso({
  aberto,
  aoFechar,
  aoSalvar,
}: {
  aberto: boolean
  aoFechar: () => void
  aoSalvar: (d: { nome: string; sigla: string; modalidade: ModalidadeCurso }) => void
}) {
  const [nome, setNome] = useState('')
  const [sigla, setSigla] = useState('')
  const [modalidade, setModalidade] = useState<ModalidadeCurso>('CST')

  return (
    <Dialogo aberto={aberto} aoFechar={aoFechar} titulo="Novo curso">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!nome.trim() || !sigla.trim()) return
          aoSalvar({ nome: nome.trim(), sigla: sigla.trim().toUpperCase(), modalidade })
          setNome('')
          setSigla('')
        }}
        className="space-y-5"
      >
        <Campo rotulo="Nome" dica="Ex.: Desenvolvimento de Software Multiplataforma">
          <Entrada value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />
        </Campo>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Sigla">
            <Entrada
              value={sigla}
              onChange={(e) => setSigla(e.target.value)}
              placeholder="DSM"
              required
            />
          </Campo>
          <Campo rotulo="Modalidade">
            <Selecao
              valor={modalidade}
              aoMudar={setModalidade}
              aria-label="Modalidade"
              opcoes={MODALIDADES}
            />
          </Campo>
        </div>
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

type DadosDisciplina = Omit<Disciplina, 'id' | 'curso_id'> & { curso_id: number }

function DialogoDisciplina({
  alvo,
  cursoId,
  padrao,
  aoFechar,
  aoSalvar,
  aoApagar,
}: {
  alvo: Disciplina | 'nova' | null
  cursoId: number
  /** Blocos do curso: disciplina nova nasce com eles. */
  padrao?: ValorComum
  aoFechar: () => void
  aoSalvar: (d: DadosDisciplina) => void
  aoApagar: () => void
}) {
  const vazia: DadosDisciplina = {
    curso_id: cursoId,
    periodo: '',
    nome: '',
    sigla: '',
    aulas_semanais: 4,
    tamanho_bloco: padrao?.tamanho_bloco ?? 2,
    modalidade: 'PRESENCIAL',
    precisa_laboratorio: false,
    tipo_laboratorio: null,
    divisao_turma: false,
    modo_divisao: 'INDIFERENTE',
    max_blocos_por_dia: padrao?.max_blocos_por_dia ?? 1,
    concentrar_no_dia: padrao?.concentrar_no_dia ?? false,
  }
  const [dados, setDados] = useState<DadosDisciplina>(vazia)

  useEffect(() => {
    if (alvo === 'nova') setDados(vazia)
    else if (alvo) setDados({ ...alvo })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alvo])

  const mudar = <K extends keyof DadosDisciplina>(campo: K, valor: DadosDisciplina[K]) =>
    setDados((d) => ({ ...d, [campo]: valor }))

  const blocos = Math.ceil(dados.aulas_semanais / Math.max(1, dados.tamanho_bloco))

  return (
    <Dialogo
      aberto={alvo !== null}
      aoFechar={aoFechar}
      titulo={alvo === 'nova' ? 'Nova disciplina' : 'Editar disciplina'}
      descricao={`${dados.aulas_semanais} aulas por semana viram ${blocos} ${blocos === 1 ? 'bloco' : 'blocos'} na grade.`}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!dados.nome.trim() || !dados.sigla.trim() || !dados.periodo.trim()) return
          aoSalvar({
            ...dados,
            tipo_laboratorio: dados.precisa_laboratorio ? dados.tipo_laboratorio : null,
          })
        }}
        className="max-h-[70vh] space-y-5 overflow-y-auto pe-1"
      >
        <Campo rotulo="Nome">
          <Entrada
            value={dados.nome}
            onChange={(e) => mudar('nome', e.target.value)}
            autoFocus
            required
          />
        </Campo>
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Sigla">
            <Entrada
              value={dados.sigla}
              onChange={(e) => mudar('sigla', e.target.value.toUpperCase())}
              required
            />
          </Campo>
          <Campo rotulo="Período" dica="1o sem, Módulo I, 1a série…">
            <Entrada
              value={dados.periodo}
              onChange={(e) => mudar('periodo', e.target.value)}
              required
            />
          </Campo>
          <Campo rotulo="Aulas por semana">
            <Entrada
              type="number"
              min={1}
              max={40}
              value={dados.aulas_semanais}
              onChange={(e) => mudar('aulas_semanais', Number(e.target.value))}
            />
          </Campo>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Tamanho do bloco" dica="2 = aulas geminadas">
            <Entrada
              type="number"
              min={1}
              max={8}
              value={dados.tamanho_bloco}
              onChange={(e) => mudar('tamanho_bloco', Number(e.target.value))}
            />
          </Campo>
          <Campo rotulo="Blocos por dia" dica="1 espalha a disciplina pela semana">
            <Entrada
              type="number"
              min={1}
              max={8}
              value={dados.max_blocos_por_dia}
              onChange={(e) => mudar('max_blocos_por_dia', Number(e.target.value))}
            />
          </Campo>
          <Campo rotulo="Modalidade">
            <Selecao
              valor={dados.modalidade}
              aoMudar={(v) => mudar('modalidade', v)}
              aria-label="Modalidade da aula"
              opcoes={[
                { valor: 'PRESENCIAL', rotulo: 'Presencial' },
                { valor: 'REMOTA', rotulo: 'Remota (sem sala)' },
              ]}
            />
          </Campo>
        </div>

        <div className="space-y-1.5 rounded-lg border border-borda p-4">
          <Interruptor
            marcado={dados.concentrar_no_dia}
            aoMudar={(v) => mudar('concentrar_no_dia', v)}
            rotulo="Concentrar as aulas no mesmo dia"
          />
          <p className="text-xs text-texto-suave">
            Ligado: as {dados.aulas_semanais} aulas ficam seguidas num único dia sempre que
            couber. Se não couber, a disciplina se espalha seguindo “Blocos por dia”, e a grade
            avisa.
          </p>
        </div>

        <div className="space-y-3 rounded-lg border border-borda p-4">
          <Interruptor
            marcado={dados.precisa_laboratorio}
            aoMudar={(v) => mudar('precisa_laboratorio', v)}
            rotulo="Precisa de laboratório"
          />
          {dados.precisa_laboratorio && (
            <Campo rotulo="Tipo de laboratório" dica="Ex.: informática, redes, química">
              <Entrada
                value={dados.tipo_laboratorio ?? ''}
                onChange={(e) => mudar('tipo_laboratorio', e.target.value)}
              />
            </Campo>
          )}
        </div>

        <div className="space-y-3 rounded-lg border border-borda p-4">
          <Interruptor
            marcado={dados.divisao_turma}
            aoMudar={(v) => mudar('divisao_turma', v)}
            rotulo="Divide a turma em subturmas A e B"
          />
          {dados.divisao_turma && (
            <Campo rotulo="Modo da divisão">
              <Selecao
                valor={dados.modo_divisao}
                aoMudar={(v) => mudar('modo_divisao', v as ModoDivisao)}
                aria-label="Modo da divisão"
                opcoes={[
                  { valor: 'PARALELA', rotulo: 'Paralela — mesmo horário, 2 professores' },
                  { valor: 'SEQUENCIAL', rotulo: 'Sequencial — mesmo professor, horários diferentes' },
                  { valor: 'INDIFERENTE', rotulo: 'Indiferente — o solver escolhe' },
                ]}
              />
            </Campo>
          )}
        </div>

        <div className="flex justify-between gap-2">
          {alvo !== 'nova' ? (
            <Botao type="button" variante="perigo" onClick={aoApagar}>
              <Trash2 className="size-4" aria-hidden />
              Excluir
            </Botao>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Botao type="button" onClick={aoFechar}>
              Cancelar
            </Botao>
            <Botao type="submit" variante="primario">
              Salvar
            </Botao>
          </div>
        </div>
      </form>
    </Dialogo>
  )
}

function DialogoTurma({
  aberto,
  modelos,
  periodosConhecidos,
  aoFechar,
  aoSalvar,
}: {
  aberto: boolean
  modelos: { id: number; nome: string }[]
  periodosConhecidos: string[]
  aoFechar: () => void
  aoSalvar: (d: {
    periodo: string
    turno: string
    modelo_turno_id: number
    qtd_alunos: number
  }) => void
}) {
  const [periodo, setPeriodo] = useState('')
  const [turno, setTurno] = useState('Noturno')
  const [modeloId, setModeloId] = useState<string>()
  const [alunos, setAlunos] = useState(40)

  useEffect(() => {
    if (!modeloId && modelos.length) setModeloId(String(modelos[0].id))
  }, [modelos, modeloId])

  return (
    <Dialogo
      aberto={aberto}
      aoFechar={aoFechar}
      titulo="Nova turma"
      descricao="As ofertas das disciplinas do período são criadas junto."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!periodo.trim() || !modeloId) return
          aoSalvar({
            periodo: periodo.trim(),
            turno,
            modelo_turno_id: Number(modeloId),
            qtd_alunos: alunos,
          })
          setPeriodo('')
        }}
        className="space-y-5"
      >
        <Campo
          rotulo="Período"
          dica={
            periodosConhecidos.length
              ? `Períodos já na matriz: ${periodosConhecidos.join(', ')}`
              : 'Cadastre disciplinas antes para a turma já nascer com ofertas.'
          }
        >
          <Entrada
            value={periodo}
            onChange={(e) => setPeriodo(e.target.value)}
            list="periodos"
            autoFocus
            required
          />
          <datalist id="periodos">
            {periodosConhecidos.map((p) => (
              <option key={p} value={p} />
            ))}
          </datalist>
        </Campo>
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Turno">
            <Entrada value={turno} onChange={(e) => setTurno(e.target.value)} />
          </Campo>
          <Campo rotulo="Modelo de turno" className="sm:col-span-1">
            <Selecao
              valor={modeloId}
              aoMudar={setModeloId}
              aria-label="Modelo de turno"
              opcoes={modelos.map((mt) => ({ valor: String(mt.id), rotulo: mt.nome }))}
            />
          </Campo>
          <Campo rotulo="Alunos">
            <Entrada
              type="number"
              min={1}
              value={alunos}
              onChange={(e) => setAlunos(Number(e.target.value))}
            />
          </Campo>
        </div>
        <div className="flex justify-end gap-2">
          <Botao type="button" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" variante="primario" disabled={!modelos.length}>
            Criar turma
          </Botao>
        </div>
      </form>
    </Dialogo>
  )
}
