# Heretto look and feel

Taken from heretto.com's computed styles (October 2026) and approved by the user on the Affirm one-sheet. The one-sheet template already applies all of this; use these values only when making something new or adjusting the template.

## Colors

| Role | Hex |
| --- | --- |
| Hero background, darkest navy | #001322 |
| Headings on light, primary button text | #011627 |
| Gradient glow (hero, top right) | #14505f → #08303f → #001322 (radial) |
| Teal accent / primary button | #79ecdd |
| Teal mid (bars, checkboxes) | #2bb1a9 |
| Teal dark (links, Medium pill text) | #147a72 |
| Teal tint (Medium pill background) | #f0fdfa |
| Cranberry (High severity) | #ad4780, pill background #fbeef5 |
| Page background | #f8fafc |
| Light blue-grey surfaces | #edf3fa, #dde5f0 |
| Light text on dark | #c5d2e0 |
| Body text on light (darkened for print) | #3c4c66; muted #5b6b82 |
| Outlines and low marks | #b1bfd2 |

The site's own body text color is #70819a, which is too light for print; use #3c4c66.

## Type

The site uses **Satoshi** (headings weight 500 for large display lines, 700 for section headings). Satoshi isn't on Google Fonts, so documents use **Poppins** (400/500/600), the closest geometric sans available both locally (for PDF rendering) and on Google Fonts (for web canvases). Don't fall back to Arial/Liberation or a serif: the user called that "janky".

## Look

- Dark navy hero with a subtle teal radial glow, thin low-opacity teal arc lines, white display headline in weight 500, teal uppercase eyebrow.
- Content cards framed like the site's case-study cards: a light 1px outer frame (#dde5f0, radius 16px, ~7px padding) around a white inner card (radius 11px, faint shadow).
- Teal check-square icons for benefit points; pill-shaped severity chips; a teal pill "button".
- Mostly white and light grey below the hero; color is used sparingly.

## Logos

- `assets/heretto-wordmark.png`: navy wordmark, transparent background, for light backgrounds.
- `assets/heretto-wordmark-white.png`: white wordmark, for the dark hero.
- The prospect's logo goes in the "Prepared for" slot only if the user supplies the file and their marketing approves using it. Never draw or recreate a prospect's logo; without a file, leave the labelled placeholder.
