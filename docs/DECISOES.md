# DECISÕES

Registro das decisões tomadas durante o desenvolvimento, conforme item 0.5 da
especificação. Formato: decisão, alternativa descartada, motivo.

---

## Etapa 1 — Scaffold, modelo de dados e seed

### D1 — Python 3.12 via `uv`, e não o Python do sistema
O sistema tem Python 3.14. `ortools` ainda não publica wheels para 3.14. O projeto
pina `requires-python = ">=3.12,<3.13"` e o `uv` baixa o interpretador certo.

### D2 — PKs inteiras, não UUID
SQLite e Postgres tratam `INTEGER PRIMARY KEY` da mesma forma sem extensão, os ids
aparecem em URLs e prompts do chat (mais curtos = menos tokens), e não há requisito
de gerar ids no cliente.

### D3 — `bloco_id` inteiro no `Slot`, em vez de comparar horários
A regra "bloco geminado não atravessa intervalo" vira uma comparação de igualdade
entre `(dia_semana, bloco_id)` mais `ordem` consecutiva. Não depende de o intervalo ser
de 10 ou 20 minutos, nem de aritmética de `time`.

### D4 — `Alocacao` é uma linha por **slot**, com `bloco_idx`
Alternativa descartada: uma linha por bloco com `slot_inicial` + `tamanho`. Uma linha
por slot deixa as consultas de ocupação ("quem está na sala 3 na 2ª aula de terça?")
serem um `WHERE slot_id = ?` direto, que é a consulta mais frequente do sistema (todas
as visões e todo o validador). `bloco_idx` preserva a informação de agrupamento para a
UI arrastar o bloco inteiro.

### D5 — Ofertas materializadas no banco
`Oferta` é gravada, não derivada em tempo de execução, porque `Atribuicao` e `Alocacao`
apontam para ela por FK. Um serviço `sincronizar_ofertas` recria as ofertas quando a
disciplina muda de `divisao_turma`.

### D6 — `Professor` no escopo, `VinculoUnidade` na unidade
Exigido pelo requisito de detectar choque entre a Fatec e a Etec da mesma cidade.
Pontuação e carga máxima são por vínculo porque a classificação docente é por unidade.

### D7 — JSON portável (`sqlalchemy.JSON`), não `JSONB`
`JSONB` seria melhor no Postgres, mas os campos JSON (`config_regras`, `diff`, `score`)
são sempre lidos inteiros, nunca consultados por chave. `JSON` funciona igual nos dois
bancos e evita um dialeto por ambiente.

### D8 — Uma migration inicial única no Alembic
O esquema nasce completo nesta etapa. Migrations incrementais começam a partir da
etapa 2, quando o modelo já estiver em uso.

### D9 — Linearização booleana `z[b,e,u]` para ocupação de espaço
Descartado `AddNoOverlap` com intervalos opcionais. Com 20–35 slots discretos por
semana, `AtMostOne` sobre booleanos propaga melhor e gera menos variáveis do que um
intervalo opcional por par (bloco, espaço). Detalhe em `PLANO.md` §5.3.

### D10 — Pré-filtro agressivo em `S(b)` em vez de restrições
Disponibilidade, intervalo, sábado, ocupação em outra unidade e deslocamento são
aplicados **removendo variáveis**, não adicionando restrições. Menos variáveis é a
alavanca principal de desempenho em timetabling com slots discretos.

### D11 — Sem Celery/RQ
O solver é CPU-bound e o caso de uso real é uma unidade gerando uma grade por vez.
`BackgroundTasks` + `run_in_threadpool` + um registro de progresso em memória
resolve. Trocar por Celery só se aparecer execução distribuída ou múltiplos workers.

### D12 — `tipo_laboratorio` como texto livre, não enum
As unidades criam tipos de laboratório próprios ("informática", "redes", "química",
"cozinha pedagógica"). Enum no código exigiria migration a cada unidade nova.
A comparação é por igualdade exata de string, normalizada em minúsculas.

### D13 — Fatec Taquaritinga usa o modelo "noturno + sábado" no seed
A matriz do DSM tem 24 aulas semanais por semestre e 5 noites × 4 aulas = 20 slots.
A própria especificação (§1.5) diz que as sobras vão para o sábado ou para
disciplinas remotas. Disciplina remota **também ocupa o slot da turma**, então ela
sozinha não resolve a aritmética: o seed usa o preset com sábado (26 slots) e marca
uma disciplina remota por semestre. `usa_sabado = true` nessa unidade.

### D14 — Preset Etec noturno com hora-aula de 55 min
Os horários publicados citados na spec (Etec Sales Gomes: 19h00–23h00, intervalo
20h50–21h10) só fecham exatamente com 4 aulas de 55 min. Manter 50 min deixaria
sobras que não existem no horário real. É preset editável, não regra.

### D15 — O seed inclui uma turma de ETIM diurno na Etec
A spec pede um professor nas duas unidades "para testar choque entre unidades e
interjornada". Dois cursos noturnos só produzem choque de horário; a violação de
interjornada exige uma aula pela manhã no dia seguinte. A turma de ETIM (07h00)
cria o par 22h30 (Fatec) → 07h00 (Etec) = 8h30 de descanso, abaixo das 11 h da CLT
art. 66. Sem ela, um dos cenários obrigatórios de teste não existiria.

### D16 — Disponibilidade só é gravada quando restringe
Ausência de registro significa `DISPONIVEL`. Gravar uma linha por (professor, slot)
seriam ~40 professores × 26 slots = 1040 linhas por unidade só para dizer "tudo bem".
Só `PREFERENCIAL` e `INDISPONIVEL` viram registro.

### D17 — Cor de disciplina por matiz hasheado, luminosidade fixa no CSS
`src/lib/cores.ts` deriva só o **matiz** de um hash FNV-1a do id, espaçado pelo
ângulo áureo para que ids vizinhos não fiquem parecidos. Luminosidade e croma são
fixos por tema na classe `.disciplina`, então o contraste não depende do hash — é o
que impede uma disciplina de sair ilegível no modo escuro. O ícone/texto redundante
cobre quem não distingue cores.

### D18 — Persister próprio de IndexedDB (idb-keyval), não o de localStorage
A spec pede cache persistente em IndexedDB. O persister oficial síncrono usa
localStorage. São ~20 linhas implementando a interface `Persister`, cada uma com
`try/catch` e fallback silencioso: cache é otimização, nunca requisito.

### D19 — `uv` no Docker do backend, build em duas camadas
`uv sync --frozen --no-install-project` antes de copiar o código: a camada de
dependências só é reconstruída quando o `uv.lock` muda.

### D20 — Nginx com `proxy_buffering off` no frontend em produção
O progresso do solver e o chat usam SSE. Com buffering ligado o nginx segura os
eventos e a grade não se desenha ao vivo.

---

## Etapa 2 — CRUDs e telas de cadastro

### D21 — Radix UI direto, com os tokens do projeto, em vez do gerador shadcn/ui
`shadcn/ui` é um gerador que copia componentes construídos **sobre o Radix UI** e
traz junto o seu próprio conjunto de tokens (`--background`, `--foreground`, …).
O sistema de design deste projeto já existia antes (`--color-superficie`,
`--color-primaria`, …, com claro/escuro e `prefers-reduced-motion`), e adotar o
gerador significaria manter dois vocabulários de cor ou reescrever o que ele gera.
`src/componentes/ui.tsx` usa as mesmas primitivas do Radix que o shadcn usa
(Dialog, Select, Switch, Label) escritas contra os tokens daqui. A dependência é a
mesma; o que muda é de quem são os nomes das cores.

### D22 — Fábrica de routers CRUD no backend
Onze entidades com comportamento idêntico (listar/criar/ler/atualizar/apagar).
`app/crud.py` gera o router e o que é específico entra por gancho
(`apos_criar` sincroniza ofertas quando muda a matriz; `antes_apagar` impede
remover unidade com grade). Sem a fábrica seriam onze arquivos quase iguais.

### D23 — `gravando()` cobre o flush, não só o commit
O `INSERT` sai no `flush`, não no `commit`. A primeira versão só protegia o commit
e uma violação de unicidade virava HTTP 500 em vez de 409. O gerenciador de
contexto `gravando()` envolve escrita **e** commit, e é o único caminho de escrita
dos routers.

### D24 — `Annotated[Session, Depends(get_db)]` em vez de `Depends()` no default
O idioma clássico do FastAPI deixa uma chamada de função no argumento padrão.
`app/db.SessaoDb` é o alias e vale para todas as rotas.

### D25 — Filtros de lista validados contra uma lista branca por recurso
`GET /unidades?nome=x` responde 422 dizendo quais filtros existem, em vez de
ignorar em silêncio um filtro digitado errado e devolver a lista inteira — o que
pareceria "o filtro não funciona".

### D26 — Modelo de turno é substituído inteiro (`PUT`), não campo a campo
O editor da tela mexe na semana toda. Antes de escrever qualquer coisa, a rota
verifica se algum horário que sumiria já tem aula alocada em alguma grade; se
tiver, recusa a requisição inteira em vez de deixar a semana pela metade.

### D27 — Cor de disciplina quantizada em 16 matizes
A primeira versão espalhava o hash pelos 360 graus com o ângulo áureo. Na prática
gerou pares como 243° e 245° — duas disciplinas diferentes com a mesma cor aos
olhos. Quantizado, duas disciplinas ou têm exatamente a mesma cor ou estão a pelo
menos 22,5° de distância. Acima de 16 disciplinas a colisão é inevitável; por isso
a sigla aparece sempre junto da cor.

### D28 — O horário fica na célula da grade de disponibilidade, não no cabeçalho
A 5ª aula de sábado na Fatec começa às 11h30 e a 5ª aula de quarta nem existe.
Um cabeçalho de linha com "5ª · 11:30–12:20" mostrava o horário do sábado para a
semana inteira. Cada célula carrega o seu próprio horário.

### D29 — `compararClassificacao` no frontend é só ordenação de tela
A ordem de desempate da Portaria CETEC 1.263/2017 aparece em
`src/rotas/professores.tsx` para listar os docentes na ordem certa. A versão
autoritativa, usada pela atribuição sugerida, vai para o backend na etapa 4 — as
duas precisam concordar, e o teste do backend será o que vale.

---

## Etapa 3 — Validador único e pré-validação

### D30 — `GradeState` puro, sem SQLAlchemy
`app/scheduling/domain.py` só tem dataclasses. O `loader` traduz o banco; o
validador e o solver enxergam apenas essas estruturas. É o que permite montar um
cenário à mão num teste (`tests/fabrica.py`) e ter certeza de que validador e
solver leem exatamente o mesmo estado.

### D31 — Horários em minutos desde a meia-noite
A interjornada compara o fim de um dia com o início do dia seguinte. Com
`datetime.time` isso exigiria aritmética de data; com minutos é uma subtração.
Nenhum turno do CPS passa da meia-noite (o mais tarde termina 23h00), então não
há wrap-around a tratar.

### D32 — `fluxos_da_oferta`: subturma como "fluxo de alunos"
Uma oferta de turma inteira ocupa os fluxos A **e** B; uma subturma ocupa só o
seu. A restrição "no máximo uma aula por (fluxo, horário)" então implementa de
uma vez as três regras: turma não tem duas aulas ao mesmo tempo, divisão paralela
pode ter A e B simultâneas, e aula de turma inteira nunca coincide com subturma.

### D33 — `candidatos.slots_iniciais` é a fonte única do filtro `S(b)`
A pré-validação e o solver precisam concordar sobre onde um bloco pode começar.
Duas implementações divergiriam: o solver acharia soluções que a pré-validação
declarou inviáveis, ou o contrário. O mesmo módulo devolve os candidatos para o
solver e os **motivos da recusa** para a mensagem de diagnóstico.

### D34 — Vazio no fim do dia não é janela
`_buracos` só conta um horário vago se ainda houver aula depois dele no mesmo
dia. É a regra da seção 5.4.1 da spec: quando a turma tem menos aulas que
horários, os vazios devem ficar no fim — sair às 21h40 não é defeito.

### D35 — Janela do professor pelo eixo do tempo, não pela `ordem` do slot
Um docente pode ter uma turma de manhã e outra à noite no mesmo dia. As duas têm
uma "1ª aula", então contar por `ordem` inventava janelas inexistentes. A
checagem compara `(inicio_min, fim_min)`.

### D36 — Pré-validação usa a demanda **mínima**, não a pior hipótese
Só pode acusar o que é inviável em qualquer arranjo. Por isso uma divisão
`PARALELA` (ou `INDIFERENTE`, que o solver ainda pode resolver em paralelo) conta
**uma vez** nos horários que a turma consome. Contar em dobro acusava o Módulo I
da Etec do seed como inviável (22 aulas em 20 horários) quando ele consome 18.
Só `SEQUENCIAL` conta duas vezes, porque A e B têm mesmo de cair em horários
diferentes.

### D37 — Ocupação externa só vem de grades PUBLICADAS
Um rascunho de outra unidade ainda pode mudar. Travar horário aqui por causa de
um rascunho alheio bloquearia a unidade sem motivo.

### D38 — Seed: a Etec ganhou um laboratório de 40 lugares
A pré-validação acusou `SEM_ESPACO_COMPATIVEL`: Lógica de Programação não tem
divisão de turma, são 36 alunos, e os dois laboratórios tinham 20 lugares. A Etec
agora tem um laboratório de 40 (para os componentes sem divisão) e dois de 20 —
que é exatamente a razão pela qual Programação Web é dividida.

### D39 — Pré-validação e validação devolvem o mesmo tipo `Violacao`
A UI, a tabela `Aviso` e o endpoint tratam as duas do mesmo jeito. Uma é "o que
impede de começar", a outra é "o que está errado no resultado", mas a forma de
mostrar ao usuário é idêntica.

---

## Etapa 4 — Atribuição sugerida

### D40 — A atribuição é um algoritmo guloso porque a norma é um algoritmo guloso
O ato de atribuição percorre a lista de classificação e cada docente escolhe
suas aulas na sua vez. Não é uma otimização — é um procedimento. Tentar
"melhorar" o resultado com um solver produziria distribuições que a norma não
autoriza. `assignment.py` reproduz o procedimento, e as ofertas que sobram viram
aviso em vez de serem redistribuídas à força.

### D41 — Duas passadas na Etec, uma na Fatec
Etec (Deliberação 23/2015): passada de **manutenção** (componentes que o docente
já lecionava, `Habilitacao.origem = ANTERIOR`) e depois de **ampliação**. Fatec
(Deliberação 52/2019): passada única, com contrato indeterminado antes.
A diferença entre as duas é uma chave de ordenação e um `if` — não duas
implementações.

### D42 — A ordem dos desempates vem de `config_regras`, não do código
`CRITERIOS` é um dicionário e `config.atribuicao.desempates` é a sequência.
A unidade pode reordenar sem alterar o sistema, como a especificação exige.

### D43 — A justificativa do aviso precisa ser verdadeira
A primeira versão dizia *"a prioridade ficou com Kelly Souza por maior pontuação
(70 × 78,5)"* — Kelly tem pontuação **menor**; ela ganhou pelo direito de
manutenção. `criterio_decisivo` recebe se está na passada de manutenção e, se o
perdedor é melhor classificado, atribui o motivo correto. A citação legal
acompanha o motivo: manutenção é Deliberação 23/2015, prioridade por
classificação é o art. 7º da Portaria 1.263/2017.

### D44 — Divisão paralela nunca cai toda no mesmo docente
Numa divisão `PARALELA` as subturmas A e B acontecem **ao mesmo tempo** em salas
diferentes. Dar as duas ao mesmo professor produziria uma grade impossível, que
só estouraria lá na frente como choque de professor. Se só há um habilitado, a
subturma B fica sem professor e vira aviso — que é a informação útil.
Em `SEQUENCIAL` o mesmo docente é o esperado.

### D45 — `expire_on_commit` no padrão do SQLAlchemy
`SessionLocal` usava `expire_on_commit=False`. Uma `Oferta` já carregada
mantinha `atribuicao=None` depois de a atribuição ter sido gravada, e a leitura
seguinte na mesma sessão via dado velho. Em produção cada requisição tem a sua
sessão e isso não apareceria, mas é uma classe de bug esperando por uma
transação mais longa. Voltar ao padrão custa uma releitura após o commit.

### D46 — "Sugerir atribuição" não é otimista
Todas as outras mutações do frontend são otimistas. Esta não: o resultado depende
de uma regra que só o servidor conhece, e adivinhar aqui poderia mostrar um
vencedor diferente do real por um instante. O botão espera a resposta e mostra os
avisos de prioridade que vieram com ela.

### D47 — `Selecao` sempre controlado (`valor ?? ''`)
Com `undefined` o Radix trata o Select como não-controlado no primeiro render e
depois avisa da troca — e, pior, voltar para "sem seleção" deixava de funcionar.

---

## Etapa 5 — Solver CP-SAT

### D48 — `w[b,s,e]` em vez de `y[b,e]` + `z[b,e,u]`
O PLANO previa uma variável "bloco usa espaço" mais uma "bloco ocupa espaço no
horário", ligadas por três cláusulas de linearização do AND. `w[b,s,e]` — "o
bloco começa em `s` **e** usa o espaço `e`" — dá o mesmo resultado com uma única
restrição (`sum_e w[b,s,e] == x[b,s]`), sem AND para linearizar, e com a mesma
contagem de variáveis. O espaço usado é lido da solução; não precisa de `y`.

### D49 — Divisão paralela é restrição rígida de igualdade
`x[bloco_A_i, s] == x[bloco_B_i, s]` para cada índice de bloco. É o sentido da
divisão paralela (A e B ao mesmo tempo, em salas diferentes) e ainda corta o
espaço de busca pela metade nessas disciplinas.

### D50 — Reprodutibilidade exige `workers=1`
A spec pede semente fixa "para ser reprodutível". A semente torna a busca de um
worker determinística, mas com vários workers e limite de tempo de relógio quem
prova a otimalidade primeiro é uma corrida entre threads: duas execuções podem
devolver ótimos **diferentes de mesmo custo**. O padrão usa todos os núcleos
(muito mais rápido) e `workers=1` dá o resultado byte-a-byte repetível. O que não
muda entre execuções é o custo do ótimo — e é isso que o teste verifica.

### D51 — `ocupa == sum(...)` escondia uma exclusividade
A variável de ocupação por horário era definida com igualdade. Como ela é
booleana, isso impunha "no máximo uma aula aqui" **dentro do próprio objetivo** —
uma restrição rígida que o diagnóstico de inviabilidade não conseguia relaxar,
e por isso o núcleo mínimo voltava vazio. Agora é a formulação de OR
(`var >= cada` e `var <= soma`), que não impõe teto. O modelo normal não muda:
a exclusividade continua vindo da sua própria restrição.

### D52 — Interjornada rígida também olha as outras unidades
A primeira versão só relacionava pares de variáveis internas. Uma aula fixa em
outra unidade no dia seguinte não entrava na conta, e o solver produzia
exatamente a violação que a regra existe para evitar. Agora os horários daqui
que não deixam o descanso mínimo em relação a uma aula externa são zerados.

### D53 — Índices em vez de varredura ao montar o modelo
`_ocupacao()` varria o dicionário `w` inteiro dentro de um laço por bloco e
horário. Com 200 blocos a montagem levava ~10 s — o suficiente para estourar o
limite de 60 s da spec mesmo com o solver resolvendo rápido. Com
`w_por_inicio` e `cobertura` pré-indexados, a montagem caiu para 0,5 s e a
primeira solução viável de uma grade cheia de 200 blocos sai em ~5 s.

### D54 — Sem Celery: `BackgroundTasks` + registro em memória
O job abre a própria sessão (não pode reaproveitar a da requisição, que fecha
com a resposta). `jobs.fabrica_de_sessao` é o ponto de troca, e é o que os
testes substituem pelo banco de teste.

### D55 — A ciência sobrevive à regeneração
`gravar_avisos` recria os avisos da grade mas preserva `ciente` de um aviso com
o mesmo tipo e a mesma mensagem. Regerar não deve obrigar o usuário a reconhecer
de novo o mesmo alerta que continua valendo.

### D56 — O solver nasce com o objetivo; o diagnóstico, não
Montar o objetivo custa variáveis auxiliares (ocupação, buracos, dias) que o
diagnóstico não usa — ele só quer saber qual conjunto de restrições não cabe
junto.

---

## Etapa 6 — Visualização, avisos e publicação

### D57 — As linhas da grade são faixas de horário, não o número da aula
`(dia, início, fim)` em vez de `(dia, ordem)`. Uma unidade pode ter turnos com
horários diferentes, e duas "1ª aula" em horários distintos não são a mesma
linha — é o mesmo motivo que fez a janela do professor ser medida no eixo do
tempo (D35). O backend devolve as faixas prontas e o `ordens` de cada uma, para
a tela não ter de reconciliar modelos de turno.

### D58 — A visão só mostra turnos que alguma turma usa
A Fatec do seed tem o modelo "manhã" cadastrado e sem nenhuma turma. Incluí-lo
na visão por professor enchia a tela de linhas vazias das 07h30 às 12h55, todas
marcadas como "janela" — um buraco em horário no qual ninguém poderia ter aula.
As três visões agora compartilham o mesmo eixo, e há teste para isso.

### D59 — A célula da grade vem pronta do servidor
`CelulaGrade` traz sigla, nome, turma, professor, espaço, ícones e horário já
resolvidos. A alternativa — devolver ids e deixar a tela cruzar — faria uma
grade de 72 aulas disparar dezenas de consultas ou manter cinco caches em
sincronia.

### D60 — Janela é destacada com cor **e** a palavra "janela"
A seção 11.3 pede que o aviso não dependa só de cor. O mesmo vale para os
ícones de aula remota, laboratório e cadeado, que têm `aria-label`.

### D61 — Impressão força o tema claro e paisagem
O tema escuro no papel gasta tinta e some. As cores das disciplinas, porém, são
informação: `print-color-adjust: exact` as preserva. `break-inside: avoid` nas
linhas impede que uma aula seja cortada entre páginas.

### D62 — Confete sem dependência
24 `<span>` animados com Motion, ~25 linhas. Uma biblioteca de confete para
isso seria mais código instalado do que escrito. Respeita
`prefers-reduced-motion`: quem desliga animação não vê nada.

---

## Etapa 7 — Edição manual

### D63 — A unidade de edição é o bloco, não a aula
Arrastar uma disciplina de 4 aulas geminadas move as duas aulas do bloco
juntas. `apply.Bloco(oferta_id, bloco_idx)` identifica o que o usuário pegou;
`candidatos.sequencia` diz se o destino comporta o bloco inteiro sem atravessar
intervalo — a mesma função que o solver usa.

### D64 — Um pedido por arrasto, não um por célula sobrevoada
`GET /grades/{id}/destinos` avalia **todos** os horários de destino de uma vez e
devolve a severidade de cada um. A tela pinta a semana no início do arrasto e
não conversa mais com o servidor até o drop. Custa 26 validações da grade — 2 ms
cada — e elimina a latência por célula.

### D65 — O arrasto mostra só o que **o movimento** quebra
`_novas_violacoes` compara o antes e o depois e reporta apenas o que surgiu. A
grade normalmente já tem avisos; repeti-los a cada arrasto faria o usuário achar
que ele causou tudo.

### D66 — Soltar no próprio lugar não é uma alteração
`_efetivas` descarta as mudanças em que `antes == depois`. Sem isso, arrastar e
soltar de volta gravava um passo no histórico e um "desfazer" que não desfazia
nada. Foi encontrado arrastando no navegador.

### D67 — Só a coluna do próprio bloco aceita o drop
Todas as colunas de uma linha compartilham o horário, então mapear a linha para
um `slot_id` sem olhar a coluna fazia o destino virar **silenciosamente o
próprio lugar do bloco** quando o usuário soltava na coluna de outra turma.
Mover uma aula para a coluna de outra turma seria trocar de quem é a aula, não
movê-la. A exceção é a visão por sala: ali a coluna **é** o destino, e arrastar
para outra coluna troca a sala da aula.

### D68 — Janela depende do turno da coluna
A visão mostra as faixas de horário de todos os turnos em uso. Uma turma do
noturno não tem janela às 07h00 — ela não tem aula de manhã. Sem essa checagem,
a tela marcava a manhã inteira como janela nas colunas do noturno e discordava
do validador, que sempre esteve certo. `calcularJanelas` virou função pura com
testes próprios; foi a segunda vez que essa lógica saiu errada.

### D69 — Editar a mão tira a grade de PUBLICADA
O que foi publicado mudou. A grade volta a RASCUNHO ou AGUARDANDO_CIENCIA
conforme os avisos que restaram.

### D70 — `forcar` aplica e deixa o bloqueio registrado
A spec pede que uma alteração manual que viola regra possa ser feita, com o
aviso BLOQUEANTE impedindo a publicação. Sem `forcar`, o movimento é recusado
com 409 e os motivos.

## Etapa 8 — Chatbot

### D71 — O LLM propõe, o usuário aplica
As ferramentas que mudam a grade não escrevem nada: devolvem uma `Proposta` com
o "antes → depois" e as violações que o movimento cria. A gravação só acontece
quando o usuário clica em Aplicar, e aí passa por `apply.py` — o mesmo caminho
do arrasto e do solver. Isso cumpre a regra central do projeto ("nunca deixe o
LLM gravar no banco diretamente") com uma consequência prática boa: uma alucinação
do modelo vira um cartão descartável, não uma grade quebrada.

### D72 — Propostas ficam em memória, não no banco
`propostas.REGISTRO` é um dicionário com trava e teto de 200. Uma proposta é
uma intenção efêmera de uma conversa, não um dado do domínio: gravá-la exigiria
tabela, migração e limpeza de lixo para nada. O custo é que reiniciar o servidor
invalida as pendentes — a API responde 404 com "Essa proposta expirou. Peça de
novo ao assistente." em vez de aplicar algo calculado contra um estado antigo.

### D73 — A proposta é revalidada na hora de aplicar
Entre propor e clicar, a grade pode ter mudado (outro usuário, outro arrasto).
`propostas.aplicar` não guarda o resultado calculado no momento da proposta: ele
refaz o movimento contra o estado atual. Guardar o `Resultado` seria mais rápido
e aplicaria uma mudança que já não faz sentido.

### D74 — `strict: true` em todas as ferramentas
O modo estrito da Responses API exige `additionalProperties: false` e **todas**
as propriedades em `required`; o que é opcional vira tipo anulável. `_obj()`
monta os esquemas assim por construção, então é impossível registrar uma
ferramenta que a API recusaria. Em troca, o modelo não inventa parâmetro nem
omite id obrigatório — os dois erros que mais custariam aqui.

### D75 — As regras da unidade entram no prompt do sistema
`instrucoes()` injeta carga máxima, interjornada, limite diário, dias com aula e
regra de atribuição. Sem isso, o assistente prometeria o que a configuração
daquela unidade proíbe. Como tudo é configurável por unidade (regra 2 do
projeto), o prompt não pode ter esses números escritos.

### D76 — Nada de ids na conversa: `buscar_entidades` primeiro
O usuário escreve "Luciana", "DSM 2", "quinta 20h50". A ferramenta de busca
traduz nome em id, inclusive de horários, e o prompt proíbe inventar ids. A
alternativa — despejar o catálogo inteiro no contexto — gastaria tokens a cada
mensagem e ainda assim quebraria numa unidade grande.

### D77 — `executar()` nunca levanta exceção
Um erro de ferramenta volta como texto para o modelo, que explica o problema ao
usuário e tenta outro caminho. Propagar a exceção mataria o SSE no meio da
resposta e deixaria a tela com uma mensagem pela metade.

### D78 — O SSE abre a própria sessão de banco
A sessão da requisição fecha quando o `StreamingResponse` começa a enviar, então
o gerador abre uma `SessionLocal` sua. Sem isso, a primeira ferramenta que lesse
a grade estouraria com a sessão fechada.

### D79 — Teto de 8 rodadas de ferramenta e 90 s por mensagem
Um laço de ferramentas sem teto é uma conta aberta na OpenAI. Ao estourar, a
tela recebe um evento `erro` dizendo para pedir uma coisa de cada vez.

### D80 — O front consome o SSE com `fetch`, não `EventSource`
A mensagem vai no corpo de um POST e `EventSource` só faz GET. O `fetch` ainda
dá o `AbortController` que o botão Parar usa. `separarEventos` é função pura com
testes: o pedaço final de cada chunk pode estar cortado no meio de um JSON, e a
primeira versão quebrava exatamente aí.

### D81 — O estado do chat nunca vem do cache em disco
`useEstadoChat` usa `staleTime: 0` e `gcTime: 0`. Isto é configuração do
servidor, não dado do usuário: o cache persistido no IndexedDB continuava
dizendo "Chat desativado" depois que a chave foi configurada. Encontrado
rodando no navegador.

## Etapa 9 — Exportação, versionamento e importação

### D82 — Um exportador por corte, não um por formato
`export/grade.py` transforma a `VisaoGrade` num quadro dias × horários e o PDF e
o Excel só desenham o que ele devolve. Escrever duas vezes a regra de "o que
aparece na grade de uma turma" garantia que os dois arquivos divergissem na
primeira mudança.

### D83 — O papel usa o outro corte da tela
A tela compara turmas lado a lado (colunas = turmas). O que se entrega na mão de
uma turma é o quadro clássico: **dias nas colunas, horários nas linhas**, uma
página por turma ou professor. É o formato que a escola já usa no mural.

### D84 — As linhas do quadro vêm do turno, não das aulas
Montar as faixas a partir das aulas que existem esconderia o horário vago — que
é exatamente o que o coordenador precisa ver. A 1ª série do ETIM tem aula às
07h50 e às 09h50; a linha vazia das 08h40 é a informação. Para professor e sala,
que não têm turno declarado, valem os turnos em que eles de fato dão aula — o
mesmo critério da tela (D68).

### D85 — A cor da disciplina é recalculada em Python, não aproximada
`export/cores.py` repete o hash FNV-1a do `Math.imul` do JavaScript e converte
OKLCH para sRGB com as matrizes que o navegador usa. Duas implementações da
mesma regra é o preço de uma aula exportada ter a cor que o coordenador viu na
tela; um "azul parecido" quebra a identificação visual de um jeito que ninguém
percebe até pôr os dois papéis lado a lado. Os testes fixam os matizes.

### D86 — ReportLab em vez de WeasyPrint
A spec aceita os dois. ReportLab é Python puro, sem GTK/Pango para instalar na
imagem, e aqui o documento é uma tabela — não há HTML pronto a aproveitar.

### D87 — Duplicar é a versão; o histórico continua sendo o histórico
Versionar não virou tabela nova: uma versão **é** uma grade da mesma unidade,
com as mesmas aulas copiadas. Tudo que já existe (visão, edição, avisos,
publicar, chat) funciona nela sem nenhuma mudança. A cópia nasce fora de
PUBLICADA e recalcula os avisos em vez de herdar a ciência, que foi dada sobre a
outra versão.

### D88 — A comparação é por bloco, não por hora-aula
Mover um bloco de duas aulas geminadas é **uma** mudança. `diff.py` compara a
primeira hora-aula de cada `(oferta, bloco_idx)` — a mesma unidade que o usuário
arrasta e o solver posiciona. As diferenças vêm antes das iguais: quem abre a
tela quer ver o que mudou.

### D89 — Importar confere primeiro e grava depois
`aplicar=false` roda a importação inteira e desfaz, devolvendo linha por linha o
que seria criado, atualizado ou recusado. A conferência e a gravação passam pelo
mesmo código — um "simulador" separado mentiria na primeira divergência. Com
`aplicar=true` só grava se **nenhuma** linha tiver erro: meio cadastro importado
é pior que nenhum.

### D90 — SAVEPOINT no SQLite precisa de transação explícita
O pysqlite só emite `BEGIN` quando vê um INSERT/UPDATE/DELETE. O `SAVEPOINT` de
cada linha era emitido antes do primeiro DML, caía fora de qualquer transação, e
o `ROLLBACK` seguinte não desfazia nada: **a conferência gravava de verdade**.
`db.preparar_sqlite` aplica a receita da documentação do SQLAlchemy
(`isolation_level=None` + `BEGIN` no evento `begin`), e o motor dos testes recebe
o mesmo tratamento — senão o teste passaria por um motivo que a aplicação não
tem. Encontrado rodando a importação contra o banco de desenvolvimento.

### D91 — Um erro de linha nunca vira 500
Cada linha roda dentro do seu `SAVEPOINT` e qualquer exceção vira uma entrada do
relatório com o número da linha e o motivo em português. Quem importa 300
professores precisa saber **qual** linha está errada, não que "a importação
falhou".

### D92 — O modelo de importação é a documentação, o exemplo e o código
Um `Modelo` guarda as colunas com a ajuda de cada uma, gera o arquivo de exemplo
e aplica a linha. Separados, os três saem do ar um do outro na primeira mudança
de cadastro. O `.xlsx` de exemplo leva a ajuda como comentário de célula: a
planilha se explica sem documentação junto.

### D93 — O CSV de exemplo sai com `;` e BOM
É o que faz o Excel em português abrir o arquivo já em colunas e com os acentos
certos, sem passar pelo assistente de importação. Na leitura, o separador é
detectado e `utf-8-sig`/`latin-1` são tentados nessa ordem.

### D94 — O professor é do escopo; importar noutra unidade cria o vínculo
Reimportar `ana.ribeiro` na Etec não duplica a docente: acrescenta o vínculo
daquela unidade. É esse o caso que gera choque de horário entre a Fatec e a Etec
da mesma cidade, e duplicar o cadastro esconderia o choque.

### D95 — O download é um link de verdade
Exportar e baixar o modelo são `<a href download>` apontando para a rota, não um
`fetch` que monta um blob: o nome do arquivo vem do `Content-Disposition` do
servidor e o navegador cuida do resto.

## Etapa 10 — Polimento

### D96 — O tema é aplicado antes da primeira pintura
O `ProvedorTema` escrevia `data-theme` num `useEffect`, que só roda **depois** de
montar. O navegador já tinha pintado o fundo do `:root` a essa altura: quem
escolheu o tema escuro via a tela clarear por um quadro a cada carregamento. Um
script de seis linhas em `index.html` lê a mesma chave do `localStorage` antes
do bundle. O preço é a chave existir em dois lugares, anotado nos dois.

### D97 — `prefers-reduced-motion` num lugar só
`<MotionConfig reducedMotion="user">` na raiz cobre todo componente do Motion.
Antes, três telas checavam `useReducedMotion` à mão e as outras não — e a que
esquecesse passaria despercebida, porque quem revisa raramente roda o sistema
com a preferência ligada. Os `useReducedMotion` que ficaram são onde a decisão é
**não renderizar** (o confete), não apenas não animar.

### D98 — Esqueleto com o formato do conteúdo
A promessa da seção 11.2 é que não haja tela de carregando. Uma pilha de barras
no lugar de uma tabela de horário cumpre a letra e falha no espírito: a página
pula quando os dados chegam. `GradeEsqueleto` desenha cabeçalho, coluna de
horários e o miolo (com buracos, senão parece uma tabela de dados);
`CartoesEsqueleto` usa a mesma grade de colunas da lista.

### D99 — Cor semântica do tema claro um tom mais escura
`sky-600`, `green-600` e `amber-600` ficam entre 2,9:1 e 4,1:1 sobre branco. Em
texto pequeno — "Aguardando ciência", "obrigatória", a etiqueta ETEC — isso
some. Passaram para o 700, que cruza os 4,5:1 sem deixar de ser a mesma cor. No
tema escuro o problema não existia: os tons claros já tinham folga sobre a
superfície escura. Medido com um auditor de contraste rodado nas dez telas, nos
dois temas.

### D100 — Opacidade não se empilha sobre cor já suave
Vários textos eram `text-texto-suave` com `opacity-60/70/80` por cima, caindo
para 2,5–3,9:1. A opacidade era decoração; a hierarquia já vinha do `text-xs`.
Onde o texto informa alguma coisa, agora é o token direto.

### D101 — Botão desabilitado troca de cor, não desbota
`disabled:opacity-50` punha texto branco sobre um índigo pálido: 1,6:1 no botão
"Publicar grade" — justamente o botão cujo `title` explica **por que** a ação
está bloqueada. Agora o estado desabilitado usa superfície e texto suaves:
legível e obviamente inativo.

### D102 — Anel de foco é regra global, não classe a lembrar
Havia uma constante `FOCO` aplicada à mão, e cerca de vinte controles a tinham
esquecido — o logo, a busca, os botões de ícone, as próprias células de aula.
Caíam no contorno padrão do navegador, fino demais sobre as cores das
disciplinas. Uma regra `:focus-visible` no CSS base cobre também o que for
escrito depois.

### D103 — Publicar, desfazer e duplicar também são otimistas
Eram as três mutações que ainda esperavam o servidor. Publicar troca o selo na
hora; desfazer risca o registro no histórico; duplicar insere o cartão da cópia
com id negativo (a convenção de `ehProvisorio`) e `aria-busy`. As três desfazem
com um toast se o servidor recusar. O que **não** dá para prever fica como
está: sugerir atribuição e gerar grade são cálculos do servidor, e importar tem
relatório próprio.

### D104 — Desempenho: testar o que o usuário espera sentado
O solver já tinha o teste de 200 blocos. Faltavam os caminhos interativos, que
rodam a cada arrasto e a cada mensagem do chat e não têm barra de progresso para
justificar a espera: `validar` a grade inteira (~3 ms), `destinos_possiveis` de
um arrasto (~100 ms para a semana toda) e `simular_movimento`. No frontend,
`calcularJanelas` e o desenho de 200 aulas. Os limites são folgados de propósito
— pegam regressão de ordem de grandeza, não milissegundos de uma CI
compartilhada.

## Massa de dados

### D105 — Massa que não fecha grade não serve para nada
`scripts/massa.py` termina rodando a **mesma pré-validação da tela da unidade**
em tudo que gerou, e sai com código 1 se alguma unidade não puder gerar grade.
Sem essa conferência, o gerador produziria um banco bonito em que o botão
"Gerar grade" responde "sem solução" — e quem estivesse navegando acharia que é
defeito do sistema, não dos dados.

### D106 — A capacidade de um turno se mede em aulas geminadas, não em horários
O ETIM tem 30 horários por semana: dois blocos de **três** aulas por dia. Como
uma geminada nunca atravessa intervalo, cada bloco de três comporta um par e
sobra um horário solto — 20 aulas, não 30. A primeira versão contou 30, montou
turmas de 26 aulas e o solver devolveu INFEASIBLE. `capacidade_em_aulas` agora
percorre o layout do preset e conta pares. (A pré-validação passou a contar
pares também em D119.)

### D107 — Espaços dimensionados por demanda, não por palpite
A primeira regra era "60% do número de turmas vira laboratório". Dava Etec com
sala sobrando e laboratório de informática faltando. Agora conta-se, por turno,
quantos espaço-horários cada tipo de laboratório e as salas comuns consomem na
semana, divide-se pelos horários do turno e soma-se uma folga. Aula remota não
entra na conta; divisão de turma entra em dobro.

### D108 — Uma unidade tem um horário noturno só
Dois presets noturnos na mesma Etec (19h00 e 18h50) se sobrepõem no relógio mas
são `ModeloTurno` distintos, então a contagem de espaços os tratava como turnos
independentes e subdimensionava as salas. Além de irreal: uma escola publica um
horário noturno, não dois.

### D109 — O teto de carga do vínculo é o que cabe nos horários livres
O ato de atribuição não olha disponibilidade — ele distribui até a carga máxima.
Com o máximo legal (29) ele empilhava 28 aulas em quem tirou um dia de folga e
só tem 16 horários, e a pré-validação reprovava a unidade. Os vínculos gerados
trazem `carga_max_semanal = 12`, que cabe em qualquer turno mesmo com um dia
livre, e o gerador cria mais docentes para compensar.

### D110 — O gerador acrescenta um escopo; não substitui o seed
`scripts/seed.py` continua sendo o exemplo da spec, com os cenários de disputa
que os testes conferem. A massa entra num escopo à parte ("Região de
Campinas"), então dá para ter os dois ao mesmo tempo — e `--limpar` existe para
quem quiser só a massa.

### D111 — A paleta de comandos filtra por conta própria e mostra só o topo
A primeira versão entregava **todos** os registros ao `cmdk` e deixava ele
filtrar. Com o banco de exemplo eram uns 60 itens e funcionava. Com a massa de
dados são mais de 1.500, o cmdk pontua todos a cada tecla, e a aba congelava por
dezenas de segundos — o inspetor do navegador chegava a estourar o tempo limite.

Agora o filtro é nosso (`shouldFilter={false}`), cada palavra é procurada
separadamente e sem acento ("lab inform" acha "Lab. Informatica 3"), e só os
seis primeiros de cada grupo vão para o DOM: 36 itens, não importa o tamanho do
banco. O cabeçalho mostra "6 de 500" para o usuário saber que refinar adianta.

Foi a massa de dados que revelou isto; com seis turmas o problema não existia.

### D112 — Janela na visão por professor segue o turno de quem leciona
Terceira vez que esta lógica sai errada, agora no corte por professor. A coluna
de um docente não declara `modelo_turno_id` — só a turma declara —, e
`calcularJanelas` tratava "sem turno" como "todos os turnos". Numa unidade que
usa manhã e noite, quem leciona só à noite aparecia com a manhã inteira
marcada como janela. O PDF já acertava (`export/grade.py` deriva o turno das
aulas da coluna); a tela passou a usar o mesmo critério.

Foi a massa de dados que revelou: a Fatec do seed só tem o noturno em uso, e o
caso nunca aparecia. Dois testes novos cobrem o docente de um turno só e o que
leciona nos dois.

### D113 — Nomes de docente por combinação, não por lista fixa
A lista tinha 59 nomes para ~500 vagas e o resto virava "Docente 184". Numa
massa feita para olhar na tela, isso estraga a demonstração inteira. Agora são
60 prenomes × 59 sobrenomes = 3.540 combinações, embaralhadas e sem repetição.

## Resolver avisos

### D114 — O solver conta a janela da turma em todo horário do turno, como o validador
`_buracos` só criava variável nos horários em que algum bloco *podia* cair. Se
o único professor de uma turma está indisponível na 1ª aula, o solver não via
a 1ª aula vaga como janela; o validador via, e a grade saía "ótima" com um
aviso que o objetivo nunca tentou evitar. Agora a turma conta todos os
horários do seu modelo de turno, com ocupação constante zero onde nada cabe.
O eixo do professor fica como estava: ali o validador também só olha os turnos
em que o docente tem aula naquele dia (D35, D112), e não há como saber isso
antes de resolver.

### D115 — "Resolver avisos" é regra rígida com fallback, não peso maior
Multiplicar os pesos por cem sempre entrega uma grade, mas nunca garante nada:
a Fatec do seed já era ótima com 3 janelas de turma, porque com geminadas de 2
aulas num bloco de 3 horários no sábado **toda** turma de 24 aulas fica com a
1ª ou a 3ª aula vaga. `Parametros.resolver_avisos` transforma janela de turma,
janela de professor e interjornada em restrição, um grupo por turma ou
professor, cada um atrás de um literal de suposição.

Quando não fecha, o diagnóstico não usa o núcleo por suposições: ele exige um
worker só, e com um worker o CP-SAT não prova a inviabilidade da Fatec em 30 s
(com oito, prova em 0,3 s). Em vez disso, crescimento guloso — endurece um
grupo por vez, turma antes de professor antes de interjornada, e guarda o maior
conjunto que ainda fecha. O complemento vai em `Parametros.relaxar`, o job
resolve de novo e **entrega a grade**: sem os avisos que tinham jeito, e com a
mensagem nomeando os que não tinham. A grade gerada assim não mostra o botão
de novo.

### D116 — O status "inviável" só é gravado depois do diagnóstico
A tela para de consultar o progresso quando `terminado` é verdadeiro. O job
marcava `inviavel` antes de diagnosticar, e a mensagem chegava depois da
última consulta: a pílula dizia "Sem solução" sem dizer por quê.

### D117 — As alocações da grade anterior são lidas antes do commit
Com `partir_de`, o endpoint lia a grade anterior depois do commit, reabrindo a
transação da sessão da requisição. No banco em memória dos testes o job
(sessão própria, mesma conexão) não conseguia abrir a dele. Em produção cada
sessão tem sua conexão e nada acontecia, mas o teste novo quebrou e a leitura
depois do commit era desnecessária de qualquer forma.

## Massa com conflitos

### D118 — `--conflitos` sabota depois de povoar, em vez de gerar torto
A massa normal promete que tudo fecha (D105), e os testes guardam isso. Para
ver o sistema reagir a dados ruins, a sabotagem é uma passada separada sobre a
região já pronta: planta um conflito de cada tipo que a pré-validação, o
validador e o diagnóstico sabem nomear, em rodízio por unidade, e devolve um
relatório impresso do que plantou e onde. Assim o gerador continua um só, a
promessa de D105 continua testada, e `tests/test_massa.py` confere que cada
conflito plantado aparece de fato na tela da unidade. O choque entre unidades
só existe contra grade **publicada**, então `--conflitos` com `--gerar-grades`
publica as grades das Fatecs antes de gerar as das Etecs.

### D119 — A pré-validação conta pares geminados, não só horários
Cadastrar turmas de manhã na Fatec do seed repetiu a armadilha de D106 do lado
do usuário: 24 aulas em blocos de 2, turno de 30 horários em blocos de 3, a
pré-validação dizia "pronta para gerar" e o solver respondia INFEASIBLE com um
diagnóstico que "não conseguiu isolar" — o núcleo por exclusividade não modela
capacidade. Agora `_turma_nao_cabe_no_turno` checa, por tamanho de bloco, se a
soma dos trechos contíguos (`len // tamanho * tamanho`) comporta as aulas
daquele tamanho. Cada tamanho é conferido sozinho, de propósito: é o que dá
para afirmar impossível em qualquer arranjo sem resolver o empacotamento. A
mensagem diz o que mudar — o tamanho do bloco das disciplinas ou os intervalos
do turno.

### D120 — A coluna da turma diz o turno, e a manhã vem antes da noite
Com turmas de manhã e de noite do mesmo curso, a visão por turma mostrava
duas colunas "DSM 1o sem" idênticas, e as linhas da manhã vazias na coluna da
noite pareciam aula sem professor. `TurmaInfo` ganhou o nome do turno, o
subtítulo virou "Manhã · 36 alunos", e as colunas se ordenam pelo primeiro
horário do turno antes de curso e período. PDF e XLSX herdam o subtítulo.

### D121 — Blocos decididos no curso, gravados na disciplina
"Geminadas, até dois blocos por dia" é decisão do curso, não de cada uma das
dezoito disciplinas. Mas o solver lê `tamanho_bloco` e `max_blocos_por_dia` na
disciplina, e uma coluna nova no curso criaria duas fontes para o mesmo dado
(e uma migration). `PUT /cursos/{id}/blocos` grava o valor em todas as
disciplinas do curso numa transação; a tela mostra o valor comum, ou "misto"
quando divergem, e a disciplina continua editável como exceção. Disciplina
nova nasce com o valor comum do curso. Sem herança em tempo de leitura: o que
está na disciplina é o que vale, e é o que a tela mostra.

### D122 — "Concentrar no mesmo dia": regra no solver, alerta na edição manual
"Blocos por dia = 2" só *permite* juntar os dois pares de uma disciplina, e o
solver juntava quando o peso de dias do professor compensava — inclusive em
sanduíche (`ED ED BDR BDR ED ED`). Para a escola escolher o "4 + 2" faltava
obrigar. `Disciplina.concentrar_no_dia` põe todos os blocos da oferta no mesmo
dia e em horários seguidos da turma (em cada dia, a ocupação da oferta só pode
começar uma vez). Não é "tamanho do bloco 4": um bloco nunca atravessa
intervalo, e nenhum turno do CPS tem quatro aulas sem intervalo — foi o que
travou a unidade quando o campo foi posto em 4.

Concentrar manda mais que "blocos por dia" (`limite_blocos_por_dia`), para não
haver duas configurações se contradizendo. No validador é **alerta**
(`AULAS_NAO_CONCENTRADAS`), não bloqueante: arrastar leva um par por vez, e o
primeiro par arrastado para outro dia sempre separa os dois — bloquear
impediria mudar a disciplina de dia à mão. A pré-validação ganhou
`CONCENTRACAO_NAO_CABE` para o caso em que nenhum dia do turno comporta as
aulas seguidas. Como os blocos (D121), aplica-se ao curso e grava na disciplina.

### D123 — Concentrar é a prioridade mais alta, não uma regra que trava
D122 nasceu rígida, e a primeira coisa que aconteceu foi alguém ligar
"Concentrar" no curso inteiro: seis disciplinas de 4 aulas por semestre, manhã
de 6 aulas e 5 dias — cabe uma concentrada por dia, cinco na semana. O solver
respondeu "sem solução", a pré-validação tinha dito "pronta para gerar", e o
diagnóstico sugeria liberar a disponibilidade de seis professores, o que não
resolveria nada.

Agora cada oferta marcada tem um booleano "ficou concentrada", e o objetivo
cobra `pesos.nao_concentradas` (100.000, acima de tudo, inclusive da preferência
mais bem pontuada) por oferta que não coube. A que fica de fora volta a
obedecer "blocos por dia". Seis marcadas viram 5 + 1; quatro marcadas, 4 + 2.
A pré-validação deixou de bloquear: `CONCENTRACAO_NAO_CABE` virou alerta e
`CONCENTRACOES_DEMAIS` diz, antes de gerar, que pelo menos N ficam espalhadas
(teto por dia com as menores, por isso "pelo menos"). Depois de gerar,
`AULAS_NAO_CONCENTRADAS` diz qual.

Peso grande em vez de duas etapas lexicográficas: é o que já existe, aparece em
"Regras da unidade" como os outros, e o modo lexicográfico, para quem quiser a
garantia, já otimiza esse termo primeiro.

### D124 — O `.env` é o da raiz, lido por caminho absoluto; os testes não o enxergam
O README manda criar o `.env` na raiz e o Compose lê dali, mas `Settings` usava
`env_file=".env"`, relativo à pasta de onde a API roda — `backend/`. Em
desenvolvimento a chave da OpenAI nunca era lida e o painel dizia "Chat
desativado" com tudo configurado. Agora são dois caminhos absolutos: o da raiz
e, por cima, um `backend/.env` opcional.

Ler a chave de verdade criou um risco que não existia: `test_chat` presume que
não há chave, e com uma no `.env` um dos testes chamaria a OpenAI com o crédito
de quem rodou a suíte. `tests/__init__.py` zera `OPENAI_API_KEY` e
`OPENAI_MODEL` no ambiente antes de a aplicação ser importada (variável de
ambiente vence o arquivo), e `tests/test_config.py` guarda as duas coisas.

### D125 — Itens do SDK voltam para a OpenAI com `to_dict()`, não `model_dump()`
A primeira conversa real com ferramenta falhou com `Unknown parameter:
'input[4].async_'`. O laço devolve a saída do modelo como entrada da rodada
seguinte, e convertia os objetos do SDK com `model_dump()`: nome Python do
campo (`async_`, que a API chama `async`) e campos que a API nem tinha mandado.
`to_dict()` é o método do SDK para isso — nomes da API, só o que veio.

O cliente falso dos testes usa dicionários e nunca exercitou a conversão. Há
agora um teste com `ResponseFunctionToolCall` de verdade, sem rede: é o tipo de
erro que só aparece quando o objeto real passa pelo caminho.

## Marca

### D126 — O símbolo é um quadro de horário que desenha um H
O cabeçalho usava um ícone genérico de calendário e o favicon ainda era o raio
do Vite. A marca nova sai do próprio assunto: uma grade de 3 × 3 (três dias,
três aulas) em que as aulas alocadas formam o H — à esquerda um bloco geminado
e uma aula solta, à direita o inverso, que também se lê como o "i" de
Inteligente, e no meio, em amarelo, a aula que encaixa. As duas células vagas
do meio ficam apagadas e somem abaixo de 24 px.

O primeiro rascunho tinha emendas largas entre os blocos e lia como "! · i":
as emendas foram fechadas até a silhueta do H dominar em 16 px.

Índigo é o que o sistema já usava; o amarelo marca-texto é a única cor nova e
aparece só nesse bloco — tinta de caneta e marca-texto sobre papel, o material
de quem monta horário à mão. O nome está em Inter Display convertida em
contornos, para os SVG não dependerem de fonte instalada. `Simbolo` e `Logo`
em `frontend/src/componentes/logo.tsx` repetem os números de `docs/marca/`.
