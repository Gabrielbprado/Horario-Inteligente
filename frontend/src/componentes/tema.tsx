import { AnimatePresence, motion } from 'motion/react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react'

import { cn } from '@/lib/utils'

export type Tema = 'claro' | 'escuro' | 'sistema'

const CHAVE = 'horario-tema'
/** A mesma chave e' lida por um script em `index.html`, que aplica o tema antes
 *  da primeira pintura. Mudar aqui exige mudar la'. */
const ATRIBUTO: Record<Tema, string | null> = { claro: 'light', escuro: 'dark', sistema: null }

function aplicar(tema: Tema) {
  const valor = ATRIBUTO[tema]
  if (valor) document.documentElement.setAttribute('data-theme', valor)
  else document.documentElement.removeAttribute('data-theme')
}

function lerTemaSalvo(): Tema {
  try {
    const salvo = localStorage.getItem(CHAVE)
    if (salvo === 'claro' || salvo === 'escuro' || salvo === 'sistema') return salvo
  } catch {
    /* localStorage bloqueado: cai no padrao */
  }
  return 'sistema'
}

const ContextoTema = createContext<{ tema: Tema; definir: (t: Tema) => void }>({
  tema: 'sistema',
  definir: () => {},
})

export function ProvedorTema({ children }: { children: React.ReactNode }) {
  const [tema, setTema] = useState<Tema>(lerTemaSalvo)

  useEffect(() => {
    aplicar(tema)
  }, [tema])

  const definir = useCallback((novo: Tema) => {
    setTema(novo)
    try {
      localStorage.setItem(CHAVE, novo)
    } catch {
      /* preferencia nao persiste, mas a sessao funciona */
    }
  }, [])

  const valor = useMemo(() => ({ tema, definir }), [tema, definir])
  return <ContextoTema value={valor}>{children}</ContextoTema>
}

export const useTema = () => use(ContextoTema)

const ICONES: Record<Tema, typeof Sun> = { claro: Sun, escuro: Moon, sistema: Monitor }
const PROXIMO: Record<Tema, Tema> = { claro: 'escuro', escuro: 'sistema', sistema: 'claro' }
const ROTULO: Record<Tema, string> = {
  claro: 'Tema claro',
  escuro: 'Tema escuro',
  sistema: 'Tema do sistema',
}

export function BotaoTema({ className }: { className?: string }) {
  const { tema, definir } = useTema()
  const Icone = ICONES[tema]

  return (
    <button
      type="button"
      onClick={() => definir(PROXIMO[tema])}
      title={ROTULO[tema]}
      aria-label={`${ROTULO[tema]}. Alternar para ${ROTULO[PROXIMO[tema]].toLowerCase()}`}
      className={cn(
        'grid size-9 place-items-center rounded-lg border border-borda bg-superficie',
        'text-texto-suave transition-colors hover:text-texto hover:bg-superficie-2',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria',
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={tema}
          initial={{ opacity: 0, rotate: -90, scale: 0.6 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 90, scale: 0.6 }}
          transition={{ duration: 0.18 }}
          className="grid place-items-center"
        >
          <Icone className="size-4.5" aria-hidden />
        </motion.span>
      </AnimatePresence>
    </button>
  )
}
