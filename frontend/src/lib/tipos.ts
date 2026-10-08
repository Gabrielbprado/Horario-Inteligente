/** Espelha `app/schemas.py`. Mantido a mao: sao poucos tipos e um gerador de
 *  OpenAPI traria uma etapa de build so para isso. */

export type TipoUnidade = 'FATEC' | 'ETEC'
export type ModalidadeCurso = 'CST' | 'TECNICO_MODULAR' | 'ETIM' | 'MTEC'
export type ModalidadeAula = 'PRESENCIAL' | 'REMOTA'
export type ModoDivisao = 'PARALELA' | 'SEQUENCIAL' | 'INDIFERENTE'
export type TipoEspaco = 'SALA' | 'LABORATORIO'
export type TipoContrato = 'INDETERMINADO' | 'DETERMINADO'
export type OrigemHabilitacao = 'CONCURSO' | 'ANTERIOR' | 'HABILITADO'
export type StatusDisponibilidade = 'DISPONIVEL' | 'PREFERENCIAL' | 'INDISPONIVEL'

export type Escopo = { id: number; nome: string }

export type Unidade = {
  id: number
  escopo_id: number
  nome: string
  tipo: TipoUnidade
  cidade: string | null
  carga_max_semanal_padrao: number
  config_regras: ConfigRegras
}

export type Slot = {
  id: number
  modelo_turno_id: number
  dia_semana: number
  ordem: number
  /** "HH:MM:SS" */
  inicio: string
  fim: string
  bloco_id: number
}

export type SlotEntrada = Omit<Slot, 'id' | 'modelo_turno_id'>

export type ModeloTurno = {
  id: number
  unidade_id: number
  nome: string
  dias_semana: number[]
  preset_origem: string | null
  slots: Slot[]
}

export type PresetTurno = {
  chave: string
  nome: string
  dias_semana: number[]
  aulas_por_dia: Record<string, number>
}

export type Curso = {
  id: number
  unidade_id: number
  nome: string
  sigla: string
  modalidade: ModalidadeCurso
}

export type Turma = {
  id: number
  curso_id: number
  periodo: string
  turno: string
  modelo_turno_id: number
  qtd_alunos: number
}

export type Disciplina = {
  id: number
  curso_id: number
  periodo: string
  nome: string
  sigla: string
  aulas_semanais: number
  tamanho_bloco: number
  modalidade: ModalidadeAula
  precisa_laboratorio: boolean
  tipo_laboratorio: string | null
  divisao_turma: boolean
  modo_divisao: ModoDivisao
  max_blocos_por_dia: number
  concentrar_no_dia: boolean
}

export type Espaco = {
  id: number
  unidade_id: number
  nome: string
  tipo: TipoEspaco
  tipo_laboratorio: string | null
  capacidade: number
}

export type Oferta = {
  id: number
  turma_id: number
  disciplina_id: number
  subturma: string | null
  disciplina_nome: string
  disciplina_sigla: string
  aulas_semanais: number
  turma_periodo: string
  curso_sigla: string
  professor_id: number | null
  professor_nome: string | null
}

export type Professor = {
  id: number
  escopo_id: number
  nome: string
  identificador: string
  email: string | null
}

export type Vinculo = {
  id: number
  professor_id: number
  unidade_id: number
  tipo_contrato: TipoContrato
  pontuacao: number
  pont_assiduidade: number
  pont_titulacao: number
  tempo_exercicio_meses: number
  num_filhos: number
  carga_max_semanal: number | null
}

export type Habilitacao = {
  id: number
  professor_id: number
  disciplina_id: number
  origem: OrigemHabilitacao
}

export type Disponibilidade = {
  id: number
  professor_id: number
  unidade_id: number
  slot_id: number
  status: StatusDisponibilidade
}

export type ConfigRegras = {
  carga_max_semanal: number
  limite_diario: { ativo: boolean; max_consecutivas: number; max_intercaladas: number }
  interjornada: { modo: 'off' | 'aviso' | 'rigida'; horas: number }
  deslocamento_entre_unidades_min: number
  usa_sabado: boolean
  atribuicao: { regra: TipoUnidade; desempates: string[] }
  pesos: {
    nao_concentradas: number
    janela_turma: number
    janela_professor: number
    preferencia: number
    dias_professor: number
    estabilidade: number
    dia_curto_no_fim: number
  }
  modo_objetivo: 'ponderado' | 'lexicografico'
}

export type Severidade = 'INFO' | 'ALERTA' | 'BLOQUEANTE'

/** Saida do validador unico e da pre-validacao. */
export type Violacao = {
  tipo: string
  severidade: Severidade
  mensagem: string
  entidades: Record<string, unknown>
}

export type Classificado = {
  posicao: number
  professor_id: number
  professor_nome: string
  tipo_contrato: TipoContrato
  pontuacao: number
  pont_assiduidade: number
  pont_titulacao: number
  tempo_exercicio_meses: number
  num_filhos: number
  carga_max: number
  aulas_atribuidas: number
}

export type ResultadoAtribuicao = {
  atribuidas: number
  preservadas: number
  sem_professor: number[]
  avisos: Violacao[]
  classificacao: Classificado[]
}

export type StatusGrade = 'RASCUNHO' | 'AGUARDANDO_CIENCIA' | 'PUBLICADA'

export type Grade = {
  id: number
  unidade_id: number
  nome: string
  status: StatusGrade
  criada_em: string
  parametros_solver: Record<string, unknown>
  score: Record<string, number | null>
}

export type ParametrosSolver = {
  nome?: string | null
  tempo_limite_s: number
  workers: number
  semente: number
  manter_fixadas: boolean
  modo_objetivo?: 'ponderado' | 'lexicografico' | null
  partir_de?: number | null
  resolver_avisos?: boolean
}

export type AlocacaoParcial = {
  oferta_id: number
  professor_id: number
  slot_id: number
  espaco_id: number | null
  bloco_idx: number
}

export type Diagnostico = {
  mensagem?: string
  culpados?: { tipo: string; id?: number; nome: string }[]
  acoes?: { chave: string; descricao: string }[]
}

export type Progresso = {
  job_id: string
  grade_id: number
  status: string
  terminado: boolean
  solucoes: number
  objetivo: number | null
  limite_inferior: number | null
  tempo_s: number
  mensagem: string | null
  diagnostico: Diagnostico | null
  metricas: Record<string, number>
  alocacoes: AlocacaoParcial[]
}

export type TipoVisao = 'turma' | 'professor' | 'espaco'

export type CelulaGrade = {
  alocacao_id: number
  oferta_id: number
  disciplina_id: number
  disciplina_sigla: string
  disciplina_nome: string
  turma_id: number
  turma_rotulo: string
  subturma: string | null
  professor_id: number
  professor_nome: string
  espaco_id: number | null
  espaco_nome: string | null
  slot_id: number
  modelo_turno_id: number
  dia: number
  ordem: number
  inicio: string
  fim: string
  bloco_id: number
  bloco_idx: number
  remota: boolean
  precisa_laboratorio: boolean
  fixada: boolean
}

export type ColunaVisao = {
  id: number
  titulo: string
  subtitulo: string | null
  tipo: string | null
  modelo_turno_id: number | null
}
export type LinhaHorario = { dia: number; inicio: string; fim: string; ordens: number[] }

export type SlotRef = {
  id: number
  modelo_turno_id: number
  dia: number
  ordem: number
  inicio: string
  fim: string
  bloco_id: number
}

export type VisaoGrade = {
  grade_id: number
  tipo: TipoVisao
  colunas: ColunaVisao[]
  horarios: LinhaHorario[]
  slots: SlotRef[]
  celulas: CelulaGrade[]
}

export type AvisoGrade = {
  id: number
  grade_id: number
  tipo: string
  severidade: Severidade
  mensagem: string
  entidades: Record<string, unknown>
  ciente: boolean
  ciente_por: string | null
  ciente_em: string | null
}

export type BlocoRef = { oferta_id: number; bloco_idx: number }

export type DestinoPossivel = {
  slot_id: number
  severidade: Severidade | null
  motivos: string[]
}

export type ResultadoMovimento = {
  permitido: boolean
  severidade: Severidade | null
  descricao: string
  alteracoes: { alocacao_id: number; antes: Record<string, unknown>; depois: Record<string, unknown> }[]
  violacoes: Violacao[]
  aplicado: boolean
}

export type RegistroHistorico = {
  id: number
  origem: 'MANUAL' | 'CHAT' | 'SOLVER'
  autor: string | null
  timestamp: string
  descricao: string
  desfeito: boolean
}

export type MudancaProposta = { rotulo: string; antes: string; depois: string }

export type Proposta = {
  id: string
  grade_id: number
  tipo: string
  descricao: string
  permitido: boolean
  aplicada: boolean
  descartada: boolean
  mudancas: MudancaProposta[]
  violacoes: Violacao[]
}

export type MensagemChat = {
  id: string
  papel: 'user' | 'assistant'
  texto: string
  /** Propostas que esta resposta produziu. */
  propostas?: Proposta[]
  ferramentas?: string[]
  erro?: string
}

// ------------------------------------------------------------------- versoes

export type TipoDiferenca =
  | 'igual'
  | 'horario'
  | 'espaco'
  | 'professor'
  | 'removida'
  | 'adicionada'

export type DiferencaGrade = {
  tipo: TipoDiferenca
  rotulo_tipo: string
  oferta_id: number
  bloco_idx: number
  rotulo: string
  antes: string | null
  depois: string | null
}

export type MetricaComparada = {
  nome: string
  primeira: number | null
  segunda: number | null
}

export type ComparacaoGrades = {
  primeira: Grade
  segunda: Grade
  resumo: Record<TipoDiferenca, number>
  metricas: MetricaComparada[]
  diferencas: DiferencaGrade[]
}

// ----------------------------------------------------------------- importacao

export type ColunaModelo = {
  nome: string
  ajuda: string
  exemplo: string
  obrigatoria: boolean
}

export type ModeloImportacao = {
  tipo: string
  titulo: string
  descricao: string
  colunas: ColunaModelo[]
}

export type AcaoImportacao = 'criar' | 'atualizar' | 'ignorar' | 'erro'

export type LinhaImportacao = {
  numero: number
  acao: AcaoImportacao
  descricao: string
  erro: string | null
}

export type RelatorioImportacao = {
  tipo: string
  aplicado: boolean
  total: number
  resumo: Record<AcaoImportacao, number>
  linhas: LinhaImportacao[]
}

/** Entidade recem-criada de forma otimista, ainda sem id do servidor. */
export type Provisorio<T> = T & { _provisorio?: boolean }

export const DIAS_CURTOS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'] as const
export const DIAS_LONGOS = [
  'Segunda',
  'Terça',
  'Quarta',
  'Quinta',
  'Sexta',
  'Sábado',
  'Domingo',
] as const

/** "19:00:00" -> "19:00" */
export const hhmm = (hora: string) => hora.slice(0, 5)
