# SEO and metadata checklist

HOP Audit records these checks mechanically for every page. You review the failures, explain what matters, and draft replacements.

| Check | Pass |
| --- | --- |
| Title | Present, unique on the site, 30–60 characters, leads with the page's subject, ends with the site name if the site does so consistently |
| Meta description | Present, unique, 70–160 characters, says what the reader can do on the page |
| Canonical | Present, absolute, points at the page itself or its preferred duplicate, same locale |
| H1 | Exactly one, matches the title's subject |
| Heading order | No skipped levels (H2 → H4) |
| Images | Every informative image has alt text that says what it shows; decorative images have empty alt |
| Open Graph | `og:title`, `og:description`, and `og:image` on landing and overview pages |
| Indexable | No `noindex` on pages in the sitemap; `hreflang` alternates point at pages that point back |

## Drafting replacements

- Titles and descriptions must fit the limits above; count characters before proposing.
- Use the page's own vocabulary and the product's names as written on the page.
- Do not stuff keywords or repeat the site name in the description.
- Severity: High for `noindex` on sitemap pages, missing or duplicate titles on top-level pages, and broken hreflang; Medium for missing descriptions, canonicals and H1 problems; Low for alt text and Open Graph.
