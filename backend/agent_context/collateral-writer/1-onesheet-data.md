# One-sheets: data and copy

There are two one-sheets, built from the same findings. Make both.

- **Lead version** (`--version lead`) for the documentation lead (director of technical documentation, content, or knowledge): issue categories, severity split, three selected issues with exact quotes, three "why it matters" lines.
- **Executive version** (`--version exec`) for a CIO or other executive: most of the page is business impact (three cards, each with a consequence and one piece of quoted evidence); the numbers appear as a compact stats line and issue-mix bar in the header.

HOP Audit fills the matching template and renders a one-page Letter PDF from the JSON you return; a build that overflows the page fails and comes back to you to trim. The approved Affirm data for each version is the model for the shape.

## Headlines and lead sentences

Headlines are the most important copy on the page and the hardest to get right. Write them fresh for each prospect. Don't reuse the Affirm headlines with the name swapped, and don't force a fixed sentence structure.

**Both versions:**
- Not critical of the prospect. No "you have issues" or "your help center is wrong". The findings make that point on their own.
- Incisive, pithy, compelling, easy to understand, and urgent, speaking directly to the heart of the value to the business.
- Never imply Heretto audits or scans content. Heretto structures and governs content; the audit is a one-off review we did.

**Executive headline:** no "you" or "your". Short enough to fit on one line where possible (about 45 characters). Approved Affirm example: "Regulated finance needs regulated content".

**Executive lead sentence:** `Structured content is critical to [imperative]; without it, [consequence].` Use a semicolon, not "because". Approved: "Structured content is critical to controlling risk; without it, the same terms read differently by page, by language, and in every AI answer." Follow it with the review sentence (articles reviewed, date, confirmed issues).

**Lead headline:** can address the reader ("you", "your team"). Center it on effectiveness: what the documentation lead's team could achieve with structured content, and what it can't keep up with today. It should make them think: with it, my team is more effective; without it, I'm exposed. Two lines via `headline_line1` / `headline_line2`. Approved Affirm example: "Your team can't be everywhere at once".

**Lead subhead:** one sentence on what structured content makes possible for the team, then the review sentence. Approved: "Structured content means a single fix made once will appear everywhere that content is used, in every language. A review of Affirm's public US and Canadian help centers on October 8, 2026 found 63 issues across 329 articles in English and French."

## Lead version fields

| Field | What goes in it | Length budget |
| --- | --- | --- |
| `prospect` | Company name | — |
| `prospect_logo` | Path to the prospect's logo file, or `null` for the labelled placeholder | — |
| `eyebrow` | `Content Integrity Snapshot · <Prospect> Help Center` | ≤ 55 characters |
| `headline_line1`, `headline_line2` | The lead headline, split over two lines | each ≤ 26 characters |
| `subhead` | What structured content makes possible + the review sentence | ≤ 260 characters |
| `stats` | 4 items `{value, label}`: confirmed issues, high severity, articles reviewed, help centers | labels ≤ 18 characters |
| `categories` | `{label, count}` per category with firm findings, sorted by count | labels ≤ 32 characters; max 9 rows |
| `severity` | `{high, medium, low}` of the firm findings | — |
| `examples` | 3 items: `severity` (High/Medium/Low), `where` (locale · type), `title`, `lines` (each `{label?, text, note?}`) | title ≤ 50 characters; ~3 lines of text each |
| `why` | 3 items `{lead, text}`, written per `business-imperatives.md` | ~95 characters each |
| `contact_name`, `contact_email` | Sender details, or leave the placeholders | — |
| `footnote` | Sites and date, items excluded, trademark/non-affiliation line | ≤ 230 characters |

Optional: `examples_heading` (default "What we found: selected issues"), `cta_title`, `cta_text`, `cta_button` (default "heretto.com").

## Executive version fields

| Field | What goes in it | Length budget |
| --- | --- | --- |
| `prospect`, `prospect_logo`, `contact_name`, `contact_email`, `footnote` | As above | — |
| `eyebrow` | `Executive Brief · <Prospect> Help Center Content` | ≤ 55 characters |
| `headline` | The executive headline | ~45 characters; 2 lines maximum |
| `lead_sentence` | `Structured content is critical to [imperative]; without it, [consequence].` | ≤ 160 characters |
| `review_sentence` | Articles reviewed, date, confirmed issues | ≤ 110 characters |
| `stats` | Same 4 items as the lead version | — |
| `mix` | The top 3 categories plus "Other" (the rest), `{label, count}` | labels ≤ 30 characters |
| `impacts` | 3 cards: `tone` (`risk` for Risk and AI risk, `cost` otherwise), `label` (e.g. "Regulatory risk", "AI risk", "Cost to serve", "Customer retention"), `title`, `body`, `evidence` | title ≤ 45 characters (one line); body ≤ 190; evidence ≤ 150 |
| `cta_title`, `cta_text` | Default in the example: "Worth 20 minutes to walk through what we found?" | — |

Impact cards: pick the three business consequences the findings support most strongly, Risk first when it applies (see `business-imperatives.md`). The card title states the consequence plainly; the body explains it for this prospect's business; the evidence is one or two exact quotes from the findings, with no commentary.

