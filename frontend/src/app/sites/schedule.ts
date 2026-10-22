import { Schedule } from './site.model';

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
export const WEEKDAY_OPTIONS = WEEKDAYS.map((label, value) => ({ value, label }));
export const MONTHDAY_OPTIONS = Array.from({ length: 28 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}`,
}));

/** Wall-clock date and time now in a time zone. */
function wallClock(now: Date, timeZone: string) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone,
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hourCycle: 'h23',
    })
      .formatToParts(now)
      .map((p) => [p.type, Number(p.value)]),
  );
  return {
    y: parts['year'],
    m: parts['month'] - 1,
    d: parts['day'],
    minutes: parts['hour'] * 60 + parts['minute'],
  };
}

/**
 * The next scheduled run as the schedule's own wall clock, e.g.
 * "Tue, Oct 28, 2026 07:00 America/Denver"; null for manual schedules.
 */
export function nextRun(schedule: Schedule, now = new Date()): string | null {
  if (schedule.frequency === 'manual') return null;
  const [hh, mm] = schedule.time.split(':').map(Number);
  const today = wallClock(now, schedule.timezone);
  for (let offset = 0; offset < 62; offset++) {
    // Calendar arithmetic in UTC: no DST, just dates.
    const date = new Date(Date.UTC(today.y, today.m, today.d + offset));
    const matches =
      schedule.frequency === 'weekly'
        ? (date.getUTCDay() + 6) % 7 === schedule.day
        : date.getUTCDate() === schedule.day;
    if (!matches || (offset === 0 && hh * 60 + mm <= today.minutes)) continue;
    const label = new Intl.DateTimeFormat('en-US', {
      timeZone: 'UTC',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(date);
    return `${label} ${schedule.time} ${schedule.timezone}`;
  }
  return null;
}

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}
