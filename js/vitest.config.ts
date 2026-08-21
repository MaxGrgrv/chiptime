import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    // Determinism: no watch-mode flakiness, no parallel ordering effects on shared vectors.
    sequence: { shuffle: false },
  },
});
