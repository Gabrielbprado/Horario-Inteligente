import { Save, Scale, SlidersHorizontal, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  Botao,
  Campo,
  Cartao,
  Entrada,
  Interruptor,
  LinhasEsqueleto,
  Selecao,
} from '@/componentes/ui'
import { useConfigRegras, useGravarConfigRegras } from '@/lib/dados'
import type { ConfigRegras } from '@/lib/tipos'

const PESOS: { chave: keyof ConfigRegras['pesos']; rotulo: string; dica: string }[] = [
  {
    chave: 'nao_concentradas',
    rotulo: 'Disciplina não concentrada',
    dica: 'Por disciplina marcada para concentrar que não coube no mesmo dia. Alto de propósito: é quase regra.',
  },
  {
    chave: 'janela_turma',
    rotulo: 'Janela da turma',
    dica: 'Buraco no meio do dia. Peso alto empurra os horários vazios para o fim do dia.',
  },
  {
    chave: 'janela_professor',
    rotulo: 'Janela do professor',
    dica: 'Buraco entre aulas do mesmo docente no mesmo dia e unidade.',
  },
  {
    chave: 'preferencia',
    rotulo: 'Preferência atendida',
    dica: 'Recompensa por alocar num horário preferencial, ponderada pela pontuação.',
  },
  {
    chave: 'dias_professor',
    rotulo: 'Dias do professor',
    dica: 'Penaliza cada dia em que o docente precisa ir à unidade.',
  },
  {
    chave: 'estabilidade',
    rotulo: 'Estabilidade',
    dica: 'Ao regenerar, penaliza mudar o que já estava alocado.',
  },
  {
    chave: 'dia_curto_no_fim',
    rotulo: 'Dia curto no fim da semana',
    dica: 'Desempate leve: prefere que o dia com menos aulas seja o último.',
  },
]

export default function Regras() {
  const unidadeId = Number(useParams().unidadeId)
  const { data, isPending } = useConfigRegras(unidadeId)
  const gravar = useGravarConfigRegras(unidadeId)
  const [rascunho, setRascunho] = useState<ConfigRegras | null>(null)

  useEffect(() => {
    if (data) setRascunho(data)
  }, [data])

  if (isPending && !rascunho) return <LinhasEsqueleto linhas={5} />
  if (!rascunho) return null

  const alterado = JSON.stringify(rascunho) !== JSON.stringify(data)
  const mudar = <K extends keyof ConfigRegras>(chave: K, valor: ConfigRegras[K]) =>
    setRascunho((r) => (r ? { ...r, [chave]: valor } : r))

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Regras da unidade</h1>
          <p className="text-texto-suave">
            Todo número de negócio do solver mora aqui. Os valores nasceram do preset do tipo da
            unidade e podem ser mudados a qualquer momento.
          </p>
        </div>
        <Botao
          variante="primario"
          disabled={!alterado || gravar.isPending}
          onClick={() => gravar.mutate(rascunho)}
        >
          <Save className="size-4" aria-hidden />
          {alterado ? 'Salvar regras' : 'Salvo'}
        </Botao>
      </header>

      <Cartao className="space-y-5 p-6">
        <div className="flex items-center gap-2">
          <Scale className="size-4.5 text-texto-suave" aria-hidden />
          <h2 className="font-medium">Carga e jornada</h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Campo rotulo="Carga máxima semanal" dica="Fatec usa 29; Etec, 34.">
            <Entrada
              type="number"
              min={1}
              max={60}
              value={rascunho.carga_max_semanal}
              onChange={(e) => mudar('carga_max_semanal', Number(e.target.value))}
            />
          </Campo>
          <Campo
            rotulo="Deslocamento entre unidades"
            dica="Minutos mínimos entre aulas em unidades diferentes."
          >
            <Entrada
              type="number"
              min={0}
              max={600}
              value={rascunho.deslocamento_entre_unidades_min}
              onChange={(e) =>
                mudar('deslocamento_entre_unidades_min', Number(e.target.value))
              }
            />
          </Campo>
          <div className="flex items-end pb-2">
            <Interruptor
              marcado={rascunho.usa_sabado}
              aoMudar={(v) => mudar('usa_sabado', v)}
              rotulo="Usa sábado"
            />
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-borda p-4">
          <Interruptor
            marcado={rascunho.limite_diario.ativo}
            aoMudar={(v) => mudar('limite_diario', { ...rascunho.limite_diario, ativo: v })}
            rotulo="Limitar aulas por dia"
          />
          <p className="text-xs text-texto-suave">
            A regra de 4 aulas consecutivas ou 6 intercaladas vinha do art. 318 da CLT na
            redação antiga; a Lei 13.415/2017 a revogou. Fica aqui como limite opcional,
            desligado por padrão.
          </p>
          {rascunho.limite_diario.ativo && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Máximo de aulas consecutivas">
                <Entrada
                  type="number"
                  min={1}
                  max={12}
                  value={rascunho.limite_diario.max_consecutivas}
                  onChange={(e) =>
                    mudar('limite_diario', {
                      ...rascunho.limite_diario,
                      max_consecutivas: Number(e.target.value),
                    })
                  }
                />
              </Campo>
              <Campo rotulo="Máximo de aulas no dia">
                <Entrada
                  type="number"
                  min={1}
                  max={12}
                  value={rascunho.limite_diario.max_intercaladas}
                  onChange={(e) =>
                    mudar('limite_diario', {
                      ...rascunho.limite_diario,
                      max_intercaladas: Number(e.target.value),
                    })
                  }
                />
              </Campo>
            </div>
          )}
        </div>

        <div className="grid gap-4 rounded-lg border border-borda p-4 sm:grid-cols-2">
          <Campo
            rotulo="Interjornada (CLT art. 66)"
            dica="Descanso entre o fim de um dia e o início do seguinte, somando todas as unidades."
          >
            <Selecao
              valor={rascunho.interjornada.modo}
              aoMudar={(v) =>
                mudar('interjornada', {
                  ...rascunho.interjornada,
                  modo: v as ConfigRegras['interjornada']['modo'],
                })
              }
              aria-label="Modo da interjornada"
              opcoes={[
                { valor: 'off', rotulo: 'Não verificar' },
                { valor: 'aviso', rotulo: 'Gerar aviso' },
                { valor: 'rigida', rotulo: 'Restrição rígida' },
              ]}
            />
          </Campo>
          <Campo rotulo="Horas de descanso">
            <Entrada
              type="number"
              min={0}
              max={24}
              disabled={rascunho.interjornada.modo === 'off'}
              value={rascunho.interjornada.horas}
              onChange={(e) =>
                mudar('interjornada', {
                  ...rascunho.interjornada,
                  horas: Number(e.target.value),
                })
              }
            />
          </Campo>
        </div>
      </Cartao>

      <Cartao className="space-y-5 p-6">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="size-4.5 text-texto-suave" aria-hidden />
          <h2 className="font-medium">Atribuição de aulas</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo
            rotulo="Regra"
            dica="Etec: manutenção e depois ampliação, pela classificação. Fatec: contrato indeterminado primeiro."
          >
            <Selecao
              valor={rascunho.atribuicao.regra}
              aoMudar={(v) =>
                mudar('atribuicao', {
                  ...rascunho.atribuicao,
                  regra: v as ConfigRegras['atribuicao']['regra'],
                })
              }
              aria-label="Regra de atribuição"
              opcoes={[
                { valor: 'ETEC', rotulo: 'Etec (Deliberação 23/2015)' },
                { valor: 'FATEC', rotulo: 'Fatec (Deliberação 52/2019)' },
              ]}
            />
          </Campo>
          <div className="text-sm">
            <p className="font-medium text-texto-suave">Ordem de desempate</p>
            <ol className="mt-1.5 list-decimal space-y-0.5 ps-5 text-texto-suave">
              <li>Assiduidade e pontualidade</li>
              <li>Titulação e atualização</li>
              <li>Tempo de exercício na unidade</li>
              <li>Número de filhos</li>
            </ol>
          </div>
        </div>
      </Cartao>

      <Cartao className="space-y-5 p-6">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4.5 text-texto-suave" aria-hidden />
          <h2 className="font-medium">Objetivo do solver</h2>
        </div>

        <Campo
          rotulo="Modo"
          dica="Lexicográfico otimiza um critério por vez, na ordem abaixo; ponderado soma tudo."
          className="max-w-sm"
        >
          <Selecao
            valor={rascunho.modo_objetivo}
            aoMudar={(v) => mudar('modo_objetivo', v as ConfigRegras['modo_objetivo'])}
            aria-label="Modo do objetivo"
            opcoes={[
              { valor: 'ponderado', rotulo: 'Soma ponderada' },
              { valor: 'lexicografico', rotulo: 'Lexicográfico' },
            ]}
          />
        </Campo>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PESOS.map(({ chave, rotulo, dica }) => (
            <Campo key={chave} rotulo={rotulo} dica={dica}>
              <Entrada
                type="number"
                min={0}
                value={rascunho.pesos[chave]}
                disabled={rascunho.modo_objetivo === 'lexicografico'}
                onChange={(e) =>
                  mudar('pesos', { ...rascunho.pesos, [chave]: Number(e.target.value) })
                }
              />
            </Campo>
          ))}
        </div>
        {rascunho.modo_objetivo === 'lexicografico' && (
          <p className="text-xs text-texto-suave">
            No modo lexicográfico os pesos não são usados: vale a ordem em que aparecem acima.
          </p>
        )}
      </Cartao>
    </div>
  )
}
