import { AnimatePresence, motion } from 'motion/react'
import { CircleCheck, Info, OctagonX, TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { Botao, Cartao } from '@/componentes/ui'
import type { Severidade, Violacao } from '@/lib/tipos'
import { cn } from '@/lib/utils'

/** Ícone além da cor: o aviso não pode depender só de cor (seção 11.3). */
const ESTILO: Record<
  Severidade,
  { Icone: typeof Info; classe: string; rotulo: string; plural: string }
> = {
  BLOQUEANTE: {
    Icone: OctagonX,
    classe: 'border-erro/35 bg-erro/5 text-erro',
    rotulo: 'impedimento',
    plural: 'impedimentos',
  },
  ALERTA: {
    Icone: TriangleAlert,
    classe: 'border-alerta/35 bg-alerta/5 text-alerta',
    rotulo: 'alerta',
    plural: 'alertas',
  },
  INFO: {
    Icone: Info,
    classe: 'border-borda bg-superficie-2 text-texto-suave',
    rotulo: 'observação',
    plural: 'observações',
  },
}

const ORDEM: Severidade[] = ['BLOQUEANTE', 'ALERTA', 'INFO']
const LIMITE_INICIAL = 5

export function Pendencias({
  violacoes,
  carregando,
  titulo = 'Pendências',
  vazio = 'Tudo pronto para gerar a grade.',
}: {
  violacoes: Violacao[] | undefined
  carregando: boolean
  titulo?: string
  vazio?: string
}) {
  const [tudo, setTudo] = useState(false)

  if (carregando && !violacoes) {
    return (
      <Cartao className="space-y-2 p-5">
        <div className="esqueleto h-5 w-32" />
        <div className="esqueleto h-10 w-full" />
        <div className="esqueleto h-10 w-full" />
      </Cartao>
    )
  }

  const lista = violacoes ?? []

  if (!lista.length) {
    return (
      <Cartao className="flex items-center gap-3 p-5">
        <CircleCheck className="size-5 shrink-0 text-ok" aria-hidden />
        <p className="text-sm">{vazio}</p>
      </Cartao>
    )
  }

  const contagem = ORDEM.map((sev) => ({
    sev,
    n: lista.filter((v) => v.severidade === sev).length,
  })).filter((c) => c.n > 0)

  const visiveis = tudo ? lista : lista.slice(0, LIMITE_INICIAL)

  return (
    <Cartao className="p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="font-medium">{titulo}</h2>
        {contagem.map(({ sev, n }) => {
          const { Icone, rotulo, plural } = ESTILO[sev]
          return (
            <span
              key={sev}
              className={cn(
                'inline-flex items-center gap-1 text-sm',
                sev === 'BLOQUEANTE' && 'text-erro',
                sev === 'ALERTA' && 'text-alerta',
                sev === 'INFO' && 'text-texto-suave',
              )}
            >
              <Icone className="size-3.5" aria-hidden />
              <motion.span
                key={n}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="tabular-nums"
              >
                {n}
              </motion.span>
              {n === 1 ? rotulo : plural}
            </span>
          )
        })}
      </div>

      <ul className="mt-4 space-y-2">
        <AnimatePresence initial={false}>
          {visiveis.map((v, i) => {
            const { Icone, classe } = ESTILO[v.severidade]
            return (
              <motion.li
                key={`${v.tipo}-${v.mensagem}`}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{
                  opacity: 1,
                  y: 0,
                  transition: { delay: Math.min(i, 6) * 0.03, duration: 0.2 },
                }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                className={cn('flex items-start gap-2.5 rounded-lg border p-3 text-sm', classe)}
              >
                <Icone className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span className="text-texto">{v.mensagem}</span>
              </motion.li>
            )
          })}
        </AnimatePresence>
      </ul>

      {lista.length > LIMITE_INICIAL && (
        <Botao
          variante="fantasma"
          tamanho="sm"
          className="mt-3"
          onClick={() => setTudo((t) => !t)}
        >
          {tudo ? 'Mostrar menos' : `Ver as outras ${lista.length - LIMITE_INICIAL}`}
        </Botao>
      )}
    </Cartao>
  )
}
