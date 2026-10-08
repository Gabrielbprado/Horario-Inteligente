/**
 * Diálogo de exportação da grade em PDF ou Excel.
 *
 * O download é um `<a download>` apontando para a rota: o arquivo vem do
 * servidor com o nome certo no `Content-Disposition`, sem precisar montar um
 * blob em memória.
 */
import { Download, FileSpreadsheet, FileText } from 'lucide-react'
import { useState } from 'react'

import { Campo, Dialogo, Selecao, estiloBotao } from '@/componentes/ui'
import { urlExportacao, useVisao } from '@/lib/dados'
import type { TipoVisao } from '@/lib/tipos'

const CORTES: { valor: TipoVisao; rotulo: string }[] = [
  { valor: 'turma', rotulo: 'Uma página por turma' },
  { valor: 'professor', rotulo: 'Uma página por professor' },
  { valor: 'espaco', rotulo: 'Uma página por sala' },
]

const TODAS = 'todas'

export function DialogoExportar({
  gradeId,
  aberto,
  aoFechar,
}: {
  gradeId: number
  aberto: boolean
  aoFechar: () => void
}) {
  const [tipo, setTipo] = useState<TipoVisao>('turma')
  const [coluna, setColuna] = useState<string>(TODAS)
  const visao = useVisao(gradeId, tipo)

  const colunaId = coluna === TODAS ? undefined : Number(coluna)
  const baixar = (formato: 'pdf' | 'xlsx') =>
    urlExportacao(gradeId, { formato, tipo, colunaId })

  const opcoesColuna = [
    { valor: TODAS, rotulo: 'Todas' },
    ...(visao.data?.colunas ?? []).map((c) => ({ valor: String(c.id), rotulo: c.titulo })),
  ]

  return (
    <Dialogo
      aberto={aberto}
      aoFechar={aoFechar}
      titulo="Exportar a grade"
      descricao="Em paisagem, com as cores das disciplinas e uma página (ou aba) por coluna."
    >
      <div className="space-y-4">
        <Campo rotulo="Como separar">
          <Selecao
            valor={tipo}
            aoMudar={(v) => {
              setTipo(v)
              setColuna(TODAS) // os ids da outra visão não valem aqui
            }}
            opcoes={CORTES}
            aria-label="Como separar"
          />
        </Campo>

        <Campo
          rotulo="Quem entra"
          dica="Escolha uma só para entregar na mão de uma turma ou de um professor."
        >
          <Selecao
            valor={coluna}
            aoMudar={setColuna}
            opcoes={opcoesColuna}
            aria-label="Quem entra"
          />
        </Campo>

        <div className="grid gap-2 sm:grid-cols-2">
          <BotaoBaixar href={baixar('pdf')} Icone={FileText} rotulo="Baixar PDF" primario />
          <BotaoBaixar href={baixar('xlsx')} Icone={FileSpreadsheet} rotulo="Baixar Excel" />
        </div>
      </div>
    </Dialogo>
  )
}

function BotaoBaixar({
  href,
  Icone,
  rotulo,
  primario = false,
}: {
  href: string
  Icone: typeof Download
  rotulo: string
  primario?: boolean
}) {
  return (
    <a
      href={href}
      download
      className={estiloBotao(primario ? 'primario' : 'secundario', 'md', 'justify-center')}
    >
      <Icone className="size-4" aria-hidden />
      {rotulo}
    </a>
  )
}
