/**
 * Etapa 10: a grade grande precisa desenhar rápido.
 *
 * O caso é o da seção 10 da spec — 10 turmas e 200 aulas — na visão por turma,
 * que é a que abre por padrão. Os limites são folgados (bem acima do medido em
 * máquina de desenvolvimento): servem para pegar regressão de ordem de
 * grandeza, não para cravar milissegundos numa CI compartilhada.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { GradeSemanal, calcularJanelas } from './grade-semanal'
import type { CelulaGrade, ColunaVisao, LinhaHorario, SlotRef, VisaoGrade } from '@/lib/tipos'

const TURMAS = 10
const DIAS = 5
const AULAS_POR_DIA = 4
const MODELO = 1

const hhmmss = (h: number) => `${String(h).padStart(2, '0')}:00:00`

/** Grade cheia: 10 turmas × 5 dias × 4 aulas = 200 aulas. */
function visaoGrande(): VisaoGrade {
  const colunas: ColunaVisao[] = Array.from({ length: TURMAS }, (_, i) => ({
    id: i + 1,
    titulo: `Turma ${i + 1}`,
    subtitulo: '40 alunos',
    tipo: null,
    modelo_turno_id: MODELO,
  }))

  const horarios: LinhaHorario[] = []
  const slots: SlotRef[] = []
  for (let dia = 0; dia < DIAS; dia++) {
    for (let ordem = 1; ordem <= AULAS_POR_DIA; ordem++) {
      const inicio = 18 + ordem
      horarios.push({ dia, inicio: hhmmss(inicio), fim: hhmmss(inicio + 1), ordens: [ordem] })
      slots.push({
        id: dia * 10 + ordem,
        modelo_turno_id: MODELO,
        dia,
        ordem,
        inicio: hhmmss(inicio),
        fim: hhmmss(inicio + 1),
        bloco_id: ordem <= 2 ? 1 : 2,
      })
    }
  }

  const celulas: CelulaGrade[] = []
  let n = 0
  for (let t = 0; t < TURMAS; t++) {
    for (let dia = 0; dia < DIAS; dia++) {
      for (let ordem = 1; ordem <= AULAS_POR_DIA; ordem++) {
        const inicio = 18 + ordem
        n++
        celulas.push({
          alocacao_id: n,
          oferta_id: n,
          disciplina_id: (n % 12) + 1,
          disciplina_sigla: `D${n % 12}`,
          disciplina_nome: `Disciplina ${n % 12}`,
          turma_id: t + 1,
          turma_rotulo: `Turma ${t + 1}`,
          subturma: null,
          professor_id: (n % 40) + 1,
          professor_nome: `Professor ${n % 40}`,
          espaco_id: (n % 18) + 1,
          espaco_nome: `Sala ${n % 18}`,
          slot_id: dia * 10 + ordem,
          modelo_turno_id: MODELO,
          dia,
          ordem,
          inicio: hhmmss(inicio),
          fim: hhmmss(inicio + 1),
          bloco_id: ordem <= 2 ? 1 : 2,
          bloco_idx: 0,
          remota: false,
          precisa_laboratorio: n % 5 === 0,
          fixada: n % 17 === 0,
        })
      }
    }
  }

  return { grade_id: 1, tipo: 'turma', colunas, horarios, slots, celulas }
}

describe('desempenho da grade grande', () => {
  it('tem mesmo 200 aulas e 10 colunas', () => {
    const visao = visaoGrande()
    expect(visao.celulas).toHaveLength(200)
    expect(visao.colunas).toHaveLength(TURMAS)
  })

  it('calcula as janelas de 200 aulas bem abaixo de um quadro de animação', () => {
    const visao = visaoGrande()
    calcularJanelas(visao) // a primeira paga o JIT

    const inicio = performance.now()
    for (let i = 0; i < 20; i++) calcularJanelas(visao)
    const ms = (performance.now() - inicio) / 20

    // Roda a cada render da grade; acima de 16 ms comeca a custar um quadro.
    expect(ms).toBeLessThan(16)
  })

  it('desenha a grade inteira num tempo aceitável', () => {
    const visao = visaoGrande()
    const inicio = performance.now()
    const { container } = render(<GradeSemanal visao={visao} />)
    const ms = performance.now() - inicio

    expect(container.querySelectorAll('.disciplina')).toHaveLength(200)
    // jsdom e' bem mais lento que um navegador; o limite pega regressao de
    // ordem de grandeza, nao milissegundos.
    expect(ms).toBeLessThan(3000)
  })
})
