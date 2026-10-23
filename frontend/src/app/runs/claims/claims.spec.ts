import { sampleClaimsView } from '../testing';
import { matchesClaim, NO_FILTERS, rankGroups } from './claims';

describe('claims', () => {
  const { claims, groups } = sampleClaimsView();
  const shown = (f: Partial<typeof NO_FILTERS>) =>
    claims.filter((c) => matchesClaim(c, { ...NO_FILTERS, ...f })).map((c) => c.statement);

  it('filters by text, help center and matching', () => {
    expect(shown({}).length).toBe(5);
    expect(shown({ query: 'REFUND' })).toEqual([
      'Refunds within 30 days.',
      'Refunds within 30 days.',
    ]);
    expect(shown({ query: 'billing/faq' })).toEqual(['The late fee is $15.']);
    expect(shown({ center: 'hc-fr' })).toEqual(['Les frais sont de 10 $.']);
    expect(shown({ group: 'matched' }).length).toBe(4);
    expect(shown({ group: 'single' })).toEqual(['Les frais sont de 10 $.']);
    expect(shown({ group: 1 })).toEqual(['The late fee is $10.', 'The late fee is $15.']);
  });

  it('ranks groups with candidates, then failures, then size', () => {
    const failed = { ...groups[1], number: 3, status: 'failed' as const };
    const big = { ...groups[1], number: 4, claims: 5 };
    expect(rankGroups([...groups, failed, big]).map((g) => g.number)).toEqual([1, 3, 4, 2]);
  });
});
