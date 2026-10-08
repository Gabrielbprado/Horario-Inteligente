import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { MotionConfig } from 'motion/react'
import { lazy, Suspense, useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'

import { ProvedorGeracao } from '@/componentes/geracao'
import { Layout } from '@/componentes/layout'
import { ProvedorTema } from '@/componentes/tema'
import { LinhasEsqueleto } from '@/componentes/ui'
import { criarPersister, criarQueryClient } from '@/lib/query'
import Inicio from '@/rotas/inicio'

// Code splitting por rota. O prefetch da barra lateral e o `onMouseEnter` dos
// cartoes carregam o chunk antes do clique.
const Unidade = lazy(() => import('@/rotas/unidade'))
const Turnos = lazy(() => import('@/rotas/turnos'))
const Cursos = lazy(() => import('@/rotas/cursos'))
const Espacos = lazy(() => import('@/rotas/espacos'))
const Professores = lazy(() => import('@/rotas/professores'))
const Disponibilidade = lazy(() => import('@/rotas/disponibilidade'))
const Atribuicao = lazy(() => import('@/rotas/atribuicao'))
const Grades = lazy(() => import('@/rotas/grades'))
const DetalheGrade = lazy(() => import('@/rotas/grade'))
const Regras = lazy(() => import('@/rotas/regras'))
const Comparar = lazy(() => import('@/rotas/comparar'))
const Importar = lazy(() => import('@/rotas/importar'))

export default function App() {
  const [cliente] = useState(criarQueryClient)
  const [persister] = useState(() => criarPersister())

  return (
    <PersistQueryClientProvider
      client={cliente}
      persistOptions={{ persister, maxAge: 24 * 60 * 60 * 1000 }}
    >
      {/* `reducedMotion="user"` cobre **todo** componente do Motion de uma vez:
          sem isto cada animacao precisaria lembrar de checar a preferencia, e a
          que esquecesse passaria despercebida. O `index.css` tem a regra
          equivalente para as transicoes de CSS. Os `useReducedMotion` que
          sobraram sao onde a decisao e' nao renderizar (o confete), nao so'
          nao animar. */}
      <MotionConfig reducedMotion="user">
        <ProvedorTema>
          <BrowserRouter>
            <ProvedorGeracao>
              <Suspense fallback={<LinhasEsqueleto linhas={4} />}>
                <Routes>
                  <Route element={<Layout />}>
                    <Route index element={<Inicio />} />
                    <Route path="unidades/:unidadeId">
                      <Route index element={<Unidade />} />
                      <Route path="turnos" element={<Turnos />} />
                      <Route path="cursos" element={<Cursos />} />
                      <Route path="espacos" element={<Espacos />} />
                      <Route path="professores" element={<Professores />} />
                      <Route path="disponibilidade" element={<Disponibilidade />} />
                      <Route path="atribuicao" element={<Atribuicao />} />
                      <Route path="grades" element={<Grades />} />
                      <Route path="grades/:gradeId" element={<DetalheGrade />} />
                      <Route path="comparar" element={<Comparar />} />
                      <Route path="importar" element={<Importar />} />
                      <Route path="regras" element={<Regras />} />
                    </Route>
                    <Route path="*" element={<NaoEncontrado />} />
                  </Route>
                </Routes>
              </Suspense>
            </ProvedorGeracao>
          </BrowserRouter>
          <Toaster position="bottom-right" closeButton richColors />
        </ProvedorTema>
      </MotionConfig>
    </PersistQueryClientProvider>
  )
}


function NaoEncontrado() {
  return (
    <div className="py-20 text-center">
      <p className="text-2xl font-semibold tracking-tight">Página não encontrada</p>
      <p className="mt-2 text-texto-suave">
        O endereço não corresponde a nenhuma tela do sistema.
      </p>
      <a href="/" className="mt-5 inline-block text-primaria hover:underline">
        Voltar ao início
      </a>
    </div>
  )
}
