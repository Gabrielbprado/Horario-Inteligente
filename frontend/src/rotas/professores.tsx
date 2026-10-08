import { AnimatePresence, motion } from 'motion/react'
import { Award, BookOpen, Link2, Plus, Trash2, UserPlus, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

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
import { estiloDisciplina } from '@/lib/cores'
import {
  cursos,
  disciplinas,
  habilitacoes,
  professores,
  unidades,
  vinculos,
} from '@/lib/dados'
import { ehProvisorio } from '@/lib/recursos'
import type { OrigemHabilitacao, TipoContrato, Vinculo } from '@/lib/tipos'
import { cn } from '@/lib/utils'

/**
 * Classificacao docente da unidade: pontuacao e, em caso de empate, a ordem de
 * desempate da Portaria CETEC 1.263/2017 — assiduidade, titulacao, tempo de
 * exercicio e numero de filhos. Devolve < 0 quando `a` vem antes de `b`.
 */
export function compararClassificacao(a: Vinculo, b: Vinculo): number {
  return (
    b.pontuacao - a.pontuacao ||
    b.pont_assiduidade - a.pont_assiduidade ||
    b.pont_titulacao - a.pont_titulacao ||
    b.tempo_exercicio_meses - a.tempo_exercicio_meses ||
    b.num_filhos - a.num_filhos
  )
}

const ORIGENS: { valor: OrigemHabilitacao; rotulo: string }[] = [
  { valor: 'CONCURSO', rotulo: 'Componente do concurso' },
  { valor: 'ANTERIOR', rotulo: 'Lecionava no período anterior' },
  { valor: 'HABILITADO', rotulo: 'Habilitado' },
]

export default function Professores() {
  const unidadeId = Number(useParams().unidadeId)
  const [busca, setBusca] = useSearchParams()

  const { data: listaUnidades } = unidades.useLista()
  const unidade = listaUnidades?.find((u) => u.id === unidadeId)

  const qProfessores = professores.useLista(
    unidade ? { escopo_id: unidade.escopo_id } : undefined,
    Boolean(unidade),
  )
  const qVinculos = vinculos.useLista({ unidade_id: unidadeId })
  const criarProfessor = professores.useCriar(
    unidade ? { escopo_id: unidade.escopo_id } : undefined,
    'professor',
  )
  const criarVinculo = vinculos.useCriar({ unidade_id: unidadeId }, 'vínculo')

  const [dialogoNovo, setDialogoNovo] = useState(false)
  const [dialogoVinculo, setDialogoVinculo] = useState<number | null>(null)

  const selecionado = busca.get('professor') ? Number(busca.get('professor')) : null
  const escolher = (id: number | null) =>
    setBusca(id === null ? {} : { professor: String(id) }, { replace: true })

  const vinculoDe = new Map((qVinculos.data ?? []).map((v) => [v.professor_id, v]))
  const ordenados = [...(qProfessores.data ?? [])].sort((a, b) => {
    const va = vinculoDe.get(a.id)
    const vb = vinculoDe.get(b.id)
    if (va && !vb) return -1
    if (!va && vb) return 1
    if (!va || !vb) return a.nome.localeCompare(b.nome, 'pt-BR')
    return compararClassificacao(va, vb) || a.nome.localeCompare(b.nome, 'pt-BR')
  })

  useEffect(() => {
    if (selecionado === null && ordenados.length) escolher(ordenados[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qProfessores.data])

  const professor = ordenados.find((p) => p.id === selecionado)

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Professores</h1>
          <p className="text-texto-suave">
            O docente pertence ao escopo; a pontuação e a carga máxima são do vínculo com esta
            unidade. É a pontuação que decide a prioridade de horário.
          </p>
        </div>
        <Botao variante="primario" onClick={() => setDialogoNovo(true)}>
          <UserPlus className="size-4" aria-hidden />
          Novo professor
        </Botao>
      </header>

      {qProfessores.isPending && !qProfessores.data ? (
        <LinhasEsqueleto linhas={4} />
      ) : !ordenados.length ? (
        <EstadoVazio
          Icone={Users}
          titulo="Nenhum professor ainda"
          descricao="Cadastre os docentes do escopo e vincule cada um às unidades em que leciona."
          acao={
            <Botao variante="primario" onClick={() => setDialogoNovo(true)}>
              <UserPlus className="size-4" aria-hidden />
              Cadastrar professor
            </Botao>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
          <nav className="space-y-1.5">
            {ordenados.map((p, i) => {
              const v = vinculoDe.get(p.id)
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => escolher(p.id)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-lg border px-3 py-2.5 text-start text-sm',
                    p.id === selecionado
                      ? 'border-primaria bg-primaria-suave text-primaria'
                      : 'border-borda bg-superficie hover:bg-superficie-2',
                    ehProvisorio(p.id) && 'opacity-60',
                  )}
                >
                  <span className="w-5 shrink-0 text-xs text-texto-suave tabular-nums">
                    {v ? i + 1 : '–'}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-medium">{p.nome}</span>
                  {v ? (
                    <span className="shrink-0 text-xs tabular-nums">
                      {v.pontuacao.toLocaleString('pt-BR', { minimumFractionDigits: 1 })}
                    </span>
                  ) : (
                    <span className="shrink-0 text-xs text-texto-suave">sem vínculo</span>
                  )}
                </button>
              )
            })}
          </nav>

          <AnimatePresence mode="wait">
            {professor && (
              <motion.div
                key={professor.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="space-y-6"
              >
                <div>
                  <h2 className="text-lg font-semibold tracking-tight">{professor.nome}</h2>
                  <p className="text-sm text-texto-suave">
                    {professor.identificador}
                    {professor.email ? ` · ${professor.email}` : ''}
                  </p>
                </div>

                <PainelVinculo
                  unidadeId={unidadeId}
                  vinculo={vinculoDe.get(professor.id)}
                  cargaPadrao={unidade?.carga_max_semanal_padrao ?? 29}
                  aoCriarVinculo={() => setDialogoVinculo(professor.id)}
                />

                <PainelHabilitacoes professorId={professor.id} unidadeId={unidadeId} />

                <PainelOutrasUnidades professorId={professor.id} unidadeAtual={unidadeId} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      <DialogoProfessor
        aberto={dialogoNovo}
        aoFechar={() => setDialogoNovo(false)}
        aoSalvar={(dados) => {
          if (!unidade) return
          criarProfessor.mutate({ escopo_id: unidade.escopo_id, ...dados })
          setDialogoNovo(false)
        }}
      />

      <Dialogo
        aberto={dialogoVinculo !== null}
        aoFechar={() => setDialogoVinculo(null)}
        titulo="Vincular à unidade"
        descricao="O vínculo carrega a pontuação da classificação docente e a carga máxima."
      >
        <FormularioVinculo
          cargaPadrao={unidade?.carga_max_semanal_padrao ?? 29}
          aoCancelar={() => setDialogoVinculo(null)}
          aoSalvar={(dados) => {
            criarVinculo.mutate({
              professor_id: dialogoVinculo!,
              unidade_id: unidadeId,
              ...dados,
            })
            setDialogoVinculo(null)
          }}
        />
      </Dialogo>
    </div>
  )
}

// ------------------------------------------------------------------ vinculo

function PainelVinculo({
  unidadeId,
  vinculo,
  cargaPadrao,
  aoCriarVinculo,
}: {
  unidadeId: number
  vinculo: Vinculo | undefined
  cargaPadrao: number
  aoCriarVinculo: () => void
}) {
  const atualizar = vinculos.useAtualizar({ unidade_id: unidadeId }, 'vínculo')
  const apagar = vinculos.useApagar({ unidade_id: unidadeId }, 'vínculo')

  if (!vinculo) {
    return (
      <Cartao className="flex flex-wrap items-center gap-3 p-5">
        <Link2 className="size-4.5 text-texto-suave" aria-hidden />
        <p className="text-sm text-texto-suave">
          Este professor não tem vínculo com esta unidade.
        </p>
        <Botao tamanho="sm" variante="primario" className="ms-auto" onClick={aoCriarVinculo}>
          Criar vínculo
        </Botao>
      </Cartao>
    )
  }

  const campo = (
    rotulo: string,
    chave: keyof Vinculo,
    props: { step?: string; min?: number } = {},
  ) => (
    <Campo rotulo={rotulo}>
      <Entrada
        type="number"
        min={props.min ?? 0}
        step={props.step ?? '0.5'}
        value={String(vinculo[chave] ?? '')}
        onChange={(e) =>
          atualizar.mutate({ id: vinculo.id, [chave]: Number(e.target.value) } as never)
        }
      />
    </Campo>
  )

  return (
    <Cartao className="p-5">
      <div className="flex items-center gap-2">
        <Award className="size-4.5 text-texto-suave" aria-hidden />
        <h3 className="font-medium">Vínculo e classificação</h3>
        <Botao
          tamanho="sm"
          variante="perigo"
          className="ms-auto"
          onClick={() => apagar.mutate(vinculo.id)}
        >
          <Trash2 className="size-4" aria-hidden />
          Remover vínculo
        </Botao>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Campo rotulo="Tipo de contrato">
          <Selecao
            valor={vinculo.tipo_contrato}
            aoMudar={(v) =>
              atualizar.mutate({ id: vinculo.id, tipo_contrato: v as TipoContrato })
            }
            aria-label="Tipo de contrato"
            opcoes={[
              { valor: 'INDETERMINADO', rotulo: 'Prazo indeterminado' },
              { valor: 'DETERMINADO', rotulo: 'Prazo determinado' },
            ]}
          />
        </Campo>
        {campo('Pontuação', 'pontuacao')}
        <Campo rotulo="Carga máxima" dica={`Em branco herda ${cargaPadrao} da unidade.`}>
          <Entrada
            type="number"
            min={1}
            value={vinculo.carga_max_semanal ?? ''}
            placeholder={String(cargaPadrao)}
            onChange={(e) =>
              atualizar.mutate({
                id: vinculo.id,
                carga_max_semanal: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </Campo>
      </div>

      <p className="mt-5 text-xs font-medium text-texto-suave">
        Critérios de desempate (Portaria CETEC 1.263/2017)
      </p>
      <div className="mt-2 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {campo('1. Assiduidade', 'pont_assiduidade')}
        {campo('2. Titulação', 'pont_titulacao')}
        {campo('3. Exercício (meses)', 'tempo_exercicio_meses', { step: '1' })}
        {campo('4. Filhos', 'num_filhos', { step: '1' })}
      </div>
    </Cartao>
  )
}

// ------------------------------------------------------------- habilitacoes

function PainelHabilitacoes({
  professorId,
  unidadeId,
}: {
  professorId: number
  unidadeId: number
}) {
  const filtro = { professor_id: professorId }
  const q = habilitacoes.useLista(filtro)
  const criar = habilitacoes.useCriar(filtro, 'habilitação')
  const apagar = habilitacoes.useApagar(filtro, 'habilitação')

  const qCursos = cursos.useLista({ unidade_id: unidadeId })
  const qDisciplinas = disciplinas.useLista()
  const idsCursos = new Set((qCursos.data ?? []).map((c) => c.id))
  const daUnidade = (qDisciplinas.data ?? []).filter((d) => idsCursos.has(d.curso_id))
  const porId = new Map(daUnidade.map((d) => [d.id, d]))

  const [adicionando, setAdicionando] = useState(false)
  const [disciplinaId, setDisciplinaId] = useState<string>()
  const [origem, setOrigem] = useState<OrigemHabilitacao>('CONCURSO')

  const jaTem = new Set((q.data ?? []).map((h) => h.disciplina_id))
  const disponiveis = daUnidade.filter((d) => !jaTem.has(d.id))

  return (
    <Cartao className="p-5">
      <div className="flex items-center gap-2">
        <BookOpen className="size-4.5 text-texto-suave" aria-hidden />
        <h3 className="font-medium">Disciplinas que leciona</h3>
        <Botao
          tamanho="sm"
          variante="fantasma"
          className="ms-auto"
          disabled={!disponiveis.length}
          onClick={() => setAdicionando(true)}
        >
          <Plus className="size-4" aria-hidden />
          Adicionar
        </Botao>
      </div>

      {!(q.data ?? []).filter((h) => porId.has(h.disciplina_id)).length ? (
        <p className="mt-4 text-sm text-texto-suave">
          Nenhuma habilitação nesta unidade. Sem habilitação, a atribuição sugerida não oferece
          a disciplina a este docente.
        </p>
      ) : (
        <ul className="mt-4 flex flex-wrap gap-2">
          {(q.data ?? [])
            .filter((h) => porId.has(h.disciplina_id))
            .map((h) => {
              const d = porId.get(h.disciplina_id)!
              return (
                <motion.li key={h.id} layout>
                  <span
                    style={estiloDisciplina(d.sigla)}
                    className="disciplina inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm"
                  >
                    <span className="font-semibold">{d.sigla}</span>
                    {/* O periodo distingue duas disciplinas de mesma sigla em
                        semestres diferentes — sem ele a lista parece cheia de
                        etiquetas repetidas. */}
                    <span className="text-xs text-texto-suave">{d.periodo}</span>
                    <span className="text-xs text-texto-suave">
                      {ORIGENS.find((o) => o.valor === h.origem)?.rotulo}
                    </span>
                    <button
                      type="button"
                      onClick={() => apagar.mutate(h.id)}
                      aria-label={`Remover habilitação em ${d.sigla} (${d.periodo})`}
                      className="opacity-60 hover:opacity-100"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </button>
                  </span>
                </motion.li>
              )
            })}
        </ul>
      )}

      <Dialogo
        aberto={adicionando}
        aoFechar={() => setAdicionando(false)}
        titulo="Adicionar habilitação"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!disciplinaId) return
            criar.mutate({
              professor_id: professorId,
              disciplina_id: Number(disciplinaId),
              origem,
            })
            setDisciplinaId(undefined)
            setAdicionando(false)
          }}
          className="space-y-5"
        >
          <Campo rotulo="Disciplina">
            <Selecao
              valor={disciplinaId}
              aoMudar={setDisciplinaId}
              aria-label="Disciplina"
              opcoes={disponiveis.map((d) => ({
                valor: String(d.id),
                rotulo: `${d.sigla} — ${d.nome} (${d.periodo})`,
              }))}
            />
          </Campo>
          <Campo
            rotulo="Origem"
            dica="A prioridade na atribuição segue esta ordem: concurso, depois anterior, depois habilitado."
          >
            <Selecao
              valor={origem}
              aoMudar={setOrigem}
              aria-label="Origem da habilitação"
              opcoes={ORIGENS.map((o) => ({ valor: o.valor, rotulo: o.rotulo }))}
            />
          </Campo>
          <div className="flex justify-end gap-2">
            <Botao type="button" onClick={() => setAdicionando(false)}>
              Cancelar
            </Botao>
            <Botao type="submit" variante="primario" disabled={!disciplinaId}>
              Adicionar
            </Botao>
          </div>
        </form>
      </Dialogo>
    </Cartao>
  )
}

function PainelOutrasUnidades({
  professorId,
  unidadeAtual,
}: {
  professorId: number
  unidadeAtual: number
}) {
  const q = vinculos.useLista({ professor_id: professorId })
  const { data: listaUnidades } = unidades.useLista()
  const outras = (q.data ?? []).filter((v) => v.unidade_id !== unidadeAtual)

  if (!outras.length) return null

  return (
    <Cartao className="p-5">
      <h3 className="font-medium">Também leciona em</h3>
      <p className="mt-1 text-sm text-texto-suave">
        As aulas publicadas nestas unidades entram como ocupação fixa ao gerar a grade aqui.
      </p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {outras.map((v) => {
          const u = listaUnidades?.find((x) => x.id === v.unidade_id)
          return (
            <Etiqueta key={v.id} tom={u?.tipo === 'FATEC' ? 'fatec' : 'etec'}>
              {u?.nome ?? `Unidade ${v.unidade_id}`} · {v.pontuacao.toLocaleString('pt-BR')}
            </Etiqueta>
          )
        })}
      </ul>
    </Cartao>
  )
}

// ----------------------------------------------------------------- dialogos

function DialogoProfessor({
  aberto,
  aoFechar,
  aoSalvar,
}: {
  aberto: boolean
  aoFechar: () => void
  aoSalvar: (d: { nome: string; identificador: string; email: string | null }) => void
}) {
  const [nome, setNome] = useState('')
  const [identificador, setIdentificador] = useState('')
  const [email, setEmail] = useState('')

  return (
    <Dialogo
      aberto={aberto}
      aoFechar={aoFechar}
      titulo="Novo professor"
      descricao="O cadastro é do escopo inteiro — o mesmo docente pode lecionar na Fatec e na Etec."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!nome.trim()) return
          aoSalvar({
            nome: nome.trim(),
            identificador:
              identificador.trim() || nome.trim().toLowerCase().replace(/\s+/g, '.'),
            email: email.trim() || null,
          })
          setNome('')
          setIdentificador('')
          setEmail('')
        }}
        className="space-y-5"
      >
        <Campo rotulo="Nome">
          <Entrada value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />
        </Campo>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Identificador" dica="CPF ou matrícula. Em branco gera do nome.">
            <Entrada
              value={identificador}
              onChange={(e) => setIdentificador(e.target.value)}
            />
          </Campo>
          <Campo rotulo="E-mail">
            <Entrada type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
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

function FormularioVinculo({
  cargaPadrao,
  aoCancelar,
  aoSalvar,
}: {
  cargaPadrao: number
  aoCancelar: () => void
  aoSalvar: (d: {
    tipo_contrato: TipoContrato
    pontuacao: number
    pont_assiduidade: number
    pont_titulacao: number
    tempo_exercicio_meses: number
    num_filhos: number
  }) => void
}) {
  const [contrato, setContrato] = useState<TipoContrato>('INDETERMINADO')
  const [pontuacao, setPontuacao] = useState(0)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        aoSalvar({
          tipo_contrato: contrato,
          pontuacao,
          pont_assiduidade: 0,
          pont_titulacao: 0,
          tempo_exercicio_meses: 0,
          num_filhos: 0,
        })
      }}
      className="space-y-5"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo rotulo="Tipo de contrato">
          <Selecao
            valor={contrato}
            aoMudar={setContrato}
            aria-label="Tipo de contrato"
            opcoes={[
              { valor: 'INDETERMINADO', rotulo: 'Prazo indeterminado' },
              { valor: 'DETERMINADO', rotulo: 'Prazo determinado' },
            ]}
          />
        </Campo>
        <Campo rotulo="Pontuação" dica={`Carga máxima herdada: ${cargaPadrao} aulas.`}>
          <Entrada
            type="number"
            min={0}
            step="0.5"
            value={pontuacao}
            onChange={(e) => setPontuacao(Number(e.target.value))}
            autoFocus
          />
        </Campo>
      </div>
      <div className="flex justify-end gap-2">
        <Botao type="button" onClick={aoCancelar}>
          Cancelar
        </Botao>
        <Botao type="submit" variante="primario">
          Vincular
        </Botao>
      </div>
    </form>
  )
}
