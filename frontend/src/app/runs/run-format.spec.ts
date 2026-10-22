import { duration, estimate, formatSeconds, scopeLabel, statusChip, tokens } from './run-format';

describe('run formatting', () => {
  it('labels scopes', () => {
    expect(scopeLabel({ mode: 'site', sections: [], pages: [] })).toBe('Whole site');
    expect(scopeLabel({ mode: 'sections', sections: ['/a', '/b'], pages: [] })).toBe('/a, /b');
    expect(scopeLabel({ mode: 'sections', sections: ['/a', '/b', '/c', '/d'], pages: [] })).toBe(
      '4 sections',
    );
    expect(scopeLabel({ mode: 'changed', sections: [], pages: [] })).toBe('Changed pages');
    expect(scopeLabel({ mode: 'pages', sections: [], pages: ['/x'] })).toBe('1 listed page');
  });

  it('formats durations and estimates', () => {
    expect(formatSeconds(35)).toBe('35 s');
    expect(formatSeconds(42 * 60)).toBe('42 min');
    expect(formatSeconds(65 * 60)).toBe('1 h 5 min');
    expect(formatSeconds(120 * 60)).toBe('2 h');
    const run = { started_at: '2026-10-22T09:00:00Z', finished_at: '2026-10-22T09:42:00Z' };
    expect(duration(run)).toBe('42 min');
    expect(
      duration(
        { started_at: '2026-10-22T09:00:00Z', finished_at: null },
        Date.parse('2026-10-22T09:09:00Z'),
      ),
    ).toBe('9 min');
    expect(duration({ started_at: null, finished_at: null })).toBe('—');
    expect(estimate(20)).toBe('about 1 min');
    expect(estimate(90 * 60)).toBe('about 1.5 h');
  });

  it('formats token counts', () => {
    expect(tokens(1_797_600)).toBe('1.80M');
    expect(tokens(84_200)).toBe('84k');
    expect(tokens(900)).toBe('900');
  });

  it('maps statuses to hop-ui chips', () => {
    expect(statusChip({ status: 'running', progress: 61 })).toEqual({
      cls: 'hop-status-chip-running',
      label: 'Running · 61%',
    });
    expect(statusChip({ status: 'completed', progress: 100 }).cls).toBe(
      'hop-status-chip-completed',
    );
    expect(statusChip(null)).toEqual({ cls: '', label: 'Not audited' });
  });
});
