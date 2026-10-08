import { describe, expect, it } from 'vitest'

import { filtrar } from './paleta'

const entrada = (grupo: string, texto: string, detalhe?: string) => ({
  chave: `${grupo}-${texto}`,
  grupo,
  Icone: (() => null) as never,
  texto,
  detalhe,
  destino: '/',
})

const muitos = (grupo: string, n: number) =>
  Array.from({ length: n }, (_, i) => entrada(grupo, `${grupo} ${i}`))

describe('filtro da paleta de comandos', () => {
  it('nunca entrega mais que seis itens por grupo', () => {
    // Com uma região inteira no banco são 1500+ registros; entregar todos ao
    // cmdk congelava a aba a cada tecla digitada.
    const resultado = filtrar([...muitos('Professores', 500), ...muitos('Turmas', 200)], '')

    for (const [, itens] of resultado) expect(itens.length).toBeLessThanOrEqual(6)
  })

  it('diz quantos ficaram de fora, para o usuário saber que vale refinar', () => {
    const [[grupo, itens, total]] = filtrar(muitos('Professores', 500), '')
    expect(grupo).toBe('Professores')
    expect(itens).toHaveLength(6)
    expect(total).toBe(500)
  })

  it('ignora acento e caixa', () => {
    const lista = [entrada('Professores', 'Iara Figueiredo'), entrada('Salas', 'Lab. Saúde 1')]
    expect(filtrar(lista, 'iara')[0][1][0].texto).toBe('Iara Figueiredo')
    expect(filtrar(lista, 'SAUDE')[0][1][0].texto).toBe('Lab. Saúde 1')
  })

  it('também procura no detalhe', () => {
    const lista = [entrada('Turmas', 'DSM · 1º sem', 'Noturno')]
    expect(filtrar(lista, 'noturno')).toHaveLength(1)
  })

  it('procura cada palavra por conta própria', () => {
    // Casamento de trecho contíguo perderia isto por causa do ponto.
    const lista = [entrada('Salas', 'Lab. Informatica 3')]
    expect(filtrar(lista, 'lab inform')).toHaveLength(1)
    expect(filtrar(lista, '3 lab')).toHaveLength(1)
  })

  it('devolve vazio quando nada casa, sem grupo fantasma', () => {
    expect(filtrar([entrada('Turmas', 'DSM')], 'xyz')).toEqual([])
  })
})
