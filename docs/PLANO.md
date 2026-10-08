# PLANO — Horário Inteligente (CPS: Fatecs e Etecs)

Documento de arquitetura, modelo de dados e formulação matemática do solver.
Escrito antes da implementação, conforme item 0.1 da especificação.

---

## 1. Visão geral

Sistema web que monta grades de horário de professores para unidades do Centro Paula
Souza, com três formas de alterar a grade — **solver**, **edição manual** e **chatbot** —
todas passando pelo **mesmo motor de validação**.

```
                      ┌──────────────────────────────────────────┐
                      │            Frontend (React)              │
                      │  cadastros · grade · avisos · chat        │
                      └───────────────┬──────────────────────────┘
                                      │ REST + SSE
                      ┌───────────────▼──────────────────────────┐
                      │              FastAPI                      │
                      │  routers · schemas · jobs em background   │
                      └───┬──────────────┬───────────────┬────────┘
                          │              │               │
              ┌───────────▼───┐  ┌───────▼────────┐  ┌───▼──────────────┐
              │ scheduling/   │  │ scheduling/    │  │ chat/            │
              │ solver.py     │  │ validator.py   │  │ tools.py         │
              │ (CP-SAT)      │  │ (fonte única)  │  │ (function calls) │
              └───────┬───────┘  └───────▲────────┘  └───┬──────────────┘
                      │                  │               │
                      └──────────────────┴───────────────┘
                                      │
                      ┌───────────────▼──────────────────────────┐
                      │   SQLAlchemy 2 · PostgreSQL / SQLite      │
                      └──────────────────────────────────────────┘
```

**Invariante central:** nenhuma escrita em `Alocacao` acontece fora de
`app/scheduling/apply.py`, que sempre chama `validator.validar()` antes de gravar e
registra `HistoricoAlteracao`. O LLM nunca toca no banco — ele chama ferramentas HTTP
internas que passam pelo mesmo caminho.

---

## 2. Estrutura de pastas

```
backend/
  app/
    main.py              app factory, CORS, routers
    config.py            settings (pydantic-settings): DATABASE_URL, OPENAI_*
    db.py                engine, SessionLocal, get_db
    models.py            todas as entidades SQLAlchemy 2 (mapped_column)
    schemas.py           Pydantic v2 (entrada/saída)
    presets.py           presets FATEC/ETEC: config_regras + modelos de turno
    crud.py              fábrica de routers CRUD genéricos
    api/
      cadastros.py       CRUD de escopo..disponibilidade (via crud.py)
      grades.py          gerar, progresso, visões, mover, publicar
      avisos.py          listar, ciência
      atribuicao.py      sugerir atribuição
      importar.py        CSV/Excel
      exportar.py        PDF/XLSX
      chat.py            SSE
    scheduling/
      domain.py          dataclasses puras (GradeState, SlotInfo, BlocoInfo, Config)
      loader.py          DB -> GradeState (inclui outras unidades do escopo)
      validator.py       validar(state, config) -> list[Violacao]   ← FONTE ÚNICA
      prevalidate.py     checagens de inviabilidade antes do solver
      assignment.py      atribuição sugerida (Etec/Fatec) + desempates
      solver.py          modelo CP-SAT
      diagnose.py        explicação de INFEASIBLE
      jobs.py            execução assíncrona + progresso
      apply.py           aplicar movimento/troca/fixar + histórico + desfazer
    chat/
      tools.py           definições JSON Schema + implementações
      service.py         loop de ferramentas com a Responses API
    export/
      pdf.py  xlsx.py
  scripts/seed.py
  tests/
frontend/            React + Vite + TS
docs/                PLANO.md  DECISOES.md
```

---

## 3. Modelo de dados

Segue a seção 3 da especificação. Notas de implementação:

### 3.1 Chaves e tipos
- PKs `int` autoincrement (SQLite e Postgres, sem extensão).
- Horários (`Slot.inicio/fim`) como `time`. Para a interjornada é necessário
  comparar entre dias: converte-se para minutos desde a meia-noite do dia,
  e aulas que terminam depois da meia-noite não existem nos presets do CPS
  (o mais tarde é 23h00), então não há wrap-around.
- `config_regras`, `parametros_solver`, `score`, `diff`, `entidades` são `JSON`
  (`sqlalchemy.JSON`, portável entre SQLite e Postgres).

### 3.2 Hierarquia de slot
`ModeloTurno` → `Slot(dia_semana, ordem, inicio, fim, bloco_id)`.

`bloco_id` é um inteiro que agrupa slots **contíguos sem intervalo entre eles, no
mesmo dia**. Dois slots só podem formar uma aula geminada se tiverem o mesmo
`(dia_semana, bloco_id)` e `ordem` consecutiva. Isso resolve a regra "bloco não
atravessa intervalo" sem precisar comparar horários.

Exemplo — preset Fatec noturno, segunda-feira:

| ordem | inicio | fim   | bloco_id |
|-------|--------|-------|----------|
| 1     | 19:00  | 19:50 | 1        |
| 2     | 19:50  | 20:40 | 1        |
| 3     | 20:50  | 21:40 | 2        |
| 4     | 21:40  | 22:30 | 2        |

(o intervalo 20:40–20:50 não é um slot; ele existe implicitamente como a mudança
de `bloco_id`.)

### 3.3 Oferta e subturma
`Oferta(turma_id, disciplina_id, subturma)`.
- Disciplina sem divisão → 1 oferta, `subturma = NULL`.
- Disciplina com divisão → 2 ofertas, `subturma = "A"` e `"B"`.

As ofertas são materializadas no banco (não calculadas em tempo de execução) porque
`Atribuicao` e `Alocacao` apontam para elas. Um serviço `sincronizar_ofertas(turma)`
recria as ofertas quando a matriz da turma muda.

### 3.4 Professor no escopo, vínculo na unidade
`Professor` pertence ao **escopo**; `VinculoUnidade` liga professor↔unidade e carrega
pontuação, subpontuações de desempate e carga máxima. Isso permite detectar choque
entre Fatec e Etec da mesma cidade.

### 3.5 Grade
`Grade` é uma versão. `Alocacao` é a linha de horário:
`(grade_id, oferta_id, professor_id, slot_id, espaco_id?, fixada)`.
Uma oferta de 4 aulas com blocos de 2 gera **4 linhas de Alocacao** (uma por slot),
agrupadas logicamente por `bloco_idx` para que a UI arraste o bloco inteiro.
Guardamos `bloco_idx` na `Alocacao` para reconstruir os blocos sem heurística.

---

## 4. Configuração por unidade (`config_regras`)

Todo número de negócio vive aqui; o código só lê. Padrões por tipo de unidade
(`presets.py`):

```jsonc
{
  "carga_max_semanal": 29,              // FATEC; ETEC = 34
  "limite_diario": {                     // CLT art. 318 antigo — desligado por padrão
    "ativo": false,
    "max_consecutivas": 4,
    "max_intercaladas": 6
  },
  "interjornada": {
    "modo": "aviso",                     // off | aviso | rigida
    "horas": 11
  },
  "deslocamento_entre_unidades_min": 0,  // minutos exigidos entre unidades
  "usa_sabado": false,
  "atribuicao": {
    "regra": "ETEC",                     // ETEC | FATEC
    "desempates": ["assiduidade", "titulacao", "tempo_exercicio", "filhos"]
  },
  "pesos": {
    "janela_turma": 1000,
    "janela_professor": 100,
    "preferencia": 40,                   // recompensa (entra negativa)
    "dias_professor": 25,
    "estabilidade": 10,
    "dia_curto_no_fim": 5
  },
  "modo_objetivo": "ponderado"           // ponderado | lexicografico
}
```

Ordem lexicográfica quando `modo_objetivo = "lexicografico"`:
`janela_turma` → `janela_professor` → `preferencia` → `dias_professor` → `estabilidade`.

---

## 5. Formulação do solver (CP-SAT)

### 5.1 Entrada — `GradeState`
Estruturas puras, sem SQLAlchemy, para o solver e o validador compartilharem:

```python
Slot(id, dia, ordem, bloco_id, inicio_min, fim_min, modelo_turno_id)
Bloco(id, oferta_id, professor_id, turma_id, subturma, disciplina_id,
      tamanho, remota, tipo_lab, alunos, max_blocos_por_dia)
Ocupacao_externa: {(professor_id, dia, ordem_global)} de outras unidades (fixa)
```

### 5.2 Decomposição em blocos
Uma oferta com `aulas_semanais = A` e `tamanho_bloco = T` vira
`floor(A/T)` blocos de tamanho `T` mais, se `A % T != 0`, um bloco de `A % T`.
Ex.: A=4, T=2 → [2,2]; A=5, T=2 → [2,2,1]; A=3, T=2 → [2,1].

### 5.3 Variáveis

**`x[b, s] ∈ {0,1}`** — bloco `b` **começa** no slot `s`.

O conjunto de slots iniciais candidatos `S(b)` é pré-filtrado (isso é o que mantém o
modelo pequeno). `s ∈ S(b)` exige:
1. `s` pertence ao `modelo_turno` da turma de `b`;
2. existem `tamanho(b)` slots com `ordem` consecutiva a partir de `s`, todos no
   mesmo `(dia, bloco_id)` — **garante que o bloco não atravessa intervalo**;
3. o professor de `b` não está `INDISPONIVEL` em nenhum desses slots;
4. o professor não tem ocupação externa (outra unidade) em nenhum desses slots;
5. o dia não é sábado se `usa_sabado = false`.

Cobertura: `cobre[b, u] = OR{ x[b,s] : s inicia um bloco que cobre u }` — implementado
como soma (os intervalos que cobrem `u` a partir de diferentes `s` são mutuamente
exclusivos porque o bloco é alocado uma vez só), então
`cobre[b,u] == sum(x[b,s] for s in S(b) if u ∈ span(s, tam(b)))`.

**`y[b, e] ∈ {0,1}`** — bloco presencial `b` usa o espaço `e`.
Criado só para `e` compatível: tipo (SALA vs LABORATORIO + `tipo_laboratorio`) e
`capacidade >= alunos(b)`.

**`z[b, e, u] ∈ {0,1}`** — bloco `b` ocupa espaço `e` no slot `u`.
`z = cobre[b,u] AND y[b,e]`, linearizado com três cláusulas:
`z <= cobre`, `z <= y`, `z >= cobre + y - 1`.

> Escolha justificada: a alternativa (`AddNoOverlap` com intervalos opcionais por
> espaço) exige um intervalo opcional por par (bloco, espaço) e um `NoOverlap` por
> espaço, o que é mais variáveis e pior propagação para horizontes discretos e
> curtos (20–35 slots/semana). Com slots discretos, a formulação booleana
> `AtMostOne(z[·, e, u])` propaga direto e é a que o CP-SAT resolve mais rápido
> nesta escala. Registrado em DECISOES.md.

**Derivadas** (só criadas quando usadas pelo objetivo):
- `ocupa_prof[p, dia, ordem]`, `ocupa_turma[t, dia, ordem]` — BoolVar com
  `AddMaxEquality` sobre as coberturas correspondentes.
- `dia_usado_prof[p, d]`, `primeira[p,d]`, `ultima[p,d]` (IntVar sobre ordens).

### 5.4 Restrições rígidas

| # | Restrição | Modelagem |
|---|-----------|-----------|
| R1 | Cada bloco alocado exatamente uma vez | `sum(x[b,·]) == 1` |
| R2 | Professor: ≤1 aula por slot (inclui outras unidades) | `AtMostOne(cobre[b,u] : prof(b)=p)` por `(p,u)`; ocupação externa entra como slot proibido em `S(b)` |
| R2b | Deslocamento entre unidades | slots da unidade B a menos de `d` minutos de uma aula fixa da unidade A saem de `S(b)` |
| R3 | Turma: ≤1 aula por slot, exceto divisão PARALELA | `AtMostOne` por `(turma, subturma_ou_None, u)`; ofertas "turma inteira" entram no grupo de A **e** no de B |
| R4 | Espaço: ≤1 aula por slot | `AtMostOne(z[·,e,u])`; presencial exige `sum(y[b,·]) == 1`; remota não tem `y` |
| R5 | Disponibilidade | filtro em `S(b)` |
| R6 | Bloco não atravessa intervalo | filtro em `S(b)` (condição 2) |
| R7 | ≤ `max_blocos_por_dia` blocos da mesma oferta por dia | `sum(x[b,s] for b in oferta, s in dia) <= max` |
| R8 | Carga semanal ≤ carga do vínculo | checada na pré-validação (a atribuição já fixa a carga); repetida como restrição para o caso de o solver escolher a atribuição |
| R9 | Divisão SEQUENCIAL mesmo professor | `AtMostOne` já cobre (mesmo professor), mais proibição de mesmo slot entre A e B |
| R10 | Limite diário (se ativo) | `sum(ocupa_prof[p,d,·]) <= max_intercaladas`; consecutivas via janela deslizante `sum(ocupa_prof[p,d,i..i+K]) <= K` |
| R11 | Interjornada (se rígida) | `ultima_fim[p,d] - primeira_inicio[p,d+1] <= 24h - H` em minutos |
| R12 | Alocações fixadas | `x[b, s_fixo] == 1` |

### 5.5 Objetivo

Minimizar `Σ w_i · c_i`, com `c_i` inteiros:

1. **Janela da turma (`janela_turma`)** — para cada `(turma_grupo, dia, ordem u)`:
   `buraco[t,d,u] = 1` se `ocupa_turma[t,d,u] == 0` **e** existe aula em ordem > u no
   mesmo dia. Modelado com `tem_depois[t,d,u] = OR(ocupa_turma[t,d,v] : v > u)` e
   `buraco >= tem_depois - ocupa_turma`. Isso implementa direto a regra "os vazios
   ficam no fim do dia".
2. **Janela do professor (`janela_professor`)** — idem, por professor e unidade,
   ponderado pelo tamanho: soma dos `buraco[p,d,u]` (um buraco de 2 slots conta 2).
   Vazio no fim do dia não conta (mesma construção `tem_depois`).
3. **Preferência (`preferencia`)** — termo **negativo**:
   `- Σ w_pref · norm_pont(p) · cobre[b,u]` para `u` marcado `PREFERENCIAL` por `p`.
   `norm_pont(p) ∈ [0,100]` = pontuação do vínculo reescalada entre a menor e a maior
   da unidade. É isso que faz "quem tem mais pontuação leva o horário disputado".
4. **Dias do professor (`dias_professor`)** — `Σ dia_usado_prof[p,d]`.
5. **Estabilidade (`estabilidade`)** — `Σ (1 - x[b, s_anterior])` para blocos que
   existiam na grade anterior.
6. **Dia curto no fim da semana (`dia_curto_no_fim`)** — desempate leve:
   `Σ (5 - d) · falta_aula[t,d]`.

**Modo lexicográfico:** resolve com objetivo 1; se `OPTIMAL`, adiciona
`obj1 == valor` e resolve o 2; e assim por diante. Cada etapa herda o tempo restante
do orçamento total.

### 5.6 Execução
- `max_time_in_seconds` (padrão 60), `num_search_workers = os.cpu_count()`,
  `random_seed = 42` (reprodutível).
- `AddHint` com a grade anterior ao regenerar, e com a solução gulosa
  (ordenar blocos por grau de restrição e encaixar no primeiro slot viável) quando
  não há grade anterior.
- Callback `CpSolverSolutionCallback` grava em memória `{objetivo, bound, tempo,
  solucao_parcial}`; `GET /grades/{id}/progresso` lê esse registro e o frontend
  desenha a melhor solução parcial ao vivo.
- Job em `BackgroundTasks` + um registro em memória por `job_id`
  (`app/scheduling/jobs.py`). Sem Celery: o solver é CPU-bound e roda em
  `run_in_threadpool`; uma única unidade por vez é o caso real de uso.

### 5.7 Inviabilidade
1. `prevalidate.py` roda antes e cobre os casos triviais da seção 5.1 da spec, com
   mensagem nomeando a entidade.
2. Se o CP-SAT ainda der `INFEASIBLE`, `diagnose.py` reconstrói o modelo com as
   restrições relaxáveis agrupadas por entidade (professor, turma, espaço) atrás de
   literais de suposição, chama `AddAssumptions` e lê
   `SufficientAssumptionsForInfeasibility()` para nomear o conjunto mínimo de culpados.
3. A mensagem final é montada em português com as entidades resolvidas e um conjunto
   de ações sugeridas (`liberar_disponibilidade`, `adicionar_espaco`, `usar_sabado`).

---

## 6. Validador único

```python
# app/scheduling/validator.py
def validar(state: GradeState, config: Config) -> list[Violacao]: ...

@dataclass(frozen=True)
class Violacao:
    tipo: str          # CHOQUE_PROFESSOR, CHOQUE_TURMA, ...
    severidade: str    # INFO | ALERTA | BLOQUEANTE
    mensagem: str      # pt-BR, pronta para a UI
    entidades: dict    # ids para o frontend destacar
```

Função pura: recebe o estado completo (inclusive as alocações das outras unidades do
escopo) e devolve a lista. Usada por: pós-solver, validação de arrasto, ferramentas do
chat, e `POST /grades/{id}/publicar`.

**Teste de concordância** (`tests/test_validator_solver.py`): gera cenários aleatórios,
roda o solver, e afirma que `validar()` não encontra nenhuma violação BLOQUEANTE de
restrição rígida na solução. É o contrato entre os dois módulos.

---

## 7. Atribuição sugerida

```
ETEC:   ordena vínculos por (pontuação, assiduidade, titulação, tempo, filhos) desc
        passada 1 — MANUTENÇÃO: para cada docente na ordem, oferece as ofertas que
                     ele lecionava no período anterior (Habilitacao.origem=ANTERIOR)
        passada 2 — AMPLIAÇÃO: percorre de novo, oferecendo por prioridade de
                     componente: CONCURSO > ANTERIOR > HABILITADO
        respeita carga_max em ambas as passadas

FATEC:  ordena por (tipo_contrato INDETERMINADO primeiro, pontuação desc, desempates)
        passada única, mesma prioridade de componente
```

Sempre que 2+ docentes habilitados disputam a mesma oferta, o perdedor gera um
`Aviso(tipo="PRIORIDADE", severidade="ALERTA")` que exige ciência, citando o critério
que decidiu (pontuação ou o desempate específico).

---

## 8. Frontend

- **Roteamento**: React Router com `lazy()` por rota + prefetch no `hover`.
- **Dados**: TanStack Query, `persistQueryClient` no IndexedDB (idb-keyval),
  `staleTime` alto + refetch em background. `onMutate` otimista em **toda** mutação.
- **Sem telas de carregando**: `useTransition` na troca de visão, skeletons com o
  formato do conteúdo apenas no primeiro acesso sem cache, pílula de progresso no topo
  para a geração da grade.
- **Grade**: dnd-kit (`DndContext` + `useDroppable` por slot), Motion `layout` para a
  reorganização, `spring` no encaixe. Validação em tempo real chamando
  `POST /grades/{id}/validar-movimento` com debounce, pintando os slots.
- **Cores de disciplina**: hash estável do id → matiz HSL, mesma cor em todas as telas,
  com ícone/texto redundante para não depender só de cor.
- **Tema**: tokens CSS em `:root`, `@media (prefers-color-scheme: dark)` e
  `[data-theme]`; `prefers-reduced-motion` reduz as durações a ~0.

---

## 9. Ordem de execução (espelha a seção 12 da spec)

1. Scaffold + modelo + migrations + seed ← **etapa atual**
2. CRUDs e telas de cadastro
3. Validador único + pré-validação
4. Atribuição sugerida
5. Solver CP-SAT + job assíncrono
6. Visualização + avisos + publicar
7. Edição manual
8. Chatbot
9. Exportação e versionamento
10. Polimento, README, performance

Cada etapa termina com os testes da seção 10 da spec que lhe correspondem e uma
atualização de `docs/DECISOES.md`.
