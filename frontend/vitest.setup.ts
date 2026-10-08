import '@testing-library/jest-dom/vitest'

// jsdom nao implementa matchMedia, usado pelo tema e por prefers-reduced-motion.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})
