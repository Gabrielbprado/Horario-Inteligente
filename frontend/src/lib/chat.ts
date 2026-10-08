/**
 * Cliente do chat: consome o SSE do backend e mantém a conversa em memória.
 *
 * `fetch` em vez de `EventSource` porque a mensagem vai no corpo de um POST —
 * `EventSource` só faz GET.
 */
import { useCallback, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api, BASE_API, jsonBody } from '@/lib/api'
import type { MensagemChat, Proposta, Violacao } from '@/lib/tipos'

export const useEstadoChat = () =>
  useQuery({
    queryKey: ['chat-estado'],
    queryFn: () => api<{ ativo: boolean; mensagem: string | null }>('/chat/estado'),
    // Isto é configuração do servidor, não dado do usuário: nunca servir do
    // cache em disco. Um "desativado" velho esconderia um chat que já funciona.
    staleTime: 0,
    gcTime: 0,
  })

type EventoSSE = { tipo: string; dados: Record<string, unknown> }

/** Divide o fluxo bruto em eventos `event:`/`data:`. */
export function* separarEventos(bloco: string): Generator<EventoSSE> {
  for (const pedaco of bloco.split('\n\n')) {
    if (!pedaco.trim()) continue
    let tipo = 'message'
    const linhasDados: string[] = []
    for (const linha of pedaco.split('\n')) {
      if (linha.startsWith('event:')) tipo = linha.slice(6).trim()
      else if (linha.startsWith('data:')) linhasDados.push(linha.slice(5).trim())
    }
    try {
      yield { tipo, dados: JSON.parse(linhasDados.join('\n') || '{}') }
    } catch {
      /* pedaço incompleto: o próximo chunk completa */
    }
  }
}

const novoId = () => Math.random().toString(36).slice(2, 10)

export function useConversa(gradeId: number) {
  const [mensagens, setMensagens] = useState<MensagemChat[]>([])
  const [respondendo, setRespondendo] = useState(false)
  const abortar = useRef<AbortController | null>(null)
  const cliente = useQueryClient()

  const enviar = useCallback(
    async (texto: string) => {
      if (!texto.trim() || respondendo) return
      const pergunta: MensagemChat = { id: novoId(), papel: 'user', texto }
      const resposta: MensagemChat = { id: novoId(), papel: 'assistant', texto: '' }
      // O histórico enviado é o de antes desta pergunta.
      const historico = mensagens.map((m) => ({ papel: m.papel, texto: m.texto }))

      setMensagens((atuais) => [...atuais, pergunta, resposta])
      setRespondendo(true)
      abortar.current = new AbortController()

      const atualizar = (mudar: (m: MensagemChat) => MensagemChat) =>
        setMensagens((atuais) =>
          atuais.map((m) => (m.id === resposta.id ? mudar(m) : m)),
        )

      try {
        const r = await fetch(`${BASE_API}/grades/${gradeId}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: jsonBody({ texto, historico }),
          signal: abortar.current.signal,
        })
        if (!r.ok || !r.body) {
          const corpo = await r.json().catch(() => null)
          throw new Error(corpo?.detail ?? `Falha na conversa (${r.status})`)
        }

        const leitor = r.body.getReader()
        const decodificador = new TextDecoder()
        let pendente = ''
        for (;;) {
          const { done, value } = await leitor.read()
          if (done) break
          pendente += decodificador.decode(value, { stream: true })
          // Guarda o último pedaço, que pode estar cortado no meio.
          const corte = pendente.lastIndexOf('\n\n')
          if (corte === -1) continue
          const completos = pendente.slice(0, corte + 2)
          pendente = pendente.slice(corte + 2)

          for (const evento of separarEventos(completos)) {
            if (evento.tipo === 'texto') {
              atualizar((m) => ({ ...m, texto: m.texto + String(evento.dados.delta ?? '') }))
            } else if (evento.tipo === 'ferramenta') {
              atualizar((m) => ({
                ...m,
                ferramentas: [...(m.ferramentas ?? []), String(evento.dados.nome)],
              }))
            } else if (evento.tipo === 'proposta') {
              atualizar((m) => ({
                ...m,
                propostas: [
                  ...(m.propostas ?? []),
                  // O evento não carrega os campos de estado: eles nascem falsos.
                  { aplicada: false, descartada: false, grade_id: gradeId, ...evento.dados } as Proposta,
                ],
              }))
            } else if (evento.tipo === 'erro') {
              atualizar((m) => ({ ...m, erro: String(evento.dados.mensagem) }))
            }
          }
        }
      } catch (erro) {
        if ((erro as Error).name === 'AbortError') {
          atualizar((m) => ({ ...m, erro: 'Interrompido.' }))
        } else {
          atualizar((m) => ({ ...m, erro: (erro as Error).message }))
        }
      } finally {
        setRespondendo(false)
        abortar.current = null
      }
    },
    [gradeId, mensagens, respondendo],
  )

  const interromper = useCallback(() => abortar.current?.abort(), [])
  const limpar = useCallback(() => setMensagens([]), [])

  /** Marca a proposta como resolvida no cartão, sem recarregar a conversa. */
  const resolverProposta = useCallback((propostaId: string, campo: 'aplicada' | 'descartada') => {
    setMensagens((atuais) =>
      atuais.map((m) => ({
        ...m,
        propostas: m.propostas?.map((p) =>
          p.id === propostaId ? { ...p, [campo]: true } : p,
        ),
      })),
    )
  }, [])

  const aplicar = useCallback(
    async (propostaId: string, forcar = false) => {
      try {
        const r = await api<{ descricao: string; violacoes: Violacao[] }>(
          `/propostas/${propostaId}/aplicar?forcar=${forcar}`,
          { method: 'POST' },
        )
        resolverProposta(propostaId, 'aplicada')
        toast.success('Alteração aplicada', { description: r.descricao })
        for (const chave of ['visao', 'avisos', 'historico', 'grades', 'destinos']) {
          cliente.invalidateQueries({ queryKey: [chave] })
        }
      } catch (erro) {
        toast.error('Não foi possível aplicar', { description: (erro as Error).message })
      }
    },
    [cliente, resolverProposta],
  )

  const descartar = useCallback(
    async (propostaId: string) => {
      await api(`/propostas/${propostaId}/descartar`, { method: 'POST' }).catch(() => null)
      resolverProposta(propostaId, 'descartada')
    },
    [resolverProposta],
  )

  return { mensagens, respondendo, enviar, interromper, limpar, aplicar, descartar }
}
