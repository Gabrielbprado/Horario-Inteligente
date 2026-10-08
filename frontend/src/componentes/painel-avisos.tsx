/**
 * Avisos da grade com registro de ciência.
 *
 * A grade só é publicada quando não há bloqueante e todos os alertas têm um
 * "Estou ciente" registrado, com quem e quando (seção 4.10 da spec).
 */
import { AnimatePresence, motion } from 'motion/react'
import { CircleCheck, Info, OctagonX, TriangleAlert, UserCheck, WandSparkles } from 'lucide-react'

import { Botao, Cartao, Etiqueta } from '@/componentes/ui'
import { useGeracao } from '@/componentes/geracao'
import { useAvisos, useDarCiencia, useGerarGrade } from '@/lib/dados'
import type { AvisoGrade, Severidade } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const ESTILO: Record<Severidade, { Icone: typeof Info; classe: string; nome: string }> = {
  BLOQUEANTE: { Icone: OctagonX, classe: 'border-erro/35 bg-erro/5', nome: 'Impedimento' },
  ALERTA: { Icone: TriangleAlert, classe: 'border-alerta/35 bg-alerta/5', nome: 'Alerta' },
  INFO: { Icone: Info, classe: 'border-borda bg-superficie-2', nome: 'Observação' },
}

const ORDEM: Severidade[] = ['BLOQUEANTE', 'ALERTA', 'INFO']

/** Avisos que o solver consegue transformar em regra rígida e regerar sem eles. */
const RESOLVIVEIS = new Set(['JANELA_TURMA', 'JANELA_PROFESSOR', 'INTERJORNADA'])

export function PainelAvisos({
  gradeId,
  unidadeId,
  jaResolvida = false,
}: {
  gradeId: number
  unidadeId: number
  /** Grade gerada por "Resolver avisos": o que sobrou já foi provado sem jeito. */
  jaResolvida?: boolean
}) {
  const { data: avisos, isPending } = useAvisos(gradeId)
  const ciencia = useDarCiencia(gradeId)
  const gerar = useGerarGrade(unidadeId)
  const { acompanhar, atual } = useGeracao()

  if (isPending && !avisos) {
    return (
      <Cartao className="space-y-2 p-5">
        <div className="esqueleto h-5 w-40" />
        <div className="esqueleto h-12 w-full" />
      </Cartao>
    )
  }

  const lista = avisos ?? []
  const bloqueantes = lista.filter((a) => a.severidade === 'BLOQUEANTE')
  const pendentes = lista.filter((a) => a.severidade === 'ALERTA' && !a.ciente)
  const resolviveis = jaResolvida ? [] : lista.filter((a) => RESOLVIVEIS.has(a.tipo))
  const gerando = gerar.isPending || atual?.gradeId !== undefined

  if (!lista.length) {
    return (
      <Cartao className="flex items-center gap-3 p-5">
        <CircleCheck className="size-5 shrink-0 text-ok" aria-hidden />
        <p className="text-sm">Nenhum aviso: a grade pode ser publicada.</p>
      </Cartao>
    )
  }

  const ordenados = [...lista].sort(
    (a, b) =>
      ORDEM.indexOf(a.severidade) - ORDEM.indexOf(b.severidade) ||
      Number(a.ciente) - Number(b.ciente),
  )

  return (
    <Cartao className="p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-medium">Avisos</h2>
        {bloqueantes.length > 0 && (
          <Etiqueta tom="erro" Icone={OctagonX}>
            {bloqueantes.length} impedimento{bloqueantes.length === 1 ? '' : 's'}
          </Etiqueta>
        )}
        <Etiqueta tom={pendentes.length ? 'alerta' : 'ok'}>
          <motion.span key={pendentes.length} initial={{ opacity: 0, y: -3 }} animate={{ opacity: 1, y: 0 }}>
            {pendentes.length}
          </motion.span>
          &nbsp;sem ciência
        </Etiqueta>
        <div className="ms-auto flex flex-wrap gap-2">
          {resolviveis.length > 0 && (
            <Botao
              tamanho="sm"
              variante="secundario"
              disabled={gerando}
              title="Regera a grade a partir desta, exigindo zero janela e interjornada de 11 h"
              onClick={() =>
                gerar.mutate(
                  { partir_de: gradeId, resolver_avisos: true },
                  { onSuccess: ({ grade_id }) => acompanhar({ gradeId: grade_id, unidadeId }) },
                )
              }
            >
              <WandSparkles className="size-4" aria-hidden />
              Resolver avisos
            </Botao>
          )}
          {pendentes.length > 0 && (
            <Botao tamanho="sm" variante="secundario" onClick={() => ciencia.todos.mutate()}>
              <UserCheck className="size-4" aria-hidden />
              Estou ciente de todos
            </Botao>
          )}
        </div>
      </div>

      {jaResolvida && lista.some((a) => RESOLVIVEIS.has(a.tipo)) && (
        <p className="mt-3 text-sm text-texto-suave">
          Esta grade já passou por “Resolver avisos”: os que ficaram não têm como sair com a
          disponibilidade e os blocos atuais.
        </p>
      )}

      <ul className="mt-4 space-y-2">
        <AnimatePresence initial={false}>
          {ordenados.map((aviso) => (
            <LinhaAviso
              key={aviso.id}
              aviso={aviso}
              aoDarCiencia={() => ciencia.um.mutate(aviso.id)}
            />
          ))}
        </AnimatePresence>
      </ul>
    </Cartao>
  )
}

function LinhaAviso({
  aviso,
  aoDarCiencia,
}: {
  aviso: AvisoGrade
  aoDarCiencia: () => void
}) {
  const { Icone, classe, nome } = ESTILO[aviso.severidade]
  const exigeCiencia = aviso.severidade === 'ALERTA'

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginTop: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'flex flex-wrap items-start gap-2.5 rounded-lg border p-3 text-sm',
        classe,
        aviso.ciente && 'opacity-60',
      )}
    >
      <Icone
        className={cn(
          'mt-0.5 size-4 shrink-0',
          aviso.severidade === 'BLOQUEANTE' && 'text-erro',
          aviso.severidade === 'ALERTA' && 'text-alerta',
          aviso.severidade === 'INFO' && 'text-texto-suave',
        )}
        aria-label={nome}
      />
      <div className="min-w-0 flex-1">
        <p>{aviso.mensagem}</p>
        {aviso.ciente && aviso.ciente_em && (
          <p className="mt-1 flex items-center gap-1 text-xs text-texto-suave">
            <CircleCheck className="size-3" aria-hidden />
            Ciente por {aviso.ciente_por} em{' '}
            {new Date(aviso.ciente_em).toLocaleString('pt-BR', {
              dateStyle: 'short',
              timeStyle: 'short',
            })}
          </p>
        )}
      </div>

      {exigeCiencia && !aviso.ciente && (
        <Botao tamanho="sm" onClick={aoDarCiencia} className="shrink-0">
          Estou ciente
        </Botao>
      )}
    </motion.li>
  )
}
