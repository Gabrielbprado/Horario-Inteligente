/**
 * Cor estavel por disciplina: a mesma disciplina recebe a mesma cor em todas as
 * telas (secao 11.1 da spec).
 *
 * O matiz e' quantizado numa roda de `MATIZES` posicoes igualmente espacadas.
 * Espalhar o hash direto pelos 360 graus parece melhor no papel mas produz pares
 * como 243 e 245, que o olho le como a mesma cor sem serem a mesma disciplina.
 * Quantizado, duas disciplinas ou tem exatamente a mesma cor ou estao a pelo
 * menos 360/MATIZES graus de distancia.
 *
 * Com mais de `MATIZES` disciplinas na tela a colisao e' inevitavel; por isso a
 * sigla aparece sempre junto da cor, e nenhuma informacao depende so dela.
 *
 * Luminosidade e croma sao fixos por tema na classe `.disciplina` (index.css),
 * entao o contraste nunca depende do hash.
 */
const MATIZES = 16
const PASSO = 360 / MATIZES

/** Deslocamento para a roda nao comecar no vermelho puro, reservado a erros. */
const OFFSET = 18

function hash(texto: string): number {
  let h = 2166136261
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return Math.abs(h)
}

export function matizDisciplina(chave: string | number): number {
  return (OFFSET + (hash(String(chave)) % MATIZES) * PASSO) % 360
}

/** Estilo inline a aplicar junto da classe `disciplina`. */
export function estiloDisciplina(chave: string | number): React.CSSProperties {
  return { '--cor-h': matizDisciplina(chave) } as React.CSSProperties
}
