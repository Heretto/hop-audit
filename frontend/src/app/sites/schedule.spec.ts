import { nextRun } from './schedule';
import { Schedule } from './site.model';

const at = (iso: string) => new Date(iso);
const weekly = (day: number, time = '07:00', timezone = 'UTC'): Schedule => ({
  frequency: 'weekly',
  day,
  time,
  timezone,
});

describe('nextRun', () => {
  it('is null for manual schedules', () => {
    expect(nextRun({ frequency: 'manual', day: 1, time: '07:00', timezone: 'UTC' })).toBeNull();
  });

  it('finds the next matching weekday (0 = Monday)', () => {
    // Thu Oct 22, 2026 12:00 UTC -> next Tuesday is Oct 27
    expect(nextRun(weekly(1), at('2026-10-22T12:00:00Z'))).toBe('Tue, Oct 27, 2026 07:00 UTC');
    expect(nextRun(weekly(6), at('2026-10-22T12:00:00Z'))).toBe('Sun, Oct 25, 2026 07:00 UTC');
  });

  it('uses today only when the time is still ahead', () => {
    expect(nextRun(weekly(3, '13:00'), at('2026-10-22T12:00:00Z'))).toBe(
      'Thu, Oct 22, 2026 13:00 UTC',
    );
    expect(nextRun(weekly(3, '12:00'), at('2026-10-22T12:00:00Z'))).toBe(
      'Thu, Oct 29, 2026 12:00 UTC',
    );
  });

  it("reads 'today' on the schedule's own clock", () => {
    // 03:00 UTC Thursday is still Wednesday 21:00 in Denver.
    expect(nextRun(weekly(2, '22:00', 'America/Denver'), at('2026-10-22T03:00:00Z'))).toBe(
      'Wed, Oct 21, 2026 22:00 America/Denver',
    );
  });

  it('handles monthly schedules across a month end', () => {
    const s: Schedule = { frequency: 'monthly', day: 5, time: '07:00', timezone: 'UTC' };
    expect(nextRun(s, at('2026-10-22T12:00:00Z'))).toBe('Thu, Nov 5, 2026 07:00 UTC');
    expect(nextRun({ ...s, day: 28 }, at('2026-12-29T00:00:00Z'))).toBe(
      'Thu, Jan 28, 2027 07:00 UTC',
    );
  });
});
