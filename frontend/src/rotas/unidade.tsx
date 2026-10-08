import { motion } from 'motion/react'
import {
  Clock,
  DoorOpen,
  GraduationCap,
  type LucideIcon,
  SlidersHorizontal,
  Users,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { Pendencias } from '@/componentes/pendencias'
import { Cartao, Etiqueta } from '@/componentes/ui'
import {
  cursos,
  espacos,
  professores,
  turmas,
  unidades,
  useModelosTurno,
  usePreValidacao,
  vinculos,
} from '@/lib/dados'

function Numero({
  indice,
  para,
  titulo,
  valor,
  detalhe,
  Icone,
  carregando,
}: {
  indice: number
  para: string
  titulo: string
  valor: number
  detalhe: string
  Icone: LucideIcon
  carregando: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: indice * 0.05, duration: 0.24 }}
      whileHover={{ scale: 1.01 }}
    >
      <Link
        to={para}
        className="block rounded-grade border border-borda bg-superficie p-5 shadow-grade focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-texto-suave">{titulo}</h2>
          <Icone className="size-4.5 text-texto-suave" aria-hidden />
        </div>
        {carregando ? (
          <div className="esqueleto mt-2 h-8 w-12" />
        ) : (
          <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{valor}</p>
        )}
        <p className="mt-1 text-sm text-texto-suave">{detalhe}</p>
      </Link>
    </motion.div>
  )
}

export default function VisaoGeralUnidade() {
  const unidadeId = Number(useParams().unidadeId)

  const { data: listaUnidades } = unidades.useLista()
  const unidade = listaUnidades?.find((u) => u.id === unidadeId)

  const qCursos = cursos.useLista({ unidade_id: unidadeId })
  const qEspacos = espacos.useLista({ unidade_id: unidadeId })
  const qVinculos = vinculos.useLista({ unidade_id: unidadeId })
  const qTurnos = useModelosTurno(unidadeId)
  const qTurmas = turmas.useLista()
  const qProfessores = professores.useLista()
  const qPendencias = usePreValidacao(unidadeId)

  const idsCursos = new Set((qCursos.data ?? []).map((c) => c.id))
  const turmasDaUnidade = (qTurmas.data ?? []).filter((t) => idsCursos.has(t.curso_id))
  const nomePorProfessor = new Map((qProfessores.data ?? []).map((p) => [p.id, p.nome]))

  const regras = unidade?.config_regras

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {unidade?.nome ?? 'Unidade'}
        </h1>
        {unidade && (
          <Etiqueta tom={unidade.tipo === 'FATEC' ? 'fatec' : 'etec'}>{unidade.tipo}</Etiqueta>
        )}
        {unidade?.cidade && <span className="text-texto-suave">{unidade.cidade}</span>}
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Numero
          indice={0}
          para={`/unidades/${unidadeId}/cursos`}
          titulo="Cursos"
          valor={qCursos.data?.length ?? 0}
          detalhe={`${turmasDaUnidade.length} turmas`}
          Icone={GraduationCap}
          carregando={qCursos.isPending && !qCursos.data}
        />
        <Numero
          indice={1}
          para={`/unidades/${unidadeId}/professores`}
          titulo="Professores vinculados"
          valor={qVinculos.data?.length ?? 0}
          detalhe="Com vínculo nesta unidade"
          Icone={Users}
          carregando={qVinculos.isPending && !qVinculos.data}
        />
        <Numero
          indice={2}
          para={`/unidades/${unidadeId}/espacos`}
          titulo="Salas e laboratórios"
          valor={qEspacos.data?.length ?? 0}
          detalhe={`${(qEspacos.data ?? []).filter((e) => e.tipo === 'LABORATORIO').length} laboratórios`}
          Icone={DoorOpen}
          carregando={qEspacos.isPending && !qEspacos.data}
        />
        <Numero
          indice={3}
          para={`/unidades/${unidadeId}/turnos`}
          titulo="Modelos de turno"
          valor={qTurnos.data?.length ?? 0}
          detalhe={`${(qTurnos.data ?? []).reduce((t, mt) => t + mt.slots.length, 0)} horários`}
          Icone={Clock}
          carregando={qTurnos.isPending && !qTurnos.data}
        />
      </div>

      <Pendencias
        violacoes={qPendencias.data}
        carregando={qPendencias.isPending}
        titulo="Antes de gerar a grade"
        vazio="Nenhum impedimento: esta unidade está pronta para gerar a grade."
      />

      {regras && (
        <Cartao className="p-6">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="size-4.5 text-texto-suave" aria-hidden />
            <h2 className="font-medium">Regras em vigor</h2>
            <Link
              to={`/unidades/${unidadeId}/regras`}
              className="ms-auto text-sm text-primaria hover:underline"
            >
              Editar
            </Link>
          </div>
          <dl className="mt-4 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <Linha rotulo="Carga máxima semanal" valor={`${regras.carga_max_semanal} aulas`} />
            <Linha
              rotulo="Interjornada (CLT art. 66)"
              valor={
                regras.interjornada.modo === 'off'
                  ? 'Não verificada'
                  : `${regras.interjornada.horas} h — ${
                      regras.interjornada.modo === 'rigida' ? 'restrição rígida' : 'aviso'
                    }`
              }
            />
            <Linha
              rotulo="Limite diário (CLT art. 318 antigo)"
              valor={
                regras.limite_diario.ativo
                  ? `${regras.limite_diario.max_consecutivas} consecutivas / ${regras.limite_diario.max_intercaladas} intercaladas`
                  : 'Desligado'
              }
            />
            <Linha rotulo="Aula no sábado" valor={regras.usa_sabado ? 'Sim' : 'Não'} />
            <Linha rotulo="Regra de atribuição" valor={regras.atribuicao.regra} />
            <Linha
              rotulo="Objetivo do solver"
              valor={
                regras.modo_objetivo === 'lexicografico'
                  ? 'Lexicográfico'
                  : 'Soma ponderada'
              }
            />
          </dl>
        </Cartao>
      )}

      {turmasDaUnidade.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-medium">Turmas</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {turmasDaUnidade.map((turma, i) => {
              const curso = qCursos.data?.find((c) => c.id === turma.curso_id)
              return (
                <motion.div
                  key={turma.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i, 8) * 0.03, duration: 0.2 }}
                >
                  <Cartao className="p-4">
                    <p className="font-medium">
                      {curso?.sigla} · {turma.periodo}
                    </p>
                    <p className="mt-0.5 text-sm text-texto-suave">
                      {turma.turno} · {turma.qtd_alunos} alunos
                    </p>
                  </Cartao>
                </motion.div>
              )
            })}
          </div>
        </section>
      )}

      {nomePorProfessor.size === 0 && qProfessores.isFetched && (
        <p className="text-sm text-texto-suave">
          Nenhum professor cadastrado no escopo ainda.
        </p>
      )}
    </div>
  )
}

const Linha = ({ rotulo, valor }: { rotulo: string; valor: string }) => (
  <div>
    <dt className="text-texto-suave">{rotulo}</dt>
    <dd className="font-medium">{valor}</dd>
  </div>
)
