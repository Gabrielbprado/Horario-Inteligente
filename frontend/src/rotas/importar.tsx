/**
 * Importação de cadastros por CSV ou Excel.
 *
 * O fluxo é conferir e depois gravar: o arquivo sobe, o servidor roda a
 * importação inteira e desfaz, e a tela mostra linha por linha o que seria
 * criado, atualizado ou recusado. Só o segundo clique grava.
 */
import { motion } from 'motion/react'
import {
  CircleCheck,
  CirclePlus,
  Download,
  FileSpreadsheet,
  FileUp,
  OctagonX,
  RefreshCw,
  Upload,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  Botao,
  Cartao,
  Etiqueta,
  LinhasEsqueleto,
  estiloBotao,
} from '@/componentes/ui'
import { urlModeloImportacao, useImportar, useModelosImportacao } from '@/lib/dados'
import type { AcaoImportacao, LinhaImportacao, ModeloImportacao } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const APARENCIA: Record<
  AcaoImportacao,
  { rotulo: string; tom: 'neutro' | 'ok' | 'alerta' | 'erro'; Icone: typeof CirclePlus }
> = {
  criar: { rotulo: 'criar', tom: 'ok', Icone: CirclePlus },
  atualizar: { rotulo: 'atualizar', tom: 'neutro', Icone: RefreshCw },
  ignorar: { rotulo: 'ignorar', tom: 'neutro', Icone: CircleCheck },
  erro: { rotulo: 'erro', tom: 'erro', Icone: OctagonX },
}

export default function Importar() {
  const unidadeId = Number(useParams().unidadeId)
  const qModelos = useModelosImportacao()
  const importar = useImportar(unidadeId)

  const [tipo, setTipo] = useState<string | null>(null)
  const [arquivo, setArquivo] = useState<File | null>(null)
  const entrada = useRef<HTMLInputElement>(null)

  const modelo = qModelos.data?.find((m) => m.tipo === tipo) ?? qModelos.data?.[0]
  const relatorio = importar.data
  const conferido = relatorio !== undefined && !relatorio.aplicado && relatorio.resumo.erro === 0

  const escolher = (novo: string) => {
    setTipo(novo)
    setArquivo(null)
    importar.reset()
  }

  const enviar = (aplicar: boolean) => {
    if (arquivo && modelo) importar.mutate({ tipo: modelo.tipo, arquivo, aplicar })
  }

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Importar cadastros</h1>
        <p className="max-w-2xl text-texto-suave">
          Baixe a planilha de exemplo, preencha e envie. Nada é gravado antes de você conferir o
          que vai mudar.
        </p>
      </header>

      {qModelos.isPending && !qModelos.data ? (
        <LinhasEsqueleto linhas={4} />
      ) : (
        <>
          <nav aria-label="O que importar" className="flex flex-wrap gap-2">
            {(qModelos.data ?? []).map((m) => (
              <button
                key={m.tipo}
                type="button"
                onClick={() => escolher(m.tipo)}
                aria-current={m.tipo === modelo?.tipo ? 'true' : undefined}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-sm transition-colors',
                  m.tipo === modelo?.tipo
                    ? 'border-primaria bg-primaria-suave font-medium text-primaria'
                    : 'border-borda bg-superficie text-texto-suave hover:bg-superficie-2',
                )}
              >
                {m.titulo}
              </button>
            ))}
          </nav>

          {modelo && (
            <div className="grid gap-6 lg:grid-cols-[1fr_22rem] lg:items-start">
              <div className="space-y-4">
                <Cartao className="p-5">
                  <h2 className="font-medium">{modelo.titulo}</h2>
                  <p className="mt-1 text-sm text-texto-suave">{modelo.descricao}</p>

                  <div className="mt-4 flex flex-wrap gap-2">
                    <a
                      href={urlModeloImportacao(modelo.tipo, 'xlsx')}
                      download
                      className={estiloBotao('secundario', 'sm')}
                    >
                      <FileSpreadsheet className="size-3.5" aria-hidden />
                      Planilha de exemplo (Excel)
                    </a>
                    <a
                      href={urlModeloImportacao(modelo.tipo, 'csv')}
                      download
                      className={estiloBotao('secundario', 'sm')}
                    >
                      <Download className="size-3.5" aria-hidden />
                      CSV
                    </a>
                  </div>
                </Cartao>

                <Cartao className="p-5">
                  <h2 className="font-medium">Envie o arquivo</h2>
                  <input
                    ref={entrada}
                    type="file"
                    accept=".csv,.xlsx"
                    aria-label="Arquivo para importar"
                    onChange={(e) => {
                      setArquivo(e.target.files?.[0] ?? null)
                      importar.reset()
                    }}
                    className={cn(
                      'mt-3 w-full cursor-pointer rounded-lg border border-dashed border-borda p-4 text-sm',
                      'file:me-3 file:rounded-md file:border-0 file:bg-superficie-2 file:px-3 file:py-1.5',
                      'file:text-sm file:font-medium hover:bg-superficie-2/40',
                    )}
                  />

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Botao
                      disabled={!arquivo || importar.isPending}
                      onClick={() => enviar(false)}
                    >
                      <FileUp className="size-4" aria-hidden />
                      Conferir sem gravar
                    </Botao>
                    <Botao
                      variante="primario"
                      disabled={!conferido || importar.isPending}
                      title={
                        conferido
                          ? undefined
                          : 'Confira o arquivo primeiro; a importação só grava sem nenhum erro.'
                      }
                      onClick={() => enviar(true)}
                    >
                      <Upload className="size-4" aria-hidden />
                      Gravar no cadastro
                    </Botao>
                  </div>
                </Cartao>

                {relatorio && <Relatorio linhas={relatorio.linhas} aplicado={relatorio.aplicado} resumo={relatorio.resumo} />}
              </div>

              <Colunas modelo={modelo} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Relatorio({
  linhas,
  aplicado,
  resumo,
}: {
  linhas: LinhaImportacao[]
  aplicado: boolean
  resumo: Record<AcaoImportacao, number>
}) {
  const erros = linhas.filter((l) => l.acao === 'erro')
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <Cartao className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-borda p-4">
          <h2 className="font-medium">
            {aplicado ? 'Importado' : erros.length ? 'Ainda não dá para gravar' : 'Conferido'}
          </h2>
          <ul className="flex flex-wrap gap-1.5">
            {(Object.keys(APARENCIA) as AcaoImportacao[])
              .filter((acao) => resumo[acao] > 0)
              .map((acao) => (
                <li key={acao}>
                  <Etiqueta tom={APARENCIA[acao].tom} Icone={APARENCIA[acao].Icone}>
                    {resumo[acao]} {APARENCIA[acao].rotulo}
                  </Etiqueta>
                </li>
              ))}
          </ul>
        </div>

        {!aplicado && erros.length > 0 && (
          <p className="border-b border-borda bg-erro/5 p-3 text-sm text-erro">
            Corrija as {erros.length} linha(s) abaixo e envie de novo: meio cadastro importado é
            pior que nenhum, então nada foi gravado.
          </p>
        )}

        <ul className="max-h-96 divide-y divide-borda overflow-y-auto text-sm">
          {linhas.map((linha) => {
            const { tom, Icone, rotulo } = APARENCIA[linha.acao]
            return (
              <li key={linha.numero} className="flex items-start gap-3 p-3">
                <span className="w-10 shrink-0 text-xs text-texto-suave tabular-nums">
                  {linha.numero}
                </span>
                <Etiqueta tom={tom} Icone={Icone} className="shrink-0">
                  {rotulo}
                </Etiqueta>
                <div className="min-w-0">
                  <p className="truncate">{linha.descricao}</p>
                  {linha.erro && <p className="mt-0.5 text-xs text-erro">{linha.erro}</p>}
                </div>
              </li>
            )
          })}
        </ul>
      </Cartao>
    </motion.div>
  )
}

function Colunas({ modelo }: { modelo: ModeloImportacao }) {
  return (
    <Cartao className="p-5">
      <h2 className="font-medium">Colunas</h2>
      <p className="mt-1 text-xs text-texto-suave">
        A ordem não importa, e acento, caixa e espaço no cabeçalho são ignorados.
      </p>
      <dl className="mt-3 space-y-3">
        {modelo.colunas.map((coluna) => (
          <div key={coluna.nome}>
            <dt className="flex items-center gap-1.5 font-mono text-xs">
              {coluna.nome}
              {coluna.obrigatoria && <Etiqueta tom="alerta">obrigatória</Etiqueta>}
            </dt>
            <dd className="mt-0.5 text-xs text-texto-suave">
              {coluna.ajuda}
              {coluna.exemplo && <span className="ms-1 text-texto-suave">Ex.: {coluna.exemplo}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </Cartao>
  )
}
