import { describe, expect, it } from 'vitest'

import { calcularJanelas } from './grade-semanal'
import type { CelulaGrade, TipoVisao, VisaoGrade } from '@/lib/tipos'

const NOTURNO = 1
const MANHA = 2

/** Uma faixa de horário: `(dia, início, fim)`. */
const hora = (h: number) => `${String(h).padStart(2, '0')}:00:00`

function montar({
  tipo = 'turma' as TipoVisao,
  colunas,
  horas,
  slots,
  aulas,
}: {
  tipo?: TipoVisao
  colunas: { id: number; modelo?: number }[]
  horas: number[]
  slots: { modelo: number; hora: number }[]
  aulas: { coluna: number; hora: number; modelo?: number }[]
}): VisaoGrade {
  return {
    grade_id: 1,
    tipo,
    colunas: colunas.map((c) => ({
      id: c.id,
      titulo: `col ${c.id}`,
      subtitulo: null,
      tipo: null,
      modelo_turno_id: c.modelo ?? null,
    })),
    horarios: horas.map((h) => ({ dia: 0, inicio: hora(h), fim: hora(h + 1), ordens: [h] })),
    slots: slots.map((s, i) => ({
      id: i + 1,
      modelo_turno_id: s.modelo,
      dia: 0,
      ordem: s.hora,
      inicio: hora(s.hora),
      fim: hora(s.hora + 1),
      bloco_id: 1,
    })),
    celulas: aulas.map(
      (a, i) =>
        ({
          alocacao_id: i + 1,
          oferta_id: i + 1,
          disciplina_id: 1,
          disciplina_sigla: 'X',
          disciplina_nome: 'X',
          turma_id: a.coluna,
          turma_rotulo: 'T',
          subturma: null,
          professor_id: a.coluna,
          professor_nome: 'P',
          espaco_id: a.coluna,
          espaco_nome: 'S',
          slot_id: i + 100,
          modelo_turno_id: a.modelo ?? NOTURNO,
          dia: 0,
          ordem: a.hora,
          inicio: hora(a.hora),
          fim: hora(a.hora + 1),
          bloco_id: 1,
          bloco_idx: 0,
          remota: false,
          precisa_laboratorio: false,
          fixada: false,
        }) satisfies CelulaGrade,
    ),
  }
}

describe('janelas na grade', () => {
  it('marca o horário vago que tem aula depois', () => {
    const visao = montar({
      colunas: [{ id: 1, modelo: NOTURNO }],
      horas: [19, 20, 21],
      slots: [19, 20, 21].map((h) => ({ modelo: NOTURNO, hora: h })),
      aulas: [
        { coluna: 1, hora: 19 },
        { coluna: 1, hora: 21 },
      ],
    })
    expect([...calcularJanelas(visao)]).toEqual(['0-20:00:00|1'])
  })

  it('vago no fim do dia não é janela: a turma sai mais cedo', () => {
    const visao = montar({
      colunas: [{ id: 1, modelo: NOTURNO }],
      horas: [19, 20, 21],
      slots: [19, 20, 21].map((h) => ({ modelo: NOTURNO, hora: h })),
      aulas: [{ coluna: 1, hora: 19 }],
    })
    expect(calcularJanelas(visao).size).toBe(0)
  })

  it('turno que a coluna não tem não vira janela', () => {
    // A coluna 1 é do noturno; as linhas da manhã existem por causa de outra
    // turma. Elas não são buraco na grade de quem só estuda à noite — mas a
    // vaga das 19h, essa sim, é janela de verdade.
    const visao = montar({
      colunas: [{ id: 1, modelo: NOTURNO }],
      horas: [7, 8, 19, 20],
      slots: [
        { modelo: MANHA, hora: 7 },
        { modelo: MANHA, hora: 8 },
        { modelo: NOTURNO, hora: 19 },
        { modelo: NOTURNO, hora: 20 },
      ],
      aulas: [{ coluna: 1, hora: 20 }],
    })
    expect([...calcularJanelas(visao)]).toEqual(['0-19:00:00|1'])
  })

  it('a manhã inteira não vira janela para quem só tem aula à noite', () => {
    const visao = montar({
      colunas: [{ id: 1, modelo: NOTURNO }],
      horas: [7, 8, 9, 19, 20],
      slots: [
        { modelo: MANHA, hora: 7 },
        { modelo: MANHA, hora: 8 },
        { modelo: MANHA, hora: 9 },
        { modelo: NOTURNO, hora: 19 },
        { modelo: NOTURNO, hora: 20 },
      ],
      aulas: [
        { coluna: 1, hora: 19 },
        { coluna: 1, hora: 20 },
      ],
    })
    expect(calcularJanelas(visao).size).toBe(0)
  })

  it('a janela continua sendo detectada dentro do turno da coluna', () => {
    const visao = montar({
      colunas: [{ id: 1, modelo: NOTURNO }],
      horas: [7, 19, 20, 21],
      slots: [
        { modelo: MANHA, hora: 7 },
        { modelo: NOTURNO, hora: 19 },
        { modelo: NOTURNO, hora: 20 },
        { modelo: NOTURNO, hora: 21 },
      ],
      aulas: [
        { coluna: 1, hora: 19 },
        { coluna: 1, hora: 21 },
      ],
    })
    expect([...calcularJanelas(visao)]).toEqual(['0-20:00:00|1'])
  })

  it('sala vaga não é janela: sala vaga é sala livre', () => {
    const visao = montar({
      tipo: 'espaco',
      colunas: [{ id: 1 }],
      horas: [19, 20, 21],
      slots: [19, 20, 21].map((h) => ({ modelo: NOTURNO, hora: h })),
      aulas: [
        { coluna: 1, hora: 19 },
        { coluna: 1, hora: 21 },
      ],
    })
    expect(calcularJanelas(visao).size).toBe(0)
  })

  it('cada coluna é avaliada por si', () => {
    const visao = montar({
      colunas: [
        { id: 1, modelo: NOTURNO },
        { id: 2, modelo: NOTURNO },
      ],
      horas: [19, 20, 21],
      slots: [19, 20, 21].map((h) => ({ modelo: NOTURNO, hora: h })),
      aulas: [
        { coluna: 1, hora: 19 },
        { coluna: 1, hora: 21 },
        { coluna: 2, hora: 19 },
        { coluna: 2, hora: 20 },
      ],
    })
    expect([...calcularJanelas(visao)]).toEqual(['0-20:00:00|1'])
  })

  it('na visão por professor, o turno sai das aulas do próprio docente', () => {
    // A coluna de um professor não declara turno nenhum. Quem só leciona à
    // noite numa unidade que também usa a manhã aparecia com a manhã inteira
    // marcada como janela — o PDF já acertava, a tela não.
    const visao = montar({
      tipo: 'professor',
      colunas: [{ id: 1 }],
      horas: [7, 8, 19, 20],
      slots: [
        { modelo: MANHA, hora: 7 },
        { modelo: MANHA, hora: 8 },
        { modelo: NOTURNO, hora: 19 },
        { modelo: NOTURNO, hora: 20 },
      ],
      aulas: [{ coluna: 1, hora: 20, modelo: NOTURNO }],
    })
    // A manhã some da conta; a vaga das 19h continua sendo janela de verdade,
    // porque é horário do turno dele e tem aula logo depois.
    expect([...calcularJanelas(visao)]).toEqual(['0-19:00:00|1'])
  })

  it('o professor que leciona nos dois turnos tem janela nos dois', () => {
    const visao = montar({
      tipo: 'professor',
      colunas: [{ id: 1 }],
      horas: [7, 8, 19, 20],
      slots: [
        { modelo: MANHA, hora: 7 },
        { modelo: MANHA, hora: 8 },
        { modelo: NOTURNO, hora: 19 },
        { modelo: NOTURNO, hora: 20 },
      ],
      aulas: [
        { coluna: 1, hora: 7, modelo: MANHA },
        { coluna: 1, hora: 20, modelo: NOTURNO },
      ],
    })
    // 08h e 19h ficam entre a primeira e a última aula do dia.
    expect([...calcularJanelas(visao)].sort()).toEqual(['0-08:00:00|1', '0-19:00:00|1'])
  })

  it('desligar o destaque devolve conjunto vazio', () => {
    const visao = montar({
      colunas: [{ id: 1, modelo: NOTURNO }],
      horas: [19, 20, 21],
      slots: [19, 20, 21].map((h) => ({ modelo: NOTURNO, hora: h })),
      aulas: [
        { coluna: 1, hora: 19 },
        { coluna: 1, hora: 21 },
      ],
    })
    expect(calcularJanelas(visao, false).size).toBe(0)
  })
})
