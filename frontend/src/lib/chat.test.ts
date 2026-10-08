import { describe, expect, it } from 'vitest'

import { separarEventos } from './chat'

const eventos = (bruto: string) => [...separarEventos(bruto)]

describe('separarEventos', () => {
  it('lê o tipo e o corpo de cada evento', () => {
    const bruto =
      'event: texto\ndata: {"delta":"Oi"}\n\nevent: ferramenta\ndata: {"nome":"buscar_grade"}\n\n'
    expect(eventos(bruto)).toEqual([
      { tipo: 'texto', dados: { delta: 'Oi' } },
      { tipo: 'ferramenta', dados: { nome: 'buscar_grade' } },
    ])
  })

  it('preserva acentos e quebras dentro do texto', () => {
    const bruto = 'event: texto\ndata: {"delta":"terça-feira\\n20h50"}\n\n'
    expect(eventos(bruto)[0].dados.delta).toBe('terça-feira\n20h50')
  })

  it('ignora pedaço cortado no meio em vez de estourar', () => {
    expect(eventos('event: texto\ndata: {"delta":"in')).toEqual([])
  })

  it('aceita evento sem corpo', () => {
    expect(eventos('event: fim\ndata:\n\n')).toEqual([{ tipo: 'fim', dados: {} }])
  })
})
