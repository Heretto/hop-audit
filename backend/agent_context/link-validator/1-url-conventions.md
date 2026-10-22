# URL conventions and link triage

HOP Audit checks every link mechanically (status, redirect chain, anchor). You classify what it found and propose the fix.

## Kinds

- **Broken**: 4xx or 5xx at the end of the chain, a DNS failure, or a timeout on retry.
- **Redirect**: 3xx that resolves. One hop is fine for external links; internal links should point at the final URL.
- **Anchor**: the page resolves but the `#fragment` matches no `id` on it.
- **Wrong locale**: a link from one language or country site to another (`/de/` page linking to `/en/`, `.ca` to `.com`) when the target exists in the source's locale.

## Fixes, in order of preference

1. **Relink** to the current URL when the content moved (the redirect target, or the same title found elsewhere on the site).
2. **Redirect** at the server when many pages link to a moved URL.
3. **Restore** the target when it was removed by mistake (it is still in the sitemap, or other pages describe it as current).
4. **Remove** the link when the target is gone for good, and say what the sentence should point to instead.

Group findings by target URL so one fix is listed once with every page that links to it. Severity: High for broken links in procedures, downloads or contact and support routes; Medium for other broken links and wrong-locale links; Low for redirects and anchors.

Never report a link as broken because the site blocked the checker (403 with a bot wall, a login page): say it could not be checked.
