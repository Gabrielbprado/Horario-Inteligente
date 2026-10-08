/**
 * Comparação entre duas versões da grade.
 *
 * A pergunta que a tela responde é "o que mudou", então as diferenças vêm
 * primeiro e as aulas que ficaram no lugar aparecem só se pedidas.
 */
import { motion } from 'motion/react'
import {
  ArrowLeft,
  ArrowRight,
  CircleMinus,
  CirclePlus,
  Clock,
  DoorOpen,
  Equal,
  GitCompare,
  UserRound,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { Campo, Cartao, EstadoVazio, Etiqueta, LinhasEsqueleto, Selecao } from '@/componentes/ui'
import { useComparacao, useGrades } from '@/lib/dados'
import type { DiferencaGrade, TipoDiferenca } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const APARENCIA: Record<
  TipoDiferenca,
  { Icone: typeof Clock; tom: 'neutro' | 'alerta' | 'ok' | 'erro' }
> = {
  horario: { Icone: Clock, tom: 'alerta' },
  espaco: { Icone: DoorOpen, tom: 'neutro' },
  professor: { Icone: UserRound, tom: 'neutro' },
  adicionada: { Icone: CirclePlus, tom: 'ok' },
  removida: { Icone: CircleMinus, tom: 'erro' },
  igual: { Icone: Equal, tom: 'neutro' },
}

const ORDEM_RESUMO: TipoDiferenca[] = [
  'horario',
  'espaco',
  'professor',
  'adicionada',
  'removida',
  'igual',
]

export default function Comparar() {
  const unidadeId = Number(useParams().unidadeId)
  const [busca, setBusca] = useSearchParams()
  const qGrades = useGrades(unidadeId)

  const grades = qGrades.data ?? []
  const primeira = busca.get('primeira') ? Number(busca.get('primeira')) : (grades[0]?.id ?? null)
  const segunda = busca.get('segunda')
    ? Number(busca.get('segunda'))
    : (grades.find((g) => g.id !== primeira)?.id ?? null)

  const comparacao = useComparacao(primeira, segunda)
  const [mostrarIguais, setMostrarIguais] = useState(false)

  const escolher = (qual: 'primeira' | 'segunda') => (valor: string) => {
    const proximo = new URLSearchParams(busca)
    proximo.set('primeira', String(primeira))
    proximo.set('segunda', String(segunda))
    proximo.set(qual, valor)
    setBusca(proximo, { replace: true })
  }

  const opcoes = grades.map((g) => ({ valor: String(g.id), rotulo: g.nome }))
  const diferencas = (comparacao.data?.diferencas ?? []).filter(
    (d) => mostrarIguais || d.tipo !== 'igual',
  )
  const mudancas = comparacao.data
    ? Object.entries(comparacao.data.resumo)
        .filter(([tipo, n]) => tipo !== 'igual' && n > 0)
        .reduce((total, [, n]) => total + n, 0)
    : 0

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <Link
          to={`/unidades/${unidadeId}/grades`}
          className="inline-flex items-center gap-1.5 text-sm text-texto-suave hover:text-primaria"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Todas as grades
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">Comparar versões</h1>
        <p className="max-w-2xl text-texto-suave">
          A unidade de comparação é o bloco de aulas geminadas — mover um bloco de duas aulas
          conta como uma mudança, não duas.
        </p>
      </header>

      {grades.length < 2 ? (
        <EstadoVazio
          Icone={GitCompare}
          titulo="Só há uma versão"
          descricao="Duplique uma grade na lista para ter duas versões e poder compará-las."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-[1fr_auto_1fr] sm:items-end">
            <Campo rotulo="Primeira versão">
              <Selecao
                valor={String(primeira)}
                aoMudar={escolher('primeira')}
                opcoes={opcoes}
                aria-label="Primeira versão"
              />
            </Campo>
            <ArrowRight className="mx-auto mb-2.5 size-4 text-texto-suave" aria-hidden />
            <Campo rotulo="Segunda versão">
              <Selecao
                valor={String(segunda)}
                aoMudar={escolher('segunda')}
                opcoes={opcoes}
                aria-label="Segunda versão"
              />
            </Campo>
          </div>

          {comparacao.isPending && !comparacao.data ? (
            <LinhasEsqueleto linhas={5} />
          ) : comparacao.error ? (
            <Cartao className="p-5 text-sm text-erro">{comparacao.error.message}</Cartao>
          ) : comparacao.data ? (
            <>
              <Cartao className="p-5">
                <h2 className="font-medium">
                  {mudancas === 0
                    ? 'As duas versões colocam todas as aulas no mesmo lugar.'
                    : `${mudancas} mudança(s) entre as duas versões.`}
                </h2>
                <ul className="mt-3 flex flex-wrap gap-2">
                  {ORDEM_RESUMO.filter((tipo) => comparacao.data.resumo[tipo] > 0).map((tipo) => (
                    <li key={tipo}>
                      <Etiqueta tom={APARENCIA[tipo].tom} Icone={APARENCIA[tipo].Icone}>
                        {comparacao.data.resumo[tipo]} {rotuloResumo(tipo)}
                      </Etiqueta>
                    </li>
                  ))}
                </ul>
              </Cartao>

              <Cartao className="overflow-hidden">
                <table className="w-full text-sm">
                  <caption className="sr-only">Métricas das duas versões</caption>
                  <thead>
                    <tr className="border-b border-borda text-start text-xs text-texto-suave">
                      <th scope="col" className="p-3 text-start font-medium">
                        Métrica
                      </th>
                      <th scope="col" className="p-3 text-end font-medium">
                        {comparacao.data.primeira.nome}
                      </th>
                      <th scope="col" className="p-3 text-end font-medium">
                        {comparacao.data.segunda.nome}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparacao.data.metricas.map((metrica) => {
                      const delta =
                        metrica.primeira !== null && metrica.segunda !== null
                          ? metrica.segunda - metrica.primeira
                          : null
                      return (
                        <tr key={metrica.nome} className="border-b border-borda last:border-0">
                          <th scope="row" className="p-3 text-start font-normal">
                            {metrica.nome}
                          </th>
                          <td className="p-3 text-end tabular-nums">{numero(metrica.primeira)}</td>
                          <td className="p-3 text-end tabular-nums">
                            {numero(metrica.segunda)}
                            {delta !== null && delta !== 0 && (
                              <span
                                className={cn(
                                  'ms-1.5 text-xs',
                                  delta < 0 ? 'text-ok' : 'text-alerta',
                                )}
                              >
                                {delta > 0 ? '+' : ''}
                                {numero(delta)}
                              </span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </Cartao>

              <section className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="font-medium">Aula por aula</h2>
                  <label className="flex items-center gap-2 text-sm text-texto-suave">
                    <input
                      type="checkbox"
                      checked={mostrarIguais}
                      onChange={(e) => setMostrarIguais(e.target.checked)}
                      className="size-4 accent-[var(--color-primaria)]"
                    />
                    Mostrar também as que não mudaram
                  </label>
                </div>

                {diferencas.length === 0 ? (
                  <Cartao className="p-5 text-sm text-texto-suave">
                    Nenhuma diferença. Marque a caixa acima para ver as aulas que ficaram no
                    lugar.
                  </Cartao>
                ) : (
                  <ul className="space-y-2">
                    {diferencas.map((diferenca, i) => (
                      <motion.li
                        key={`${diferenca.oferta_id}-${diferenca.bloco_idx}`}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{
                          opacity: 1,
                          y: 0,
                          transition: { delay: Math.min(i, 10) * 0.02 },
                        }}
                      >
                        <LinhaDiferenca diferenca={diferenca} />
                      </motion.li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

function LinhaDiferenca({ diferenca }: { diferenca: DiferencaGrade }) {
  const { Icone, tom } = APARENCIA[diferenca.tipo]
  return (
    <Cartao className={cn('p-3', diferenca.tipo === 'igual' && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-2">
        <Etiqueta tom={tom} Icone={Icone}>
          {diferenca.rotulo_tipo}
        </Etiqueta>
        <p className="font-medium">{diferenca.rotulo}</p>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-texto-suave">
        <span className={cn(diferenca.tipo !== 'igual' && 'line-through')}>
          {diferenca.antes ?? 'não existia'}
        </span>
        <ArrowRight className="size-3.5 shrink-0" aria-hidden />
        <span className={cn(diferenca.tipo !== 'igual' && 'font-medium text-texto')}>
          {diferenca.depois ?? 'deixou de existir'}
        </span>
      </div>
    </Cartao>
  )
}

function rotuloResumo(tipo: TipoDiferenca): string {
  return {
    horario: 'de horário',
    espaco: 'de sala',
    professor: 'de professor',
    adicionada: 'só na segunda',
    removida: 'só na primeira',
    igual: 'sem mudança',
  }[tipo]
}

const numero = (valor: number | null) =>
  valor === null ? '—' : valor.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
