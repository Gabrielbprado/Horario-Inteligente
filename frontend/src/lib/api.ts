export class ErroApi extends Error {
  status: number
  detalhe: unknown

  constructor(status: number, detalhe: unknown, mensagem: string) {
    super(mensagem)
    this.name = 'ErroApi'
    this.status = status
    this.detalhe = detalhe
  }
}

/** Raiz da API. Exportada para quem precisa da URL crua: download por `<a>` e
 *  upload multipart, que nao passam pelo `api()`. */
export const BASE_API = import.meta.env.VITE_API_URL ?? '/api'

/** Cliente HTTP unico. Erros viram `ErroApi` com a mensagem ja em pt-BR. */
export async function api<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(`${BASE_API}${caminho}`, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null)
    const detalhe = corpo?.detail ?? corpo
    const mensagem =
      typeof detalhe === 'string' ? detalhe : `Falha na requisicao (${resposta.status})`
    throw new ErroApi(resposta.status, detalhe, mensagem)
  }

  return resposta.status === 204 ? (undefined as T) : ((await resposta.json()) as T)
}

export const jsonBody = (dados: unknown) => JSON.stringify(dados)
