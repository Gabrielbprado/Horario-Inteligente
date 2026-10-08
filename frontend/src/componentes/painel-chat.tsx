/**
 * Painel lateral do assistente.
 *
 * O modelo nunca altera a grade: cada pedido de mudança volta como um cartão
 * "antes → depois" com Aplicar e Descartar (seção 6.3 da spec).
 */
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowRight,
  Bot,
  Check,
  MessagesSquare,
  OctagonX,
  Send,
  Square,
  TriangleAlert,
  Trash2,
  Wrench,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Botao, Cartao, Etiqueta } from '@/componentes/ui'
import { useConversa, useEstadoChat } from '@/lib/chat'
import type { MensagemChat, Proposta } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const NOME_FERRAMENTA: Record<string, string> = {
  buscar_grade: 'lendo a grade',
  buscar_entidades: 'procurando quem você citou',
  validar_movimento: 'conferindo se cabe',
  mover_aula: 'preparando a mudança',
  trocar_aulas: 'preparando a troca',
  fixar_aula: 'preparando o cadeado',
  alterar_disponibilidade: 'preparando a disponibilidade',
  regenerar_parcial: 'recalculando a vizinhança',
  explicar: 'levantando o porquê',
  desfazer: 'preparando o desfazer',
}

/** Tira o "Chat desativado:" da mensagem da API, que aqui ja e' o titulo. */
export function semPrefixo(mensagem: string | null): string {
  const resto = (mensagem ?? '').replace(/^chat desativado:\s*/i, '').trim()
  if (!resto) return 'Configure OPENAI_API_KEY e OPENAI_MODEL no servidor.'
  return resto[0].toUpperCase() + resto.slice(1)
}

const SUGESTOES = [
  'Por que essa turma tem janela?',
  'O professor X não pode mais às segundas',
  'Mostre as aulas de sexta',
]

export function PainelChat({
  gradeId,
  aberto,
  aoFechar,
}: {
  gradeId: number
  aberto: boolean
  aoFechar: () => void
}) {
  const { data: estado } = useEstadoChat()
  const conversa = useConversa(gradeId)
  const [texto, setTexto] = useState('')
  const fim = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fim.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [conversa.mensagens])

  return (
    <AnimatePresence>
      {aberto && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={aoFechar}
            className="nao-imprimir fixed inset-0 z-40 bg-black/25 lg:hidden"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            role="complementary"
            aria-label="Assistente de horários"
            className="nao-imprimir fixed end-0 top-0 z-40 flex h-dvh w-[min(26rem,100vw)] flex-col border-s border-borda bg-superficie shadow-grade"
          >
            <header className="flex items-center gap-2 border-b border-borda px-4 py-3">
              <Bot className="size-4.5 text-primaria" aria-hidden />
              <h2 className="font-medium">Assistente</h2>
              {conversa.mensagens.length > 0 && (
                <Botao
                  tamanho="sm"
                  variante="fantasma"
                  className="ms-auto"
                  onClick={conversa.limpar}
                >
                  <Trash2 className="size-3.5" aria-hidden />
                  Limpar
                </Botao>
              )}
              <button
                type="button"
                onClick={aoFechar}
                aria-label="Fechar o assistente"
                className={cn(
                  'grid size-8 place-items-center rounded-lg text-texto-suave hover:bg-superficie-2',
                  conversa.mensagens.length === 0 && 'ms-auto',
                )}
              >
                <X className="size-4" aria-hidden />
              </button>
            </header>

            {estado && !estado.ativo ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
                <MessagesSquare className="size-8 text-texto-suave" aria-hidden />
                <p className="font-medium">Chat desativado</p>
                {/* A mensagem da API se basta sozinha ("Chat desativado:
                    configure..."), mas aqui repetiria o titulo logo acima. */}
                <p className="text-sm text-texto-suave">{semPrefixo(estado.mensagem)}</p>
                <p className="text-xs text-texto-suave">
                  O resto do sistema funciona normalmente.
                </p>
              </div>
            ) : (
              <>
                <div className="flex-1 space-y-4 overflow-y-auto p-4">
                  {conversa.mensagens.length === 0 && (
                    <div className="space-y-3 text-sm text-texto-suave">
                      <p>
                        Peça alterações em português. Toda mudança vira uma proposta que
                        você confere antes de aplicar.
                      </p>
                      <div className="flex flex-col gap-1.5">
                        {SUGESTOES.map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => conversa.enviar(s)}
                            className="rounded-lg border border-borda px-3 py-2 text-start text-sm hover:bg-superficie-2"
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {conversa.mensagens.map((mensagem) => (
                    <Mensagem
                      key={mensagem.id}
                      mensagem={mensagem}
                      aoAplicar={conversa.aplicar}
                      aoDescartar={conversa.descartar}
                    />
                  ))}
                  <div ref={fim} />
                </div>

                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    conversa.enviar(texto)
                    setTexto('')
                  }}
                  className="flex items-end gap-2 border-t border-borda p-3"
                >
                  <textarea
                    value={texto}
                    onChange={(e) => setTexto(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        conversa.enviar(texto)
                        setTexto('')
                      }
                    }}
                    rows={2}
                    placeholder="Troca a aula de Banco de Dados de terça para quinta…"
                    aria-label="Mensagem para o assistente"
                    className="min-h-[4.5rem] flex-1 resize-none rounded-lg border border-borda bg-superficie px-3 py-2 text-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria"
                  />
                  {conversa.respondendo ? (
                    <Botao type="button" tamanho="icone" onClick={conversa.interromper} aria-label="Parar">
                      <Square className="size-4" aria-hidden />
                    </Botao>
                  ) : (
                    <Botao
                      type="submit"
                      tamanho="icone"
                      variante="primario"
                      disabled={!texto.trim()}
                      aria-label="Enviar"
                    >
                      <Send className="size-4" aria-hidden />
                    </Botao>
                  )}
                </form>
              </>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function Mensagem({
  mensagem,
  aoAplicar,
  aoDescartar,
}: {
  mensagem: MensagemChat
  aoAplicar: (id: string, forcar?: boolean) => void
  aoDescartar: (id: string) => void
}) {
  const doUsuario = mensagem.papel === 'user'
  const pensando = !doUsuario && !mensagem.texto && !mensagem.erro

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('space-y-2', doUsuario && 'flex justify-end')}
    >
      {doUsuario ? (
        <p className="max-w-[85%] rounded-2xl rounded-ee-sm bg-primaria px-3 py-2 text-sm text-primaria-texto">
          {mensagem.texto}
        </p>
      ) : (
        <div className="space-y-2">
          {!!mensagem.ferramentas?.length && (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-texto-suave">
              <Wrench className="size-3" aria-hidden />
              {[...new Set(mensagem.ferramentas)]
                .map((f) => NOME_FERRAMENTA[f] ?? f)
                .join(' · ')}
            </p>
          )}

          {pensando ? (
            <p className="flex gap-1 text-texto-suave" aria-label="Digitando">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  animate={{ opacity: [0.25, 1, 0.25] }}
                  transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.18 }}
                  className="inline-block size-1.5 rounded-full bg-current"
                />
              ))}
            </p>
          ) : (
            mensagem.texto && (
              <p className="whitespace-pre-wrap text-sm">{mensagem.texto}</p>
            )
          )}

          {mensagem.propostas?.map((proposta) => (
            <CartaoProposta
              key={proposta.id}
              proposta={proposta}
              aoAplicar={aoAplicar}
              aoDescartar={aoDescartar}
            />
          ))}

          {mensagem.erro && (
            <p className="flex items-start gap-1.5 rounded-lg border border-erro/35 bg-erro/5 p-2 text-sm text-erro">
              <OctagonX className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {mensagem.erro}
            </p>
          )}
        </div>
      )}
    </motion.div>
  )
}

function CartaoProposta({
  proposta,
  aoAplicar,
  aoDescartar,
}: {
  proposta: Proposta
  aoAplicar: (id: string, forcar?: boolean) => void
  aoDescartar: (id: string) => void
}) {
  const resolvida = proposta.aplicada || proposta.descartada
  const bloqueante = !proposta.permitido

  return (
    <motion.div layout>
      <Cartao
        className={cn(
          'overflow-hidden',
          bloqueante && 'border-erro/40',
          resolvida && 'opacity-60',
        )}
      >
        <div className="flex items-center gap-2 border-b border-borda px-3 py-2">
          <Etiqueta tom={bloqueante ? 'erro' : 'neutro'}>{proposta.tipo}</Etiqueta>
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{proposta.descricao}</p>
          {proposta.aplicada && (
            <Etiqueta tom="ok" Icone={Check}>
              aplicada
            </Etiqueta>
          )}
          {proposta.descartada && <Etiqueta>descartada</Etiqueta>}
        </div>

        <ul className="divide-y divide-borda">
          {proposta.mudancas.slice(0, 8).map((mudanca, i) => (
            <li key={i} className="px-3 py-2 text-xs">
              <p className="font-medium">{mudanca.rotulo}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-texto-suave">
                <span className="line-through">{mudanca.antes}</span>
                <ArrowRight className="size-3 shrink-0" aria-hidden />
                <span className="font-medium text-texto">{mudanca.depois}</span>
              </p>
            </li>
          ))}
          {proposta.mudancas.length > 8 && (
            <li className="px-3 py-2 text-xs text-texto-suave">
              e mais {proposta.mudancas.length - 8} alteração(ões)
            </li>
          )}
        </ul>

        {!!proposta.violacoes.length && (
          <ul className="border-t border-borda bg-alerta/5 px-3 py-2 text-xs">
            {proposta.violacoes.slice(0, 3).map((v, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <TriangleAlert className="mt-0.5 size-3 shrink-0 text-alerta" aria-hidden />
                {v.mensagem}
              </li>
            ))}
          </ul>
        )}

        {!resolvida && (
          <div className="flex gap-2 border-t border-borda p-2">
            <Botao tamanho="sm" onClick={() => aoDescartar(proposta.id)}>
              Descartar
            </Botao>
            <Botao
              tamanho="sm"
              variante={bloqueante ? 'perigo' : 'primario'}
              className="ms-auto"
              onClick={() => aoAplicar(proposta.id, bloqueante)}
            >
              {bloqueante ? 'Aplicar mesmo assim' : 'Aplicar'}
            </Botao>
          </div>
        )}
      </Cartao>
    </motion.div>
  )
}
