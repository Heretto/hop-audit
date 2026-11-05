import { defineConfig } from 'vitest/config';

// Merged into the config Angular's unit-test builder generates.
// Worker threads, and time to tear down. A worker that dies while the pool
// stops (SIGTERM for forks, exit 1 for threads) aborts the run and can hide
// the report of a test that actually failed, so read the full output when
// the summary is missing. Four workers at most: with one per core (16 here)
// the pool crashed while stopping far more often.
export default defineConfig({
  test: {
    pool: 'threads',
    maxWorkers: 4,
    teardownTimeout: 30_000,
  },
});
