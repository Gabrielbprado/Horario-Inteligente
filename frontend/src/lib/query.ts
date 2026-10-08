import type { PersistedClient, Persister } from '@tanstack/react-query-persist-client'
import { QueryClient } from '@tanstack/react-query'
import { del, get, set } from 'idb-keyval'

/**
 * Persistencia no IndexedDB: ao reabrir o app os dados aparecem na hora e sao
 * revalidados em segundo plano (secao 11.2 da spec). Qualquer falha do IndexedDB
 * (modo privado, cota, navegador antigo) e engolida: o app so perde o cache frio.
 */
export function criarPersister(chave = 'horario-inteligente'): Persister {
  return {
    persistClient: async (cliente: PersistedClient) => {
      try {
        await set(chave, cliente)
      } catch {
        /* cache e otimizacao, nunca requisito */
      }
    },
    restoreClient: async () => {
      try {
        return await get<PersistedClient>(chave)
      } catch {
        return undefined
      }
    },
    removeClient: async () => {
      try {
        await del(chave)
      } catch {
        /* idem */
      }
    },
  }
}

export function criarQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // stale-while-revalidate: mostra o cache imediatamente, revalida atras
        staleTime: 30_000,
        gcTime: 24 * 60 * 60 * 1000,
        refetchOnWindowFocus: true,
        retry: (falhas, erro) => {
          const status = (erro as { status?: number }).status
          if (status && status >= 400 && status < 500) return false
          return falhas < 2
        },
      },
      mutations: { retry: 0 },
    },
  })
}
