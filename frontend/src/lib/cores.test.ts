import { describe, expect, it } from 'vitest'

import { estiloDisciplina, matizDisciplina } from './cores'

/** Distancia angular na roda de matizes. */
const distancia = (a: number, b: number) => {
  const d = Math.abs(a - b) % 360
  return Math.min(d, 360 - d)
}

describe('cor estavel por disciplina', () => {
  it('devolve sempre o mesmo matiz para a mesma chave', () => {
    expect(matizDisciplina(42)).toBe(matizDisciplina(42))
    expect(matizDisciplina('ALP')).toBe(matizDisciplina('ALP'))
    expect(matizDisciplina(42)).toBe(matizDisciplina('42'))
  })

  it('mantem o matiz dentro de [0, 360)', () => {
    for (const chave of ['ALP', 'DW1', 7, 999, '', 'disciplina com nome muito longo']) {
      const h = matizDisciplina(chave)
      expect(h).toBeGreaterThanOrEqual(0)
      expect(h).toBeLessThan(360)
    }
  })

  it('nunca produz duas cores quase iguais: ou coincidem, ou ficam bem separadas', () => {
    const siglas = [
      'ALP', 'DD', 'ESW1', 'MBD', 'SOR', 'MCT', 'DW1', 'ED',
      'BDR', 'ESW2', 'MAT', 'ING', 'DW2', 'PDM', 'BDN', 'IHC',
      'GP', 'EMP', 'LP', 'PW', 'BD', 'AI', 'PAP', 'QS', 'SE', 'PI',
    ]
    for (const a of siglas) {
      for (const b of siglas) {
        if (a === b) continue
        const d = distancia(matizDisciplina(a), matizDisciplina(b))
        // 0 = colisao aceita (a sigla desambigua); qualquer outra distancia
        // precisa ser grande o bastante para o olho separar.
        expect(d === 0 || d >= 22).toBe(true)
      }
    }
  })

  it('usa varios matizes diferentes, nao concentra tudo numa faixa', () => {
    const siglas = Array.from({ length: 60 }, (_, i) => `D${i}`)
    const distintos = new Set(siglas.map(matizDisciplina))
    expect(distintos.size).toBeGreaterThanOrEqual(10)
  })

  it('expoe o matiz como variavel CSS', () => {
    expect(estiloDisciplina('DW1')).toEqual({ '--cor-h': matizDisciplina('DW1') })
  })
})
