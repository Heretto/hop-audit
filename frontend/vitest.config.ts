import { defineConfig } from 'vitest/config';

// Merged into the config Angular's unit-test builder generates.
// Worker threads, not child processes: under load (./dev.sh check runs the
// backend suite first) Vitest could kill a slow-to-exit forked worker with
// SIGTERM at shutdown and fail an all-green run.
export default defineConfig({
  test: {
    pool: 'threads',
    teardownTimeout: 30_000,
  },
});
