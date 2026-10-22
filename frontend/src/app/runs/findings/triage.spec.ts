import { sampleIntegrity, sampleIntegrityView } from '../testing';
import { exampleHint, examples, matches, recount } from './triage';

const findings = sampleIntegrityView().findings;
const none = { query: '', category: '', tier: '' as const, severity: '' };

describe('triage', () => {
  it('recounts by tier, severity and category (firm only)', () => {
    const r = recount(findings);
    expect([r.firm, r.review, r.drop, r.candidates]).toEqual([3, 1, 1, 5]);
    expect([r.high, r.medium, r.low]).toEqual([2, 1, 0]);
    expect(r.categories).toEqual([
      { code: 'C', label: 'Contradictions', n: 1 },
      { code: 'O', label: 'Outdated content', n: 1 },
      { code: 'T', label: 'Translation defects', n: 1 },
    ]);
  });

  it('orders examples as picked and ignores non-firm ones', () => {
    const picked = examples([
      sampleIntegrity({ id: 'a', example_rank: 2 }),
      sampleIntegrity({ id: 'b', example_rank: 1 }),
      sampleIntegrity({ id: 'c', example_rank: 3, tier: 'review' }),
      sampleIntegrity({ id: 'd' }),
    ]);
    expect(picked.map((f) => f.id)).toEqual(['b', 'a']);
  });

  it('hints how many examples to pick', () => {
    expect(exampleHint(1)).toBe('pick 2 more');
    expect(exampleHint(3)).toContain('backup');
    expect(exampleHint(4)).toBe('3 for the one-sheet plus a backup');
    expect(exampleHint(6)).toContain('too many');
  });

  it('filters by text, slug, category, tier and severity', () => {
    const f = findings[0];
    expect(matches(f, { ...none, query: 'c-01' })).toBe(true);
    expect(matches(f, { ...none, query: 'credit-faq' })).toBe(true);
    expect(matches(f, { ...none, query: 'nothing like this' })).toBe(false);
    expect(matches(f, { ...none, category: 'T' })).toBe(false);
    expect(matches(f, { ...none, tier: 'review' })).toBe(false);
    expect(matches(f, { ...none, severity: 'High' })).toBe(true);
  });
});
