import { listItem } from '../testing';
import { chartPoints, comparisonCsv, defaultPair, scoreDeltas, scored } from './history';

const site = { mode: 'site' as const, sections: [], pages: [] };
const runs = [
  listItem({ id: 'r1', number: 1, scope: site, metrics: { score: 71, analyzed_at: 'x' } }),
  listItem({
    id: 'r2',
    number: 2,
    scope: { mode: 'sections', sections: ['/api'], pages: [] },
    metrics: { score: 70, analyzed_at: 'x' },
  }),
  listItem({ id: 'r3', number: 3, scope: site, metrics: { score: 79, analyzed_at: 'x' } }),
  listItem({ id: 'r4', number: 4, status: 'running', metrics: {} }),
  listItem({
    id: 'x1',
    site_id: 's2',
    number: 1,
    scope: site,
    metrics: { score: 60, analyzed_at: 'x' },
  }),
];

describe('history helpers', () => {
  it('charts whole-site scored runs in order', () => {
    expect(scored(runs).map((r) => r.id)).toEqual(['r1', 'r2', 'r3', 'x1']);
    expect(chartPoints(runs.filter((r) => r.site_id === 's1')).map((p) => p.score)).toEqual([
      71, 79,
    ]);
  });

  it('changes are per site, against the previous scored run', () => {
    const d = scoreDeltas(runs);
    expect(d.get('r2')).toBe(-1);
    expect(d.get('r3')).toBe(9);
    expect(d.has('r1') || d.has('x1')).toBe(false);
  });

  it('picks the latest two scored runs to compare', () => {
    expect(defaultPair(runs.filter((r) => r.site_id === 's1'))).toEqual(['r2', 'r3']);
    expect(defaultPair(runs.slice(0, 1))).toBeNull();
  });

  it('writes the comparison as CSV', () => {
    expect(
      comparisonCsv(
        [
          { label: 'Site score', a: 79, b: 82, delta: 3 },
          { label: 'X', a: null, b: 1, delta: null },
        ],
        13,
        14,
      ),
    ).toBe('Metric,#13,#14,Change\n"Site score",79,82,3\n"X",,1,');
  });
});
