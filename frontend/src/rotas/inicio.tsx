import { useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { Building2, CircleAlert, Layers, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Botao,
  Campo,
  Cartao,
  Dialogo,
  Entrada,
  EstadoVazio,
  Etiqueta,
  CartoesEsqueleto,
  Selecao,
} from '@/componentes/ui'
import { cursos, escopos, espacos, professores, unidades } from '@/lib/dados'
import { ehProvisorio } from '@/lib/recursos'
import type { TipoUnidade } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const CASCATA = {
  hidden: { opacity: 0, y: 10 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: Math.min(i, 8) * 0.04, duration: 0.24, ease: 'easeOut' as const },
  }),
}

export default function Inicio() {
  const cliente = useQueryClient()
  const listaEscopos = escopos.useLista()
  const listaUnidades = unidades.useLista()
  const criarEscopo = escopos.useCriar(undefined, 'escopo')
  const criarUnidade = unidades.useCriar(undefined, 'unidade')

  const [dialogoEscopo, setDialogoEscopo] = useState(false)
  const [dialogoUnidade, setDialogoUnidade] = useState<number | null>(null)

  const carregandoFrio = listaEscopos.isPending && !listaEscopos.data

  if (listaEscopos.isError) {
    return (
      <div className="rounded-grade border border-borda bg-superficie p-10 text-center">
        <CircleAlert className="mx-auto size-6 text-alerta" aria-hidden />
        <p className="mt-3 font-medium">Não foi possível falar com o servidor</p>
        <p className="mt-1 text-sm text-texto-suave">
          Verifique se a API está rodando em <code>http://localhost:8000</code>.
        </p>
        <Botao className="mt-5" variante="primario" onClick={() => listaEscopos.refetch()}>
          Tentar de novo
        </Botao>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Escopos e unidades</h1>
          <p className="text-texto-suave">
            Um escopo agrupa as unidades entre as quais o sistema detecta choque de horário.
          </p>
        </div>
        <Botao variante="primario" onClick={() => setDialogoEscopo(true)}>
          <Plus className="size-4" aria-hidden />
          Novo escopo
        </Botao>
      </header>

      {carregandoFrio ? (
        <CartoesEsqueleto quantidade={2} altura="h-32" />
      ) : !listaEscopos.data?.length ? (
        <EstadoVazio
          Icone={Layers}
          titulo="Nenhum escopo ainda"
          descricao="Comece criando o escopo Centro Paula Souza e depois adicione as Fatecs e Etecs."
          acao={
            <Botao variante="primario" onClick={() => setDialogoEscopo(true)}>
              <Plus className="size-4" aria-hidden />
              Criar escopo
            </Botao>
          }
        />
      ) : (
        <div className="space-y-8">
          {listaEscopos.data.map((escopo, i) => {
            const doEscopo = (listaUnidades.data ?? []).filter((u) => u.escopo_id === escopo.id)
            return (
              <motion.section
                key={escopo.id}
                custom={i}
                variants={CASCATA}
                initial="hidden"
                animate="show"
                className="space-y-3"
              >
                <div className="flex items-center gap-3">
                  <h2 className="font-semibold tracking-tight">{escopo.nome}</h2>
                  <span className="text-sm text-texto-suave">
                    {doEscopo.length} {doEscopo.length === 1 ? 'unidade' : 'unidades'}
                  </span>
                  <Botao
                    tamanho="sm"
                    variante="fantasma"
                    className="ms-auto"
                    onClick={() => setDialogoUnidade(escopo.id)}
                  >
                    <Plus className="size-4" aria-hidden />
                    Nova unidade
                  </Botao>
                </div>

                {doEscopo.length === 0 ? (
                  <Cartao className="p-6 text-sm text-texto-suave">
                    Nenhuma unidade neste escopo ainda.
                  </Cartao>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {doEscopo.map((unidade, j) => (
                      <motion.div key={unidade.id} custom={j} variants={CASCATA}>
                        <Link
                          to={`/unidades/${unidade.id}`}
                          onMouseEnter={() => {
                            cursos.prefetch(cliente, { unidade_id: unidade.id })
                            espacos.prefetch(cliente, { unidade_id: unidade.id })
                            professores.prefetch(cliente)
                          }}
                          className={cn(
                            'block h-full rounded-grade border border-borda bg-superficie p-5',
                            'shadow-grade transition-transform hover:scale-[1.01]',
                            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primaria',
                            ehProvisorio(unidade.id) && 'opacity-60',
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <Building2 className="size-5 text-texto-suave" aria-hidden />
                            <Etiqueta tom={unidade.tipo === 'FATEC' ? 'fatec' : 'etec'}>
                              {unidade.tipo}
                            </Etiqueta>
                          </div>
                          <p className="mt-3 font-medium">{unidade.nome}</p>
                          <p className="mt-0.5 text-sm text-texto-suave">
                            {unidade.cidade ?? 'Sem cidade informada'}
                          </p>
                          <p className="mt-3 text-xs text-texto-suave">
                            Carga máxima {unidade.carga_max_semanal_padrao} aulas/semana
                          </p>
                        </Link>
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.section>
            )
          })}
        </div>
      )}

      <DialogoEscopo
        aberto={dialogoEscopo}
        aoFechar={() => setDialogoEscopo(false)}
        aoSalvar={(nome) => {
          criarEscopo.mutate({ nome })
          setDialogoEscopo(false)
        }}
      />

      <DialogoUnidade
        escopoId={dialogoUnidade}
        aoFechar={() => setDialogoUnidade(null)}
        aoSalvar={(dados) => {
          criarUnidade.mutate(dados)
          setDialogoUnidade(null)
        }}
      />
    </div>
  )
}

function DialogoEscopo({
  aberto,
  aoFechar,
  aoSalvar,
}: {
  aberto: boolean
  aoFechar: () => void
  aoSalvar: (nome: string) => void
}) {
  const [nome, setNome] = useState('')
  return (
    <Dialogo aberto={aberto} aoFechar={aoFechar} titulo="Novo escopo">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (nome.trim()) {
            aoSalvar(nome.trim())
            setNome('')
          }
        }}
        className="space-y-5"
      >
        <Campo rotulo="Nome" dica="Ex.: Centro Paula Souza">
          <Entrada value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />
        </Campo>
        <div className="flex justify-end gap-2">
          <Botao type="button" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" variante="primario">
            Criar
          </Botao>
        </div>
      </form>
    </Dialogo>
  )
}

function DialogoUnidade({
  escopoId,
  aoFechar,
  aoSalvar,
}: {
  escopoId: number | null
  aoFechar: () => void
  aoSalvar: (dados: {
    escopo_id: number
    nome: string
    tipo: TipoUnidade
    cidade: string
  }) => void
}) {
  const [nome, setNome] = useState('')
  const [cidade, setCidade] = useState('')
  const [tipo, setTipo] = useState<TipoUnidade>('FATEC')

  return (
    <Dialogo
      aberto={escopoId !== null}
      aoFechar={aoFechar}
      titulo="Nova unidade"
      descricao="A unidade já nasce com as regras e os modelos de turno padrão do tipo escolhido."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!nome.trim() || escopoId === null) return
          aoSalvar({ escopo_id: escopoId, nome: nome.trim(), tipo, cidade: cidade.trim() })
          setNome('')
          setCidade('')
        }}
        className="space-y-5"
      >
        <Campo rotulo="Nome" dica="Ex.: Fatec Taquaritinga">
          <Entrada value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />
        </Campo>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Tipo">
            <Selecao
              valor={tipo}
              aoMudar={setTipo}
              aria-label="Tipo da unidade"
              opcoes={[
                { valor: 'FATEC', rotulo: 'Fatec (superior tecnológico)' },
                { valor: 'ETEC', rotulo: 'Etec (técnico e médio)' },
              ]}
            />
          </Campo>
          <Campo rotulo="Cidade">
            <Entrada value={cidade} onChange={(e) => setCidade(e.target.value)} />
          </Campo>
        </div>
        <div className="flex justify-end gap-2">
          <Botao type="button" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" variante="primario">
            Criar unidade
          </Botao>
        </div>
      </form>
    </Dialogo>
  )
}
