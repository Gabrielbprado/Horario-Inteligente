import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { toast } from 'sonner'

import { api, jsonBody } from '@/lib/api'

type ComId = { id: number }
type Filtro = Record<string, string | number | undefined | null>

function querystring(filtro?: Filtro): string {
  if (!filtro) return ''
  const partes = Object.entries(filtro).filter(([, v]) => v !== undefined && v !== null)
  if (!partes.length) return ''
  return '?' + new URLSearchParams(partes.map(([k, v]) => [k, String(v)])).toString()
}

/** Ids otimistas sao negativos: nunca colidem com os do servidor e ficam faceis
 *  de reconhecer na UI (ainda salvando). */
let proximoIdProvisorio = -1
const idProvisorio = () => proximoIdProvisorio--

export const ehProvisorio = (id: number) => id < 0

/**
 * Camada de dados de um recurso REST.
 *
 * Toda mutacao e otimista: a lista em cache muda antes da resposta do servidor
 * e volta atras com um toast se ele recusar (secao 11.2 da spec). Sao onze
 * recursos com exatamente esse comportamento, por isso a fabrica.
 */
export function criarRecurso<T extends ComId, E extends object>(caminho: string) {
  const chaveBase = [caminho] as const
  const chave = (filtro?: Filtro) => (filtro ? [caminho, filtro] : chaveBase)

  const opcoes = (filtro?: Filtro) =>
    queryOptions({
      queryKey: chave(filtro),
      queryFn: () => api<T[]>(`/${caminho}${querystring(filtro)}`),
    })

  /** Carrega antes do clique (hover num link, abertura de uma unidade). */
  const prefetch = (cliente: QueryClient, filtro?: Filtro) =>
    cliente.prefetchQuery(opcoes(filtro))

  function useLista(filtro?: Filtro, habilitado = true) {
    return useQuery({ ...opcoes(filtro), enabled: habilitado })
  }

  /** Aplica `transformar` na lista em cache e devolve como desfazer. */
  function ajustarCache(cliente: QueryClient, filtro: Filtro | undefined, transformar: (l: T[]) => T[]) {
    const anterior = cliente.getQueryData<T[]>(chave(filtro))
    cliente.setQueryData<T[]>(chave(filtro), (lista) => transformar(lista ?? []))
    return () => cliente.setQueryData(chave(filtro), anterior)
  }

  function useCriar(filtro?: Filtro, rotulo = 'registro') {
    const cliente = useQueryClient()
    return useMutation({
      mutationFn: (dados: E) =>
        api<T>(`/${caminho}`, { method: 'POST', body: jsonBody(dados) }),
      onMutate: async (dados) => {
        await cliente.cancelQueries({ queryKey: chave(filtro) })
        const provisorio = { ...dados, id: idProvisorio() } as unknown as T
        return { desfazer: ajustarCache(cliente, filtro, (l) => [...l, provisorio]) }
      },
      onError: (erro, _dados, contexto) => {
        contexto?.desfazer()
        toast.error(`Não foi possível criar o ${rotulo}`, { description: erro.message })
      },
      onSettled: () => cliente.invalidateQueries({ queryKey: chaveBase }),
    })
  }

  function useAtualizar(filtro?: Filtro, rotulo = 'registro') {
    const cliente = useQueryClient()
    return useMutation({
      mutationFn: ({ id, ...dados }: Partial<E> & ComId) =>
        api<T>(`/${caminho}/${id}`, { method: 'PATCH', body: jsonBody(dados) }),
      onMutate: async ({ id, ...dados }) => {
        await cliente.cancelQueries({ queryKey: chave(filtro) })
        return {
          desfazer: ajustarCache(cliente, filtro, (l) =>
            l.map((item) => (item.id === id ? { ...item, ...dados } : item)),
          ),
        }
      },
      onError: (erro, _dados, contexto) => {
        contexto?.desfazer()
        toast.error(`Não foi possível salvar o ${rotulo}`, { description: erro.message })
      },
      onSettled: () => cliente.invalidateQueries({ queryKey: chaveBase }),
    })
  }

  function useApagar(filtro?: Filtro, rotulo = 'registro') {
    const cliente = useQueryClient()
    return useMutation({
      mutationFn: (id: number) => api<void>(`/${caminho}/${id}`, { method: 'DELETE' }),
      onMutate: async (id) => {
        await cliente.cancelQueries({ queryKey: chave(filtro) })
        return {
          desfazer: ajustarCache(cliente, filtro, (l) => l.filter((item) => item.id !== id)),
        }
      },
      onError: (erro, _id, contexto) => {
        contexto?.desfazer()
        toast.error(`Não foi possível excluir o ${rotulo}`, { description: erro.message })
      },
      onSettled: () => cliente.invalidateQueries({ queryKey: chaveBase }),
    })
  }

  return { caminho, chave, chaveBase, opcoes, prefetch, useLista, useCriar, useAtualizar, useApagar }
}
