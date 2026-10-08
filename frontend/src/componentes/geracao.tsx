/**
 * Geração da grade nunca é tela de espera (seção 11.2 da spec).
 *
 * `ProvedorGeracao` guarda qual grade está sendo gerada; a pílula no topo
 * acompanha o solver em qualquer tela, e o usuário continua navegando.
 */
import { useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { CircleCheck, Loader2, TriangleAlert, X } from 'lucide-react'
import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { useProgresso } from '@/lib/dados'
import type { Progresso } from '@/lib/tipos'
import { cn } from '@/lib/utils'

type EmAndamento = { gradeId: number; unidadeId: number } | null

const Contexto = createContext<{
  atual: EmAndamento
  acompanhar: (g: { gradeId: number; unidadeId: number }) => void
  encerrar: () => void
  progresso: Progresso | undefined
}>({ atual: null, acompanhar: () => {}, encerrar: () => {}, progresso: undefined })

export const useGeracao = () => use(Contexto)

export function ProvedorGeracao({ children }: { children: React.ReactNode }) {
  const [atual, setAtual] = useState<EmAndamento>(null)
  const { data: progresso } = useProgresso(atual?.gradeId)
  const cliente = useQueryClient()

  const acompanhar = useCallback((g: { gradeId: number; unidadeId: number }) => setAtual(g), [])
  const encerrar = useCallback(() => setAtual(null), [])

  // Terminou: avisa por toast e recarrega o que depende da grade.
  useEffect(() => {
    if (!progresso?.terminado || !atual) return
    cliente.invalidateQueries({ queryKey: ['grades', atual.unidadeId] })
    cliente.invalidateQueries({ queryKey: ['avisos', progresso.grade_id] })

    if (progresso.status === 'concluido') {
      const acao = {
        label: 'Ver grade',
        onClick: () => {
          window.location.href = `/unidades/${atual.unidadeId}/grades?grade=${progresso.grade_id}`
        },
      }
      if (progresso.mensagem) {
        // "Resolver avisos" fechou a grade, mas um aviso nao tinha jeito.
        toast.warning('Grade gerada; alguns avisos não têm como sair', {
          description: progresso.mensagem,
          duration: 15_000,
          action: acao,
        })
      } else {
        toast.success('Grade gerada', {
          description: `${progresso.metricas.janela_turma ?? 0} janela(s) de turma em ${progresso.tempo_s.toLocaleString('pt-BR')} s.`,
          action: acao,
        })
      }
    } else {
      toast.error('Não foi possível montar a grade', {
        description: progresso.mensagem ?? undefined,
        duration: 12_000,
      })
    }
  }, [progresso?.terminado, progresso?.status, atual, cliente, progresso])

  const valor = useMemo(
    () => ({ atual, acompanhar, encerrar, progresso }),
    [atual, acompanhar, encerrar, progresso],
  )
  return <Contexto value={valor}>{children}</Contexto>
}

/** Pílula discreta no cabeçalho, visível em qualquer tela. */
export function PilulaGeracao() {
  const { atual, encerrar, progresso } = useGeracao()
  if (!atual || !progresso) return null

  const rodando = !progresso.terminado
  const janelas = progresso.metricas?.janela_turma

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -6, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -6 }}
        className={cn(
          'flex h-9 items-center gap-2 rounded-full border px-3 text-sm',
          rodando && 'border-primaria/40 bg-primaria-suave text-primaria',
          !rodando && progresso.status === 'concluido' && 'border-ok/40 bg-ok/10 text-ok',
          !rodando && progresso.status !== 'concluido' && 'border-erro/40 bg-erro/10 text-erro',
        )}
      >
        {rodando ? (
          <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
        ) : progresso.status === 'concluido' ? (
          <CircleCheck className="size-3.5 shrink-0" aria-hidden />
        ) : (
          <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
        )}

        <span className="hidden whitespace-nowrap sm:inline">
          {rodando ? 'Gerando grade' : progresso.status === 'concluido' ? 'Grade pronta' : 'Sem solução'}
          {rodando && progresso.solucoes > 0 && janelas !== undefined && (
            <span className="ms-1.5 text-texto-suave tabular-nums">
              melhor: {janelas} janela{janelas === 1 ? '' : 's'}
            </span>
          )}
        </span>

        <Link
          to={`/unidades/${atual.unidadeId}/grades?grade=${atual.gradeId}`}
          className="underline-offset-2 hover:underline"
        >
          ver
        </Link>
        <button
          type="button"
          onClick={encerrar}
          aria-label="Dispensar aviso de geração"
          className="opacity-60 hover:opacity-100"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      </motion.div>
    </AnimatePresence>
  )
}
