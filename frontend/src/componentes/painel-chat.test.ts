import { describe, expect, it } from 'vitest'

import { semPrefixo } from './painel-chat'

describe('mensagem de chat desativado', () => {
  it('tira o prefixo que o painel já mostra como título', () => {
    expect(semPrefixo('Chat desativado: configure OPENAI_API_KEY no servidor.')).toBe(
      'Configure OPENAI_API_KEY no servidor.',
    )
  })

  it('não depende da caixa do prefixo', () => {
    expect(semPrefixo('chat desativado: faltou a chave.')).toBe('Faltou a chave.')
  })

  it('deixa intacta a mensagem que não tem o prefixo', () => {
    expect(semPrefixo('A chave expirou.')).toBe('A chave expirou.')
  })

  it('tem um texto próprio quando a API não manda mensagem', () => {
    expect(semPrefixo(null)).toContain('OPENAI_API_KEY')
    expect(semPrefixo('Chat desativado:')).toContain('OPENAI_API_KEY')
  })
})
