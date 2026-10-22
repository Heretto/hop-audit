# Plain-language checklist and how to report

HOP Audit computes Flesch Reading Ease, Flesch-Kincaid grade, words per sentence and passive voice for every page. You explain the scores and propose fixes; do not recompute them.

Score bands (Flesch Reading Ease): 60+ plain; 50–59 fairly difficult; 30–49 difficult; below 30 very difficult. Tutorials and getting-started pages should reach 60. Reference pages (API, configuration tables) may be denser: judge them on sentence length and structure, not the score alone. The site's focus text overrides these defaults.

For each page you flag:

1. Name the cause in one sentence: long sentences, stacked noun phrases, passive constructions, undefined jargon, or a wall of text without lists or headings.
2. Quote the worst sentence exactly and give a rewrite that keeps every fact.
3. Severity: High when a reader could do the task wrong because of the wording; Medium for a page that misses its band; Low for isolated sentences.
4. Mark a finding `on_focus` when it is something the site's or run's focus asked for.

Do not flag product names, code, UI labels or required legal text as jargon. Do not rewrite for style alone when the page already meets its band.
