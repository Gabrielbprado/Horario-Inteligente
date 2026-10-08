import { Command } from 'cmdk'
import { AnimatePresence, motion } from 'motion/react'
import { BookOpen, Building2, DoorOpen, GraduationCap, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cursos, disciplinas, espacos, professores, turmas, unidades } from '@/lib/dados'

/**
 * Paleta de comandos (Ctrl+K): encontra qualquer professor, turma, disciplina,
 * curso, sala ou unidade. Os dados já estão no cache do TanStack Query, então a
 * busca é local.
 *
 * A filtragem é nossa, não do cmdk (`shouldFilter={false}`). A primeira versão
 * entregava **todos** os registros ao cmdk e deixava ele filtrar: com o banco
 * de exemplo eram 60 itens e funcionava; com uma região inteira são mais de
 * 1500, e o cmdk pontua todos a cada tecla — a aba congelava por dezenas de
 * segundos. Aqui o DOM nunca passa de `POR_GRUPO` itens por grupo, não importa
 * o tamanho do banco.
 */

/** Quantos itens de cada tipo aparecem. Mais que isto vira rolagem, não ajuda. */
const POR_GRUPO = 6

type Entrada = {
  chave: string
  grupo: string
  Icone: typeof Users
  texto: string
  detalhe?: string
  destino: string
}

/** Sem acento e sem caixa: quem digita "iara" acha "Iara", "saude" acha "Saúde". */
const normalizar = (texto: string) =>
  texto
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()

export function PaletaComandos({ aberta, aoFechar }: { aberta: boolean; aoFechar: () => void }) {
  const navegar = useNavigate()
  const [busca, setBusca] = useState('')

  const { data: listaUnidades = [] } = unidades.useLista()
  const { data: listaCursos = [] } = cursos.useLista()
  const { data: listaTurmas = [] } = turmas.useLista()
  const { data: listaDisciplinas = [] } = disciplinas.useLista()
  const { data: listaProfessores = [] } = professores.useLista()
  const { data: listaEspacos = [] } = espacos.useLista()

  const entradas = useMemo<Entrada[]>(() => {
    const unidadeDoCurso = new Map(listaCursos.map((c) => [c.id, c.unidade_id]))
    const cursoPorId = new Map(listaCursos.map((c) => [c.id, c]))
    const primeiraUnidade = listaUnidades[0]?.id

    return [
      ...listaUnidades.map((u) => ({
        chave: `u${u.id}`,
        grupo: 'Unidades',
        Icone: Building2,
        texto: u.nome,
        detalhe: u.tipo,
        destino: `/unidades/${u.id}`,
      })),
      ...listaCursos.map((c) => ({
        chave: `c${c.id}`,
        grupo: 'Cursos',
        Icone: GraduationCap,
        texto: `${c.sigla} — ${c.nome}`,
        destino: `/unidades/${c.unidade_id}/cursos?curso=${c.id}`,
      })),
      ...listaTurmas.map((t) => {
        const curso = cursoPorId.get(t.curso_id)
        return {
          chave: `t${t.id}`,
          grupo: 'Turmas',
          Icone: GraduationCap,
          texto: `${curso?.sigla ?? '?'} · ${t.periodo}`,
          detalhe: t.turno,
          destino: `/unidades/${curso?.unidade_id}/cursos?curso=${t.curso_id}`,
        }
      }),
      ...listaDisciplinas.map((d) => ({
        chave: `d${d.id}`,
        grupo: 'Disciplinas',
        Icone: BookOpen,
        texto: `${d.sigla} — ${d.nome}`,
        detalhe: d.periodo,
        destino: `/unidades/${unidadeDoCurso.get(d.curso_id)}/cursos?curso=${d.curso_id}`,
      })),
      ...listaProfessores.map((p) => ({
        chave: `p${p.id}`,
        grupo: 'Professores',
        Icone: Users,
        texto: p.nome,
        detalhe: p.email ?? undefined,
        destino: `/unidades/${primeiraUnidade}/professores?professor=${p.id}`,
      })),
      ...listaEspacos.map((e) => ({
        chave: `e${e.id}`,
        grupo: 'Salas e laboratórios',
        Icone: DoorOpen,
        texto: e.nome,
        detalhe: e.tipo_laboratorio ?? e.tipo,
        destino: `/unidades/${e.unidade_id}/espacos`,
      })),
    ]
  }, [listaUnidades, listaCursos, listaTurmas, listaDisciplinas, listaProfessores, listaEspacos])

  const visiveis = useMemo(() => filtrar(entradas, busca), [entradas, busca])

  const ir = (destino: string) => {
    aoFechar()
    setBusca('')
    navegar(destino)
  }

  return (
    <AnimatePresence>
      {aberta && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={aoFechar}
            className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 420, damping: 32 }}
            className="fixed start-1/2 top-[12vh] z-50 w-[min(38rem,calc(100vw-2rem))] -translate-x-1/2"
          >
            <Command
              label="Buscar no sistema"
              shouldFilter={false}
              className="overflow-hidden rounded-grade border border-borda bg-superficie shadow-grade"
            >
              <Command.Input
                autoFocus
                value={busca}
                onValueChange={setBusca}
                placeholder="Buscar unidade, curso, turma, disciplina, professor ou sala…"
                className="w-full border-b border-borda bg-transparent px-4 py-3.5 text-sm outline-none placeholder:text-texto-suave/70"
              />
              <Command.List className="max-h-[22rem] overflow-y-auto p-2">
                {visiveis.length === 0 && (
                  <Command.Empty className="px-3 py-8 text-center text-sm text-texto-suave">
                    Nada encontrado.
                  </Command.Empty>
                )}

                {visiveis.map(([grupo, itens, total]) => (
                  <Command.Group
                    key={grupo}
                    heading={total > itens.length ? `${grupo} (${itens.length} de ${total})` : grupo}
                    className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-texto-suave"
                  >
                    {itens.map((entrada) => (
                      <Command.Item
                        key={entrada.chave}
                        value={entrada.chave}
                        onSelect={() => ir(entrada.destino)}
                        className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-superficie-2"
                      >
                        <entrada.Icone
                          className="size-4 shrink-0 text-texto-suave"
                          aria-hidden
                        />
                        <span className="truncate">{entrada.texto}</span>
                        {entrada.detalhe && (
                          <span className="ms-auto shrink-0 truncate text-xs text-texto-suave">
                            {entrada.detalhe}
                          </span>
                        )}
                      </Command.Item>
                    ))}
                  </Command.Group>
                ))}
              </Command.List>
            </Command>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

/**
 * Agrupa e corta. Devolve `[grupo, itens mostrados, total encontrado]` — o
 * total vai no cabeçalho para o usuário saber que refinar a busca adianta.
 */
export function filtrar(
  entradas: Entrada[],
  busca: string,
): [string, Entrada[], number][] {
  // Cada palavra procurada por conta própria: "lab inform" acha
  // "Lab. Informatica 1", que um casamento de trecho contíguo perderia por
  // causa do ponto.
  const termos = normalizar(busca).split(/\s+/).filter(Boolean)
  const grupos = new Map<string, { itens: Entrada[]; total: number }>()

  for (const entrada of entradas) {
    const alvo = normalizar(`${entrada.texto} ${entrada.detalhe ?? ''}`)
    if (!termos.every((termo) => alvo.includes(termo))) continue
    const atual = grupos.get(entrada.grupo) ?? { itens: [], total: 0 }
    atual.total += 1
    if (atual.itens.length < POR_GRUPO) atual.itens.push(entrada)
    grupos.set(entrada.grupo, atual)
  }

  return [...grupos].map(([grupo, { itens, total }]) => [grupo, itens, total])
}
