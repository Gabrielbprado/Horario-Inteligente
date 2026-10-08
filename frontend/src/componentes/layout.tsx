import { useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  Building2,
  CalendarCheck,
  ClipboardList,
  Clock,
  DoorOpen,
  GraduationCap,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  SlidersHorizontal,
  Upload,
  UserCheck,
  Users,
} from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useParams } from 'react-router-dom'

import { Logo } from '@/componentes/logo'
import { PilulaGeracao } from '@/componentes/geracao'
import { BotaoTema } from '@/componentes/tema'
import {
  cursos,
  disciplinas,
  escopos,
  espacos,
  opcoesConfigRegras,
  opcoesGrades,
  opcoesModelosImportacao,
  opcoesModelosTurno,
  opcoesOfertas,
  professores,
  unidades,
} from '@/lib/dados'
import { cn } from '@/lib/utils'

// A paleta so' existe depois do Ctrl+K, e carrega o `cmdk` junto. Sair do
// pacote inicial tira ~40 kB de quem so' quer abrir a grade; o atalho tem tempo
// de sobra para buscar o pedaco enquanto o usuario ainda esta digitando.
const PaletaComandos = lazy(() =>
  import('@/componentes/paleta').then((m) => ({ default: m.PaletaComandos })),
)

const ITENS = [
  { para: '', rotulo: 'Visão geral', Icone: LayoutDashboard, fim: true },
  { para: 'turnos', rotulo: 'Modelos de turno', Icone: Clock },
  { para: 'cursos', rotulo: 'Cursos e turmas', Icone: GraduationCap },
  { para: 'espacos', rotulo: 'Salas e laboratórios', Icone: DoorOpen },
  { para: 'professores', rotulo: 'Professores', Icone: Users },
  { para: 'disponibilidade', rotulo: 'Disponibilidade', Icone: UserCheck },
  { para: 'atribuicao', rotulo: 'Atribuição de aulas', Icone: ClipboardList },
  { para: 'grades', rotulo: 'Grades de horário', Icone: CalendarCheck },
  { para: 'importar', rotulo: 'Importar cadastros', Icone: Upload },
  { para: 'regras', rotulo: 'Regras da unidade', Icone: SlidersHorizontal },
]

export function Trilha({ partes }: { partes: string[] }) {
  return (
    <nav aria-label="Trilha de navegação" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {partes.map((parte, i) => (
          <li key={`${parte}-${i}`} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && (
              <span aria-hidden className="text-texto-suave/70">
                ›
              </span>
            )}
            <span
              className={cn(
                'truncate',
                i === partes.length - 1 ? 'font-medium text-texto' : 'text-texto-suave',
              )}
            >
              {parte}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  )
}

function BarraLateral({
  unidadeId,
  recolhida,
  aoAlternar,
}: {
  unidadeId: number
  recolhida: boolean
  aoAlternar: () => void
}) {
  const cliente = useQueryClient()

  // Prefetch no hover: a tela seguinte ja chega com dados no cache.
  const prefetchDe = (destino: string) => () => {
    const filtro = { unidade_id: unidadeId }
    if (destino === 'cursos') cursos.prefetch(cliente, filtro)
    if (destino === 'espacos') espacos.prefetch(cliente, filtro)
    if (destino === 'professores') professores.prefetch(cliente)
    if (destino === 'disponibilidade') professores.prefetch(cliente)
    if (destino === 'atribuicao') cliente.prefetchQuery(opcoesOfertas(filtro))
    if (destino === 'grades') cliente.prefetchQuery(opcoesGrades(unidadeId))
    if (destino === 'turnos') cliente.prefetchQuery(opcoesModelosTurno(unidadeId))
    if (destino === 'importar') cliente.prefetchQuery(opcoesModelosImportacao())
    if (destino === 'regras') cliente.prefetchQuery(opcoesConfigRegras(unidadeId))
  }

  return (
    <aside
      className={cn(
        'nao-imprimir sticky top-14 hidden h-[calc(100dvh-3.5rem)] shrink-0 border-e border-borda',
        'transition-[width] duration-200 md:block',
        recolhida ? 'w-16' : 'w-60',
      )}
    >
      <nav className="flex h-full flex-col gap-1 p-3">
        {ITENS.map(({ para, rotulo, Icone, fim }) => (
          <NavLink
            key={para || 'inicio'}
            to={`/unidades/${unidadeId}/${para}`.replace(/\/$/, '')}
            end={fim}
            onMouseEnter={prefetchDe(para)}
            onFocus={prefetchDe(para)}
            title={recolhida ? rotulo : undefined}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria',
                isActive
                  ? 'bg-primaria-suave font-medium text-primaria'
                  : 'text-texto-suave hover:bg-superficie-2 hover:text-texto',
              )
            }
          >
            <Icone className="size-4.5 shrink-0" aria-hidden />
            {!recolhida && <span className="truncate">{rotulo}</span>}
          </NavLink>
        ))}

        <button
          type="button"
          onClick={aoAlternar}
          className="mt-auto flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-texto-suave hover:bg-superficie-2"
          aria-label={recolhida ? 'Expandir menu' : 'Recolher menu'}
        >
          {recolhida ? (
            <PanelLeftOpen className="size-4.5" aria-hidden />
          ) : (
            <>
              <PanelLeftClose className="size-4.5" aria-hidden />
              <span>Recolher</span>
            </>
          )}
        </button>
      </nav>
    </aside>
  )
}

export function Layout() {
  const local = useLocation()
  const params = useParams()
  const semAnimacao = useReducedMotion()
  const [recolhida, setRecolhida] = useState(false)
  const [paletaAberta, setPaletaAberta] = useState(false)
  // Depois do primeiro Ctrl+K a paleta fica montada: so' assim a animacao de
  // saida tem em que rodar. Antes disso ela nem e' baixada.
  const [paletaJaUsada, setPaletaJaUsada] = useState(false)
  const abrirPaleta = (aberta: boolean) => {
    if (aberta) setPaletaJaUsada(true)
    setPaletaAberta(aberta)
  }
  const cliente = useQueryClient()

  const unidadeId = params.unidadeId ? Number(params.unidadeId) : undefined
  const { data: listaUnidades } = unidades.useLista()
  const { data: listaEscopos } = escopos.useLista()
  const unidade = listaUnidades?.find((u) => u.id === unidadeId)
  const escopo = listaEscopos?.find((e) => e.id === unidade?.escopo_id)

  // Ctrl+K / Cmd+K abre a paleta de comandos.
  useEffect(() => {
    const aoTeclar = (evento: KeyboardEvent) => {
      if (evento.key === 'k' && (evento.metaKey || evento.ctrlKey)) {
        evento.preventDefault()
        // So' os setters, para o efeito nao depender de nada de fora.
        setPaletaJaUsada(true)
        setPaletaAberta((a) => !a)
      }
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [])

  // Carrega em segundo plano o que a proxima tela provavelmente vai pedir.
  useEffect(() => {
    if (unidadeId === undefined) return
    cursos.prefetch(cliente, { unidade_id: unidadeId })
    professores.prefetch(cliente)
    disciplinas.prefetch(cliente)
  }, [unidadeId, cliente])

  const trilha = ['Centro Paula Souza']
  if (escopo) trilha[0] = escopo.nome
  if (unidade) trilha.push(unidade.nome)

  return (
    <div className="flex min-h-full flex-col">
      <header className="nao-imprimir sticky top-0 z-30 border-b border-borda vidro">
        <div className="flex h-14 w-full items-center gap-3 px-4 sm:px-6">
          <NavLink to="/" aria-label="Horário Inteligente — início" className="shrink-0 rounded-lg">
            <Logo />
          </NavLink>
          <span aria-hidden className="h-5 w-px shrink-0 bg-borda" />
          <Trilha partes={trilha} />

          <div className="ms-auto flex items-center gap-2">
            <PilulaGeracao />
            <button
              type="button"
              onClick={() => abrirPaleta(true)}
              className="flex h-9 items-center gap-2 rounded-lg border border-borda bg-superficie px-2.5 text-sm text-texto-suave hover:bg-superficie-2"
            >
              <Search className="size-4" aria-hidden />
              <span className="hidden sm:inline">Buscar</span>
              <kbd className="hidden rounded border border-borda px-1 font-sans text-[0.65rem] sm:inline">
                Ctrl K
              </kbd>
            </button>
            <BotaoTema />
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        {unidadeId !== undefined && (
          <BarraLateral
            unidadeId={unidadeId}
            recolhida={recolhida}
            aoAlternar={() => setRecolhida((r) => !r)}
          />
        )}

        <main className="min-w-0 flex-1 px-4 py-8 sm:px-6">
          <div className="mx-auto w-full max-w-6xl">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={local.pathname}
                initial={semAnimacao ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={semAnimacao ? undefined : { opacity: 0, y: -4 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>

      <Suspense fallback={null}>
        {paletaJaUsada && (
          <PaletaComandos aberta={paletaAberta} aoFechar={() => abrirPaleta(false)} />
        )}
      </Suspense>
    </div>
  )
}

export const IconeUnidade = Building2
