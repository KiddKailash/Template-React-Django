import { defineConfig } from 'vitest/config';

// Node environment, no DOM: components are checked by rendering to static
// markup (react-dom/server), as LLMStockAnalysis does. Add jsdom and
// @testing-library/react when a test needs to click things.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
  },
});
