/**
 * A marca do Horário Inteligente.
 *
 * O símbolo é um quadro de horário de 3 × 3 — três dias, três aulas — em que
 * as aulas alocadas desenham um H: à esquerda um bloco geminado e uma aula
 * solta, à direita o inverso (que também se lê como o "i" de Inteligente), e
 * no meio, em amarelo marca-texto, a aula que encaixa. Os dois horários vagos
 * do meio aparecem como células apagadas.
 *
 * As cores são da marca e não acompanham o tema: o ladrilho é sempre índigo.
 * Os mesmos números estão em `docs/marca/*.svg` e em `public/favicon.svg`.
 */
const TINTA = '#4F46E5'
const MARCA_TEXTO = '#FFD60A'

export function Simbolo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 72 72" className={className} aria-hidden focusable="false">
      <rect width="72" height="72" rx="16" fill={TINTA} />
      <g fill="#fff">
        <rect x="12" y="12" width="14" height="31" rx="3.2" />
        <rect x="12" y="46" width="14" height="14" rx="3.2" />
        <rect x="46" y="12" width="14" height="14" rx="3.2" />
        <rect x="46" y="29" width="14" height="31" rx="3.2" />
        <rect x="29" y="12" width="14" height="14" rx="3.2" opacity=".15" />
        <rect x="29" y="46" width="14" height="14" rx="3.2" opacity=".15" />
      </g>
      <rect x="29" y="29" width="14" height="14" rx="3.2" fill={MARCA_TEXTO} />
    </svg>
  )
}

/** Símbolo + nome: "Horário" pesado, "Inteligente" leve, como na assinatura. */
export function Logo({ comNome = true }: { comNome?: boolean }) {
  return (
    <span className="flex shrink-0 items-center gap-2.5">
      <Simbolo className="size-8" />
      {comNome && (
        <span className="hidden text-[1.0625rem] tracking-tight sm:inline">
          <span className="font-extrabold">Horário</span>{' '}
          <span className="font-normal">Inteligente</span>
        </span>
      )}
    </span>
  )
}
