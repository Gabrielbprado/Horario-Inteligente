import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { toast } from 'sonner'

import { api, BASE_API, ErroApi, jsonBody } from '@/lib/api'
import { criarRecurso } from '@/lib/recursos'
import type {
  ConfigRegras,
  Curso,
  Disciplina,
  Disponibilidade,
  Escopo,
  Espaco,
  Habilitacao,
  ModeloTurno,
  Oferta,
  PresetTurno,
  Professor,
  StatusDisponibilidade,
  Turma,
  Unidade,
  Vinculo,
  Violacao,
  Classificado,
  ResultadoAtribuicao,
  Grade,
  ParametrosSolver,
  Progresso,
  AvisoGrade,
  TipoVisao,
  VisaoGrade,
  BlocoRef,
  DestinoPossivel,
  RegistroHistorico,
  ResultadoMovimento,
  ComparacaoGrades,
  ModeloImportacao,
  RelatorioImportacao,
} from '@/lib/tipos'

type SemId<T> = Omit<T, 'id'>

export const escopos = criarRecurso<Escopo, SemId<Escopo>>('escopos')
export const unidades = criarRecurso<Unidade, Partial<SemId<Unidade>>>('unidades')
export const cursos = criarRecurso<Curso, SemId<Curso>>('cursos')
export const turmas = criarRecurso<Turma, SemId<Turma>>('turmas')
export const disciplinas = criarRecurso<Disciplina, Partial<SemId<Disciplina>>>('disciplinas')

/** Tamanho do bloco e blocos por dia do curso inteiro: grava em todas as disciplinas. */
export function useAplicarBlocosDoCurso(cursoId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (dados: {
      tamanho_bloco?: number
      max_blocos_por_dia?: number
      concentrar_no_dia?: boolean
    }) =>
      api<Disciplina[]>(`/cursos/${cursoId}/blocos`, { method: 'PUT', body: jsonBody(dados) }),
    onSuccess: (lista) => {
      cliente.invalidateQueries({ queryKey: ['disciplinas'] })
      toast.success(`Blocos aplicados a ${lista.length} disciplina${lista.length === 1 ? '' : 's'}`)
    },
    onError: (erro) =>
      toast.error('Não foi possível aplicar os blocos ao curso', { description: erro.message }),
  })
}
export const espacos = criarRecurso<Espaco, Partial<SemId<Espaco>>>('espacos')
export const professores = criarRecurso<Professor, SemId<Professor>>('professores')
export const vinculos = criarRecurso<Vinculo, Partial<SemId<Vinculo>>>('vinculos')
export const habilitacoes = criarRecurso<Habilitacao, SemId<Habilitacao>>('habilitacoes')
export const atribuicoes = criarRecurso<
  { id: number; professor_id: number; oferta_id: number },
  { professor_id: number; oferta_id: number }
>('atribuicoes')
export const disponibilidades = criarRecurso<Disponibilidade, SemId<Disponibilidade>>(
  'disponibilidades',
)

// ------------------------------------------------------------------ nao-CRUD

export const opcoesModelosTurno = (unidadeId: number) =>
  queryOptions({
    queryKey: ['modelos-turno', { unidade_id: unidadeId }],
    queryFn: () => api<ModeloTurno[]>(`/modelos-turno?unidade_id=${unidadeId}`),
  })

export const useModelosTurno = (unidadeId: number | undefined) =>
  useQuery({ ...opcoesModelosTurno(unidadeId!), enabled: unidadeId !== undefined })

export const usePresetsTurno = (tipo?: string) =>
  useQuery({
    queryKey: ['presets-turno', tipo],
    queryFn: () => api<PresetTurno[]>(`/presets/turno${tipo ? `?tipo=${tipo}` : ''}`),
    staleTime: Infinity, // presets sao constantes do servidor
  })

export const opcoesOfertas = (filtro: { unidade_id?: number; turma_id?: number }) =>
  queryOptions({
    queryKey: ['ofertas', filtro],
    queryFn: () =>
      api<Oferta[]>(
        '/ofertas?' +
          new URLSearchParams(
            Object.entries(filtro)
              .filter(([, v]) => v !== undefined)
              .map(([k, v]) => [k, String(v)]),
          ),
      ),
  })

export const useOfertas = (filtro: { unidade_id?: number; turma_id?: number }) =>
  useQuery(opcoesOfertas(filtro))

/**
 * O que impede esta unidade de gerar uma grade. Roda o mesmo motor de validacao
 * do solver, entao a tela mostra exatamente o que o servidor vai recusar.
 */
export const usePreValidacao = (unidadeId: number | undefined) =>
  useQuery({
    queryKey: ['pre-validacao', unidadeId],
    queryFn: () => api<Violacao[]>(`/unidades/${unidadeId}/pre-validacao`),
    enabled: unidadeId !== undefined,
    staleTime: 10_000,
  })

export const useClassificacao = (unidadeId: number | undefined) =>
  useQuery({
    queryKey: ['classificacao', unidadeId],
    queryFn: () => api<Classificado[]>(`/unidades/${unidadeId}/atribuicao/classificacao`),
    enabled: unidadeId !== undefined,
  })

/**
 * Roda o ato de atribuição da unidade. Não é otimista: o resultado depende de
 * uma regra que só o servidor conhece, e inventar uma previsão aqui poderia
 * mostrar um vencedor diferente do real.
 */
export function useSugerirAtribuicao(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (opcoes: { substituir?: boolean } = {}) =>
      api<ResultadoAtribuicao>(
        `/unidades/${unidadeId}/atribuicao/sugerir?substituir=${opcoes.substituir ?? false}`,
        { method: 'POST' },
      ),
    onSuccess: (resultado) => {
      const bloqueios = resultado.avisos.filter((a) => a.severidade === 'BLOQUEANTE').length
      if (bloqueios) {
        toast.warning(`${resultado.atribuidas} aulas atribuídas`, {
          description: `${bloqueios} oferta(s) ficaram sem professor.`,
        })
      } else {
        toast.success(`${resultado.atribuidas} aulas atribuídas`)
      }
    },
    onError: (erro) =>
      toast.error('Não foi possível sugerir a atribuição', { description: erro.message }),
    onSettled: () => {
      cliente.invalidateQueries({ queryKey: ['ofertas'] })
      cliente.invalidateQueries({ queryKey: ['classificacao', unidadeId] })
      cliente.invalidateQueries({ queryKey: ['pre-validacao', unidadeId] })
      cliente.invalidateQueries({ queryKey: atribuicoes.chaveBase })
    },
  })
}

export function useLimparAtribuicao(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: () => api<void>(`/unidades/${unidadeId}/atribuicao`, { method: 'DELETE' }),
    onMutate: async () => {
      const chaves = [['ofertas'], ['classificacao', unidadeId]]
      await Promise.all(chaves.map((k) => cliente.cancelQueries({ queryKey: k })))
      const anterior = cliente.getQueriesData<Oferta[]>({ queryKey: ['ofertas'] })
      cliente.setQueriesData<Oferta[]>({ queryKey: ['ofertas'] }, (lista) =>
        (lista ?? []).map((o) => ({ ...o, professor_id: null, professor_nome: null })),
      )
      return { anterior }
    },
    onError: (erro, _v, contexto) => {
      contexto?.anterior.forEach(([chave, dados]) => cliente.setQueryData(chave, dados))
      toast.error('Não foi possível limpar a atribuição', { description: erro.message })
    },
    onSettled: () => {
      cliente.invalidateQueries({ queryKey: ['ofertas'] })
      cliente.invalidateQueries({ queryKey: ['classificacao', unidadeId] })
      cliente.invalidateQueries({ queryKey: ['pre-validacao', unidadeId] })
    },
  })
}

// ------------------------------------------------------------------- grades

export const opcoesGrades = (unidadeId: number) =>
  queryOptions({
    queryKey: ['grades', unidadeId],
    queryFn: () => api<Grade[]>(`/grades?unidade_id=${unidadeId}`),
  })

export const useGrades = (unidadeId: number | undefined) =>
  useQuery({ ...opcoesGrades(unidadeId!), enabled: unidadeId !== undefined })

/**
 * Acompanha o solver. Enquanto o job não termina, refaz a consulta a cada 1,2 s
 * — é o que alimenta a pílula de progresso e o desenho ao vivo da grade.
 */
export function useProgresso(gradeId: number | undefined) {
  return useQuery({
    queryKey: ['progresso', gradeId],
    queryFn: () => api<Progresso>(`/grades/${gradeId}/progresso`),
    enabled: gradeId !== undefined,
    refetchInterval: (consulta) => (consulta.state.data?.terminado ? false : 1200),
    staleTime: 0,
    retry: false,
  })
}

export function useGerarGrade(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (params: Partial<ParametrosSolver>) =>
      api<{ grade_id: number; job_id: string }>(`/unidades/${unidadeId}/grades/gerar`, {
        method: 'POST',
        body: jsonBody(params),
      }),
    onError: (erro) => {
      const detalhe = (erro as ErroApi).detalhe as
        | { mensagem?: string; pendencias?: { mensagem: string }[] }
        | undefined
      if (detalhe?.pendencias?.length) {
        toast.error(detalhe.mensagem ?? 'A unidade ainda não pode gerar a grade', {
          description: detalhe.pendencias[0].mensagem,
        })
      } else {
        toast.error('Não foi possível iniciar a geração', { description: erro.message })
      }
    },
    onSettled: () => cliente.invalidateQueries({ queryKey: ['grades', unidadeId] }),
  })
}

export function useApagarGrade(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/grades/${id}`, { method: 'DELETE' }),
    onMutate: async (id) => {
      const chave = opcoesGrades(unidadeId).queryKey
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<Grade[]>(chave)
      cliente.setQueryData<Grade[]>(chave, (l) => (l ?? []).filter((g) => g.id !== id))
      return { anterior }
    },
    onError: (erro, _id, contexto) => {
      cliente.setQueryData(opcoesGrades(unidadeId).queryKey, contexto?.anterior)
      toast.error('Não foi possível excluir a grade', { description: erro.message })
    },
    onSettled: () => cliente.invalidateQueries({ queryKey: ['grades', unidadeId] }),
  })
}

export const opcoesVisao = (gradeId: number, tipo: TipoVisao) =>
  queryOptions({
    queryKey: ['visao', gradeId, tipo],
    queryFn: () => api<VisaoGrade>(`/grades/${gradeId}/visao?tipo=${tipo}`),
  })

export const useVisao = (gradeId: number | undefined, tipo: TipoVisao) =>
  useQuery({ ...opcoesVisao(gradeId!, tipo), enabled: gradeId !== undefined })

export const opcoesAvisos = (gradeId: number) =>
  queryOptions({
    queryKey: ['avisos', gradeId],
    queryFn: () => api<AvisoGrade[]>(`/grades/${gradeId}/avisos`),
  })

export const useAvisos = (gradeId: number | undefined) =>
  useQuery({ ...opcoesAvisos(gradeId!), enabled: gradeId !== undefined })

/** "Estou ciente": some da lista na hora e volta com toast se o servidor recusar. */
export function useDarCiencia(gradeId: number) {
  const cliente = useQueryClient()
  const chave = opcoesAvisos(gradeId).queryKey

  const otimista = (transformar: (l: AvisoGrade[]) => AvisoGrade[]) => async () => {
    await cliente.cancelQueries({ queryKey: chave })
    const anterior = cliente.getQueryData<AvisoGrade[]>(chave)
    cliente.setQueryData<AvisoGrade[]>(chave, (l) => transformar(l ?? []))
    return { anterior }
  }
  const desfazer = (erro: Error, _v: unknown, contexto?: { anterior?: AvisoGrade[] }) => {
    cliente.setQueryData(chave, contexto?.anterior)
    toast.error('Não foi possível registrar a ciência', { description: erro.message })
  }
  const recarregar = () => {
    cliente.invalidateQueries({ queryKey: chave })
    cliente.invalidateQueries({ queryKey: ['grades'] })
  }

  const marcar = (a: AvisoGrade): AvisoGrade => ({
    ...a,
    ciente: true,
    ciente_por: 'você',
    ciente_em: new Date().toISOString(),
  })

  const um = useMutation({
    mutationFn: (id: number) => api<AvisoGrade>(`/avisos/${id}/ciente`, { method: 'POST' }),
    onMutate: (id) => otimista((l) => l.map((a) => (a.id === id ? marcar(a) : a)))(),
    onError: desfazer,
    onSettled: recarregar,
  })

  const todos = useMutation({
    mutationFn: () =>
      api<AvisoGrade[]>(`/grades/${gradeId}/avisos/ciente-todos`, { method: 'POST' }),
    onMutate: otimista((l) => l.map((a) => (a.severidade === 'ALERTA' ? marcar(a) : a))),
    onError: desfazer,
    onSettled: recarregar,
  })

  return { um, todos }
}

/** Publica. Otimista: o selo muda na hora — o botão só fica habilitado quando
 *  não há pendência, então a recusa do servidor é a exceção, não a regra. */
export function usePublicar(gradeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: () => api<Grade>(`/grades/${gradeId}/publicar`, { method: 'POST' }),
    onMutate: async () => {
      const chaves = cliente
        .getQueryCache()
        .findAll({ queryKey: ['grades'] })
        .map((q) => q.queryKey)
      await Promise.all(chaves.map((chave) => cliente.cancelQueries({ queryKey: chave })))
      const anterior = chaves.map((chave) => [chave, cliente.getQueryData(chave)] as const)
      for (const chave of chaves) {
        cliente.setQueryData<Grade[]>(chave, (lista) =>
          (lista ?? []).map((g) => (g.id === gradeId ? { ...g, status: 'PUBLICADA' } : g)),
        )
      }
      return { anterior }
    },
    onError: (erro, _v, contexto) => {
      for (const [chave, dados] of contexto?.anterior ?? []) cliente.setQueryData(chave, dados)
      const detalhe = (erro as ErroApi).detalhe as
        | { mensagem?: string; motivos?: string[] }
        | undefined
      toast.error(detalhe?.mensagem ?? 'Não foi possível publicar', {
        description: detalhe?.motivos?.join(' '),
      })
    },
    onSuccess: () => toast.success('Grade publicada'),
    onSettled: () => {
      cliente.invalidateQueries({ queryKey: ['grades'] })
      cliente.invalidateQueries({ queryKey: opcoesAvisos(gradeId).queryKey })
    },
  })
}

// -------------------------------------------------------------- edicao manual

/**
 * Onde este bloco pode cair, com a severidade de cada destino.
 *
 * Uma requisição por arrasto, não uma por célula sobrevoada: a tela recebe a
 * semana inteira já avaliada e pinta verde/amarelo/vermelho na hora.
 */
export function useDestinos(gradeId: number, bloco: BlocoRef | null) {
  return useQuery({
    queryKey: ['destinos', gradeId, bloco?.oferta_id, bloco?.bloco_idx],
    queryFn: () =>
      api<DestinoPossivel[]>(
        `/grades/${gradeId}/destinos?oferta_id=${bloco!.oferta_id}&bloco_idx=${bloco!.bloco_idx}`,
      ),
    enabled: bloco !== null,
    staleTime: 0,
  })
}

function invalidarGrade(cliente: QueryClient, gradeId: number) {
  cliente.invalidateQueries({ queryKey: ['visao', gradeId] })
  cliente.invalidateQueries({ queryKey: ['avisos', gradeId] })
  cliente.invalidateQueries({ queryKey: ['historico', gradeId] })
  cliente.invalidateQueries({ queryKey: ['destinos', gradeId] })
  cliente.invalidateQueries({ queryKey: ['grades'] })
}

/** Move o bloco. Otimista: a aula muda de lugar na hora e volta se o servidor recusar. */
export function useMoverBloco(gradeId: number, tipo: TipoVisao) {
  const cliente = useQueryClient()
  const chave = opcoesVisao(gradeId, tipo).queryKey

  return useMutation({
    mutationFn: (
      dados: BlocoRef & { slot_inicial: number; espaco_id?: number; forcar?: boolean },
    ) =>
      api<ResultadoMovimento>(`/grades/${gradeId}/aplicar-movimento`, {
        method: 'POST',
        body: jsonBody(dados),
      }),
    onMutate: async ({ oferta_id, bloco_idx, slot_inicial }) => {
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<VisaoGrade>(chave)
      if (!anterior) return { anterior }

      const doBloco = anterior.celulas
        .filter((c) => c.oferta_id === oferta_id && c.bloco_idx === bloco_idx)
        .sort((a, b) => a.ordem - b.ordem)
      const alvo = anterior.slots.find((x) => x.id === slot_inicial)
      if (!doBloco.length || !alvo) return { anterior }

      // As aulas geminadas caem em horários seguidos do mesmo turno.
      const doTurno = anterior.slots
        .filter((x) => x.modelo_turno_id === alvo.modelo_turno_id)
        .sort((a, b) => a.dia - b.dia || a.ordem - b.ordem)
      const inicio = doTurno.findIndex((x) => x.id === alvo.id)
      const destinos = doTurno.slice(inicio, inicio + doBloco.length)
      if (destinos.length < doBloco.length) return { anterior }

      const movidos = new Map(
        doBloco.map((c, i) => [
          c.alocacao_id,
          {
            ...c,
            slot_id: destinos[i].id,
            dia: destinos[i].dia,
            ordem: destinos[i].ordem,
            inicio: destinos[i].inicio,
            fim: destinos[i].fim,
          },
        ]),
      )
      cliente.setQueryData<VisaoGrade>(chave, {
        ...anterior,
        celulas: anterior.celulas.map((c) => movidos.get(c.alocacao_id) ?? c),
      })
      return { anterior }
    },
    onError: (erro, _dados, contexto) => {
      cliente.setQueryData(chave, contexto?.anterior)
      const detalhe = (erro as ErroApi).detalhe as
        | { mensagem?: string; motivos?: string[] }
        | undefined
      toast.error(detalhe?.mensagem ?? 'Não foi possível mover a aula', {
        description: detalhe?.motivos?.[0] ?? erro.message,
      })
    },
    onSuccess: (resultado) => {
      if (resultado.severidade === 'ALERTA') {
        toast.warning('Aula movida com alerta', {
          description: resultado.violacoes[0]?.mensagem,
        })
      }
    },
    onSettled: () => invalidarGrade(cliente, gradeId),
  })
}

export function useFixarBloco(gradeId: number, tipo: TipoVisao) {
  const cliente = useQueryClient()
  const chave = opcoesVisao(gradeId, tipo).queryKey

  return useMutation({
    mutationFn: (dados: BlocoRef & { fixada: boolean }) =>
      api<ResultadoMovimento>(`/grades/${gradeId}/fixar`, {
        method: 'POST',
        body: jsonBody(dados),
      }),
    onMutate: async ({ oferta_id, bloco_idx, fixada }) => {
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<VisaoGrade>(chave)
      cliente.setQueryData<VisaoGrade>(chave, (v) =>
        v
          ? {
              ...v,
              celulas: v.celulas.map((c) =>
                c.oferta_id === oferta_id && c.bloco_idx === bloco_idx ? { ...c, fixada } : c,
              ),
            }
          : v,
      )
      return { anterior }
    },
    onError: (erro, _dados, contexto) => {
      cliente.setQueryData(chave, contexto?.anterior)
      toast.error('Não foi possível fixar a aula', { description: erro.message })
    },
    onSettled: () => invalidarGrade(cliente, gradeId),
  })
}

export const useHistorico = (gradeId: number | undefined) =>
  useQuery({
    queryKey: ['historico', gradeId],
    queryFn: () => api<RegistroHistorico[]>(`/grades/${gradeId}/historico`),
    enabled: gradeId !== undefined,
  })

/**
 * Desfaz os ultimos passos. Otimista no historico: os registros ja aparecem
 * riscados. A grade em si nao da' para prever sem refazer a conta do servidor,
 * entao ela e' recarregada — o historico e' a confirmacao visual imediata.
 */
export function useDesfazer(gradeId: number) {
  const cliente = useQueryClient()
  const chave = ['historico', gradeId]

  return useMutation({
    mutationFn: (passos: number = 1) =>
      api<string[]>(`/grades/${gradeId}/desfazer?passos=${passos}`, { method: 'POST' }),
    onMutate: async (passos = 1) => {
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<RegistroHistorico[]>(chave)
      cliente.setQueryData<RegistroHistorico[]>(chave, (lista) => {
        if (!lista) return lista
        let restantes = passos
        // O historico vem do mais recente para o mais antigo.
        return lista.map((r) =>
          !r.desfeito && restantes-- > 0 ? { ...r, desfeito: true } : r,
        )
      })
      return { anterior }
    },
    onSuccess: (desfeitos) =>
      toast.success('Desfeito', { description: desfeitos.join('; ') }),
    onError: (erro, _v, contexto) => {
      cliente.setQueryData(chave, contexto?.anterior)
      toast.error('Nada para desfazer', { description: erro.message })
    },
    onSettled: () => invalidarGrade(cliente, gradeId),
  })
}

export const opcoesConfigRegras = (unidadeId: number) =>
  queryOptions({
    queryKey: ['config-regras', unidadeId],
    queryFn: () => api<ConfigRegras>(`/unidades/${unidadeId}/config-regras`),
  })

export const useConfigRegras = (unidadeId: number | undefined) =>
  useQuery({ ...opcoesConfigRegras(unidadeId!), enabled: unidadeId !== undefined })

export function useGravarConfigRegras(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (regras: ConfigRegras) =>
      api<ConfigRegras>(`/unidades/${unidadeId}/config-regras`, {
        method: 'PUT',
        body: jsonBody(regras),
      }),
    onMutate: async (regras) => {
      const chave = ['config-regras', unidadeId]
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<ConfigRegras>(chave)
      cliente.setQueryData(chave, regras)
      return { anterior }
    },
    onError: (erro, _regras, contexto) => {
      cliente.setQueryData(['config-regras', unidadeId], contexto?.anterior)
      toast.error('Não foi possível salvar as regras', { description: erro.message })
    },
    onSuccess: () => toast.success('Regras da unidade salvas'),
    onSettled: () => {
      cliente.invalidateQueries({ queryKey: ['config-regras', unidadeId] })
      cliente.invalidateQueries({ queryKey: ['unidades'] })
    },
  })
}

export function useSubstituirModeloTurno(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (modelo: ModeloTurno) =>
      api<ModeloTurno>(`/modelos-turno/${modelo.id}`, {
        method: 'PUT',
        body: jsonBody({
          unidade_id: modelo.unidade_id,
          nome: modelo.nome,
          preset_origem: modelo.preset_origem,
          slots: modelo.slots.map(({ dia_semana, ordem, inicio, fim, bloco_id }) => ({
            dia_semana,
            ordem,
            inicio,
            fim,
            bloco_id,
          })),
        }),
      }),
    onMutate: async (modelo) => {
      const chave = opcoesModelosTurno(unidadeId).queryKey
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<ModeloTurno[]>(chave)
      cliente.setQueryData<ModeloTurno[]>(chave, (lista) =>
        (lista ?? []).map((mt) => (mt.id === modelo.id ? modelo : mt)),
      )
      return { anterior }
    },
    onError: (erro, _modelo, contexto) => {
      cliente.setQueryData(opcoesModelosTurno(unidadeId).queryKey, contexto?.anterior)
      toast.error('Não foi possível salvar o turno', { description: erro.message })
    },
    onSuccess: () => toast.success('Modelo de turno salvo'),
    onSettled: () =>
      cliente.invalidateQueries({ queryKey: opcoesModelosTurno(unidadeId).queryKey }),
  })
}

/** Marcacao em massa na grade de disponibilidade (uma noite, um dia inteiro). */
export function useDisponibilidadeEmLote(professorId: number, unidadeId: number) {
  const cliente = useQueryClient()
  const chave = disponibilidades.chave({ professor_id: professorId })

  return useMutation({
    mutationFn: (dados: { slot_ids: number[]; status: StatusDisponibilidade }) =>
      api<Disponibilidade[]>('/disponibilidades/lote', {
        method: 'PUT',
        body: jsonBody({ professor_id: professorId, unidade_id: unidadeId, ...dados }),
      }),
    onMutate: async ({ slot_ids, status }) => {
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<Disponibilidade[]>(chave)
      cliente.setQueryData<Disponibilidade[]>(chave, (lista) => {
        const restantes = (lista ?? []).filter((d) => !slot_ids.includes(d.slot_id))
        if (status === 'DISPONIVEL') return restantes
        return [
          ...restantes,
          ...slot_ids.map((slot_id, i) => ({
            id: -1_000_000 - i,
            professor_id: professorId,
            unidade_id: unidadeId,
            slot_id,
            status,
          })),
        ]
      })
      return { anterior }
    },
    onError: (erro, _dados, contexto) => {
      cliente.setQueryData(chave, contexto?.anterior)
      toast.error('Não foi possível salvar a disponibilidade', { description: erro.message })
    },
    onSettled: () => cliente.invalidateQueries({ queryKey: disponibilidades.chaveBase }),
  })
}

/** Atribuir/desatribuir professor a uma oferta, refletindo na lista de ofertas. */
export function useAtribuirProfessor(filtro: { unidade_id?: number; turma_id?: number }) {
  const cliente = useQueryClient()
  const chave = opcoesOfertas(filtro).queryKey

  return useMutation({
    mutationFn: async (dados: {
      oferta_id: number
      professor_id: number | null
      atribuicao_id: number | null
    }) => {
      if (dados.atribuicao_id !== null) {
        await api<void>(`/atribuicoes/${dados.atribuicao_id}`, { method: 'DELETE' })
      }
      if (dados.professor_id === null) return
      await api('/atribuicoes', {
        method: 'POST',
        body: jsonBody({ oferta_id: dados.oferta_id, professor_id: dados.professor_id }),
      })
    },
    onMutate: async ({ oferta_id, professor_id }) => {
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<Oferta[]>(chave)
      cliente.setQueryData<Oferta[]>(chave, (lista) =>
        (lista ?? []).map((o) => (o.id === oferta_id ? { ...o, professor_id } : o)),
      )
      return { anterior }
    },
    onError: (erro, _dados, contexto) => {
      cliente.setQueryData(chave, contexto?.anterior)
      toast.error('Não foi possível atribuir a aula', { description: erro.message })
    },
    onSettled: () => {
      cliente.invalidateQueries({ queryKey: ['ofertas'] })
      cliente.invalidateQueries({ queryKey: atribuicoes.chaveBase })
    },
  })
}

// ----------------------------------------------------- exportar, versoes, importar

/** URL de download: o navegador baixa direto, sem passar pelo `fetch`. */
export function urlExportacao(
  gradeId: number,
  opcoes: { formato: 'pdf' | 'xlsx'; tipo: TipoVisao; colunaId?: number },
) {
  const busca = new URLSearchParams({ formato: opcoes.formato, tipo: opcoes.tipo })
  if (opcoes.colunaId !== undefined) busca.set('coluna_id', String(opcoes.colunaId))
  return `${BASE_API}/grades/${gradeId}/exportar?${busca}`
}

export const urlModeloImportacao = (tipo: string, formato: 'csv' | 'xlsx') =>
  `${BASE_API}/importar/modelos/${tipo}/arquivo?formato=${formato}`

export function useDuplicarGrade(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (dados: { gradeId: number; nome?: string }) =>
      api<Grade>(`/grades/${dados.gradeId}/duplicar`, {
        method: 'POST',
        body: jsonBody({ nome: dados.nome ?? null }),
      }),
    // Otimista: o cartao da copia aparece na hora, marcado como provisorio ate
    // o servidor devolver o id e o nome definitivos.
    onMutate: async ({ gradeId, nome }) => {
      const chave = opcoesGrades(unidadeId).queryKey
      await cliente.cancelQueries({ queryKey: chave })
      const anterior = cliente.getQueryData<Grade[]>(chave)
      const origem = anterior?.find((g) => g.id === gradeId)
      if (origem) {
        const copia: Grade = {
          ...origem,
          // Id negativo: a convencao de `ehProvisorio`, usada em todos os
          // cadastros otimistas.
          id: -Date.now(),
          nome: nome ?? `${origem.nome} (cópia)`,
          status: 'RASCUNHO',
          criada_em: new Date().toISOString(),
        }
        cliente.setQueryData<Grade[]>(chave, [copia, ...(anterior ?? [])])
      }
      return { anterior }
    },
    onError: (erro, _v, contexto) => {
      cliente.setQueryData(opcoesGrades(unidadeId).queryKey, contexto?.anterior)
      toast.error('Não foi possível duplicar', { description: erro.message })
    },
    onSuccess: (grade) => {
      cliente.invalidateQueries({ queryKey: opcoesGrades(unidadeId).queryKey })
      toast.success('Versão criada', {
        description: `${grade.nome} tem as mesmas aulas e pode ser mexida à vontade.`,
      })
    },
  })
}

export const useComparacao = (primeira: number | null, segunda: number | null) =>
  useQuery({
    queryKey: ['comparacao', primeira, segunda],
    queryFn: () => api<ComparacaoGrades>(`/grades/${primeira}/comparar?com=${segunda}`),
    enabled: primeira !== null && segunda !== null && primeira !== segunda,
    staleTime: 10_000,
  })

export const opcoesModelosImportacao = () =>
  queryOptions({
    queryKey: ['modelos-importacao'],
    queryFn: () => api<ModeloImportacao[]>('/importar/modelos'),
    staleTime: Infinity, // os modelos sao codigo, nao dado
  })

export const useModelosImportacao = () => useQuery(opcoesModelosImportacao())

export function useImportar(unidadeId: number) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: async (dados: { tipo: string; arquivo: File; aplicar: boolean }) => {
      const corpo = new FormData()
      corpo.append('arquivo', dados.arquivo)
      const busca = new URLSearchParams({
        unidade_id: String(unidadeId),
        tipo: dados.tipo,
        aplicar: String(dados.aplicar),
      })
      // Sem `Content-Type`: o navegador precisa escrever o boundary do multipart.
      const resposta = await fetch(`${BASE_API}/importar/csv?${busca}`, {
        method: 'POST',
        body: corpo,
      })
      const conteudo = await resposta.json().catch(() => null)
      if (!resposta.ok) {
        const detalhe = conteudo?.detail
        throw new Error(
          typeof detalhe === 'string' ? detalhe : `Falha na importação (${resposta.status})`,
        )
      }
      return conteudo as RelatorioImportacao
    },
    onSuccess: (relatorio) => {
      if (!relatorio.aplicado) return
      // Importar mexe em quase todo cadastro; invalidar tudo é mais barato que
      // esquecer uma tela e mostrar dado velho.
      cliente.invalidateQueries()
      toast.success('Cadastro importado', {
        description: `${relatorio.resumo.criar} criado(s), ${relatorio.resumo.atualizar} atualizado(s).`,
      })
    },
    onError: (erro) => toast.error('Não foi possível importar', { description: erro.message }),
  })
}
