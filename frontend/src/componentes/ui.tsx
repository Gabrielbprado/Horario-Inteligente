/**
 * Primitivas de interface sobre Radix UI, no estilo shadcn/ui mas escritas
 * contra os tokens deste projeto (`--color-superficie`, `--color-primaria`, ...)
 * em vez dos tokens que o gerador do shadcn traz. Ver DECISOES.md D21.
 */
import * as DialogPrimitivo from '@radix-ui/react-dialog'
import * as LabelPrimitivo from '@radix-ui/react-label'
import * as SelectPrimitivo from '@radix-ui/react-select'
import * as SwitchPrimitivo from '@radix-ui/react-switch'
import { AnimatePresence, motion } from 'motion/react'
import { Check, ChevronDown, X } from 'lucide-react'
import { forwardRef, type ComponentProps, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

const FOCO =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria'

// ------------------------------------------------------------------- Botao

const VARIANTES = {
  primario: 'bg-primaria text-primaria-texto hover:brightness-110',
  secundario: 'border border-borda bg-superficie hover:bg-superficie-2',
  fantasma: 'hover:bg-superficie-2',
  perigo: 'border border-erro/40 text-erro hover:bg-erro/10',
} as const

const TAMANHOS = {
  sm: 'h-8 px-3 text-sm gap-1.5',
  md: 'h-9.5 px-4 text-sm gap-2',
  icone: 'size-9 justify-center',
} as const

export type BotaoProps = ComponentProps<'button'> & {
  variante?: keyof typeof VARIANTES
  tamanho?: keyof typeof TAMANHOS
}

/** As classes do botao, para dar a um `<a>` a mesma aparencia — um download
 *  precisa ser um link de verdade, nao um `onClick` que simula um. */
export const estiloBotao = (
  variante: keyof typeof VARIANTES = 'secundario',
  tamanho: keyof typeof TAMANHOS = 'md',
  className?: string,
) =>
  cn(
    'inline-flex items-center rounded-lg font-medium transition-[background,filter,transform]',
    'active:scale-[0.98] disabled:pointer-events-none',
    // Desabilitado troca de cor em vez de desbotar. Esmaecer o botao primario
    // punha texto branco sobre um indigo palido — 1,6:1, ilegivel — justamente
    // no botao cujo `title` explica **por que** a acao esta bloqueada. Cinza
    // sobre superficie-2 le-se bem e continua obviamente inativo.
    'disabled:border-borda disabled:bg-superficie-2 disabled:text-texto-suave',
    'disabled:shadow-none disabled:brightness-100',
    VARIANTES[variante],
    TAMANHOS[tamanho],
    FOCO,
    className,
  )

export const Botao = forwardRef<HTMLButtonElement, BotaoProps>(function Botao(
  { className, variante = 'secundario', tamanho = 'md', ...props },
  ref,
) {
  return <button ref={ref} className={estiloBotao(variante, tamanho, className)} {...props} />
})

// ------------------------------------------------------------ Campo / Input

export const Rotulo = ({ className, ...props }: ComponentProps<typeof LabelPrimitivo.Root>) => (
  <LabelPrimitivo.Root
    className={cn('text-sm font-medium text-texto-suave', className)}
    {...props}
  />
)

export const Entrada = forwardRef<HTMLInputElement, ComponentProps<'input'>>(function Entrada(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        'h-9.5 w-full rounded-lg border border-borda bg-superficie px-3 text-sm',
        'placeholder:text-texto-suave/60 disabled:opacity-50',
        FOCO,
        className,
      )}
      {...props}
    />
  )
})

export function Campo({
  rotulo,
  dica,
  children,
  className,
}: {
  rotulo: string
  dica?: string
  children: ReactNode
  className?: string
}) {
  return (
    <label className={cn('flex flex-col gap-1.5', className)}>
      <span className="text-sm font-medium text-texto-suave">{rotulo}</span>
      {children}
      {dica && <span className="text-xs text-texto-suave">{dica}</span>}
    </label>
  )
}

// ------------------------------------------------------------------ Select

export function Selecao<T extends string>({
  valor,
  aoMudar,
  opcoes,
  placeholder = 'Selecione…',
  className,
  'aria-label': ariaLabel,
}: {
  valor: T | undefined
  aoMudar: (v: T) => void
  opcoes: { valor: T; rotulo: string }[]
  placeholder?: string
  className?: string
  'aria-label'?: string
}) {
  // `valor ?? ''` mantem o Select sempre controlado. Com `undefined` o Radix
  // trata o componente como nao-controlado no primeiro render e depois reclama
  // da troca — e voltar para "sem selecao" deixaria de funcionar.
  return (
    <SelectPrimitivo.Root value={valor ?? ''} onValueChange={(v) => aoMudar(v as T)}>
      <SelectPrimitivo.Trigger
        aria-label={ariaLabel}
        className={cn(
          'flex h-9.5 w-full items-center justify-between gap-2 rounded-lg border border-borda',
          'bg-superficie px-3 text-start text-sm',
          FOCO,
          className,
        )}
      >
        <SelectPrimitivo.Value placeholder={placeholder} />
        <ChevronDown className="size-4 shrink-0 text-texto-suave" aria-hidden />
      </SelectPrimitivo.Trigger>
      <SelectPrimitivo.Portal>
        <SelectPrimitivo.Content
          position="popper"
          sideOffset={6}
          className="z-50 max-h-72 overflow-hidden rounded-lg border border-borda bg-superficie shadow-grade"
        >
          <SelectPrimitivo.Viewport className="p-1">
            {opcoes.map((o) => (
              <SelectPrimitivo.Item
                key={o.valor}
                value={o.valor}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-superficie-2"
              >
                <SelectPrimitivo.ItemIndicator>
                  <Check className="size-3.5 text-primaria" aria-hidden />
                </SelectPrimitivo.ItemIndicator>
                <SelectPrimitivo.ItemText>{o.rotulo}</SelectPrimitivo.ItemText>
              </SelectPrimitivo.Item>
            ))}
          </SelectPrimitivo.Viewport>
        </SelectPrimitivo.Content>
      </SelectPrimitivo.Portal>
    </SelectPrimitivo.Root>
  )
}

// ------------------------------------------------------------------ Switch

export function Interruptor({
  marcado,
  aoMudar,
  rotulo,
}: {
  marcado: boolean
  aoMudar: (v: boolean) => void
  rotulo: string
}) {
  return (
    <div className="flex items-center gap-2.5">
      <SwitchPrimitivo.Root
        checked={marcado}
        onCheckedChange={aoMudar}
        id={`sw-${rotulo}`}
        className={cn(
          'relative h-5.5 w-10 shrink-0 rounded-full border border-borda transition-colors',
          'data-[state=checked]:border-primaria data-[state=checked]:bg-primaria',
          'data-[state=unchecked]:bg-superficie-2',
          FOCO,
        )}
      >
        <SwitchPrimitivo.Thumb className="block size-4 translate-x-0.5 rounded-full bg-superficie shadow transition-transform data-[state=checked]:translate-x-5" />
      </SwitchPrimitivo.Root>
      <Rotulo htmlFor={`sw-${rotulo}`} className="cursor-pointer text-texto">
        {rotulo}
      </Rotulo>
    </div>
  )
}

// ------------------------------------------------------------------ Dialogo

export function Dialogo({
  aberto,
  aoFechar,
  titulo,
  descricao,
  children,
}: {
  aberto: boolean
  aoFechar: () => void
  titulo: string
  descricao?: string
  children: ReactNode
}) {
  return (
    <DialogPrimitivo.Root open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <AnimatePresence>
        {aberto && (
          <DialogPrimitivo.Portal forceMount>
            <DialogPrimitivo.Overlay asChild forceMount>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
              />
            </DialogPrimitivo.Overlay>
            <DialogPrimitivo.Content asChild forceMount>
              <motion.div
                initial={{ opacity: 0, scale: 0.97, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.98, y: 4 }}
                transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                className="fixed start-1/2 top-1/2 z-50 w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-grade border border-borda bg-superficie p-6 shadow-grade"
              >
                <DialogPrimitivo.Title className="text-lg font-semibold tracking-tight">
                  {titulo}
                </DialogPrimitivo.Title>
                {descricao ? (
                  <DialogPrimitivo.Description className="mt-1 text-sm text-texto-suave">
                    {descricao}
                  </DialogPrimitivo.Description>
                ) : (
                  <DialogPrimitivo.Description className="sr-only">
                    {titulo}
                  </DialogPrimitivo.Description>
                )}
                <div className="mt-5">{children}</div>
                <DialogPrimitivo.Close
                  aria-label="Fechar"
                  className={cn(
                    'absolute end-4 top-4 grid size-8 place-items-center rounded-lg text-texto-suave hover:bg-superficie-2',
                    FOCO,
                  )}
                >
                  <X className="size-4" aria-hidden />
                </DialogPrimitivo.Close>
              </motion.div>
            </DialogPrimitivo.Content>
          </DialogPrimitivo.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitivo.Root>
  )
}

// ------------------------------------------------------------ Cartao / Badge

export const Cartao = ({ className, ...props }: ComponentProps<'div'>) => (
  <div
    className={cn(
      'rounded-grade border border-borda bg-superficie shadow-grade',
      className,
    )}
    {...props}
  />
)

export function Etiqueta({
  children,
  tom = 'neutro',
  Icone,
  className,
}: {
  children: ReactNode
  tom?: 'neutro' | 'ok' | 'alerta' | 'erro' | 'fatec' | 'etec'
  Icone?: typeof Check
  className?: string
}) {
  const tons = {
    neutro: 'border-borda text-texto-suave',
    ok: 'border-ok/40 text-ok',
    alerta: 'border-alerta/40 text-alerta',
    erro: 'border-erro/40 text-erro',
    fatec: 'border-fatec/40 text-fatec',
    etec: 'border-etec/40 text-etec',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium',
        tons[tom],
        className,
      )}
    >
      {Icone && <Icone className="size-3" aria-hidden />}
      {children}
    </span>
  )
}

// ------------------------------------------------------- vazio / esqueleto

export function EstadoVazio({
  Icone,
  titulo,
  descricao,
  acao,
}: {
  Icone: typeof Check
  titulo: string
  descricao: string
  acao?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center rounded-grade border border-dashed border-borda-forte px-6 py-14 text-center">
      <span className="grid size-11 place-items-center rounded-xl bg-superficie-2 text-texto-suave">
        <Icone className="size-5" aria-hidden />
      </span>
      <p className="mt-4 font-medium">{titulo}</p>
      <p className="mt-1 max-w-sm text-sm text-texto-suave">{descricao}</p>
      {acao && <div className="mt-5">{acao}</div>}
    </div>
  )
}

/**
 * Esqueletos com o formato do conteudo, nao barras genericas.
 *
 * A promessa da secao 11.2 da spec e' que nao haja tela de carregando; o que
 * substitui e' um desenho que ja tem as medidas do que vai chegar, para a
 * pagina nao pular quando os dados aparecem. Uma pilha de barras no lugar de
 * uma tabela de horario pula.
 */
export const LinhasEsqueleto = ({ linhas = 4 }: { linhas?: number }) => (
  <div className="space-y-2" aria-hidden>
    {Array.from({ length: linhas }, (_, i) => (
      <div key={i} className="esqueleto h-14 w-full" />
    ))}
  </div>
)

/** Grade de cartoes: mesma coluna, mesma altura, mesmo espacamento da lista. */
export const CartoesEsqueleto = ({
  quantidade = 3,
  altura = 'h-44',
}: {
  quantidade?: number
  altura?: string
}) => (
  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-hidden>
    {Array.from({ length: quantidade }, (_, i) => (
      <div key={i} className={cn('esqueleto rounded-grade', altura)} />
    ))}
  </div>
)

/** Tabela semanal: cabecalho, coluna de horarios e o miolo das aulas. */
export function GradeEsqueleto({ colunas = 3, linhas = 8 }: { colunas?: number; linhas?: number }) {
  return (
    <div className="p-2" aria-hidden>
      <div className="flex gap-2 p-2">
        <div className="esqueleto h-8 w-24 shrink-0" />
        {Array.from({ length: colunas }, (_, i) => (
          <div key={i} className="esqueleto h-8 flex-1" />
        ))}
      </div>
      {Array.from({ length: linhas }, (_, linha) => (
        <div key={linha} className="flex gap-2 p-2">
          <div className="esqueleto h-11 w-24 shrink-0 opacity-60" />
          {Array.from({ length: colunas }, (_, coluna) => (
            <div
              key={coluna}
              className="esqueleto h-11 flex-1"
              // Buracos: uma grade cheia de blocos identicos parece uma tabela
              // de dados, nao uma semana de aulas.
              style={{ opacity: (linha * 7 + coluna * 3) % 5 === 0 ? 0.25 : 1 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}
