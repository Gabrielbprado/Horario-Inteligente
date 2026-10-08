import { describe, expect, it } from 'vitest'

import { compararClassificacao } from './professores'
import type { Vinculo } from '@/lib/tipos'

const vinculo = (campos: Partial<Vinculo>): Vinculo => ({
  id: 1,
  professor_id: 1,
  unidade_id: 1,
  tipo_contrato: 'INDETERMINADO',
  pontuacao: 0,
  pont_assiduidade: 0,
  pont_titulacao: 0,
  tempo_exercicio_meses: 0,
  num_filhos: 0,
  carga_max_semanal: null,
  ...campos,
})

/** `a` vem antes de `b` na classificação. */
const antesDe = (a: Vinculo, b: Vinculo) => compararClassificacao(a, b) < 0

describe('classificação docente (Portaria CETEC 1.263/2017)', () => {
  it('ordena por pontuação decrescente', () => {
    expect(antesDe(vinculo({ pontuacao: 87.5 }), vinculo({ pontuacao: 72 }))).toBe(true)
    expect(antesDe(vinculo({ pontuacao: 72 }), vinculo({ pontuacao: 87.5 }))).toBe(false)
  })

  it('empate na pontuação: decide a assiduidade', () => {
    const gisele = vinculo({ pontuacao: 61, pont_assiduidade: 20, pont_titulacao: 24 })
    const henrique = vinculo({ pontuacao: 61, pont_assiduidade: 12, pont_titulacao: 26 })
    expect(antesDe(gisele, henrique)).toBe(true)
  })

  it('empate na assiduidade: decide a titulação', () => {
    const a = vinculo({ pontuacao: 61, pont_assiduidade: 20, pont_titulacao: 30 })
    const b = vinculo({ pontuacao: 61, pont_assiduidade: 20, pont_titulacao: 26 })
    expect(antesDe(a, b)).toBe(true)
  })

  it('empate na titulação: decide o tempo de exercício', () => {
    const base = { pontuacao: 61, pont_assiduidade: 20, pont_titulacao: 30 }
    expect(
      antesDe(
        vinculo({ ...base, tempo_exercicio_meses: 120 }),
        vinculo({ ...base, tempo_exercicio_meses: 60 }),
      ),
    ).toBe(true)
  })

  it('último critério: número de filhos', () => {
    const base = {
      pontuacao: 61,
      pont_assiduidade: 20,
      pont_titulacao: 30,
      tempo_exercicio_meses: 60,
    }
    expect(antesDe(vinculo({ ...base, num_filhos: 3 }), vinculo({ ...base, num_filhos: 1 }))).toBe(
      true,
    )
  })

  it('vínculos idênticos empatam de verdade', () => {
    expect(compararClassificacao(vinculo({ pontuacao: 50 }), vinculo({ pontuacao: 50 }))).toBe(0)
  })
})
