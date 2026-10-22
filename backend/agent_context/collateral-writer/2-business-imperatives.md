# Why it matters: writing the business case

This applies to the lead version's three "why it matters" lines and the executive version's lead sentence and three impact cards (see `onesheet-data.md` for those formats).

The three "why it matters" lines on the one-sheet turn a list of content defects into a business problem. Write them yourself from the findings and what you know about the prospect. Don't ask the user for value props or which imperative applies. The point is that the person running the skill doesn't have to do this thinking.

## Context

Heretto usually explains itself through features that help the people who write content. Those people rarely approve the purchase; directors and executives do, and they care about what it costs the business when content goes wrong. The one-sheet should speak to that: what these findings mean for the business, not what a writer would like about a CCMS.

Heretto's positioning is moving from "a tool" to a governed, auditable system of record for content, which matters more as companies put AI assistants on top of their content.

## The four Business Imperatives

- **Risk:** fines, lawsuits, failed audits, or losing the right to sell
- **Customer Acquisition:** winning new customers or converting prospects
- **Customer Retention:** keeping and growing existing customers
- **Cost:** the cost of serving customers and running the business

AI is not a separate imperative. It's a way content failures reach customers at scale, so place AI points under Risk (an assistant gives a binding wrong answer; see Moffatt v. Air Canada, where the company was held to what its chatbot said) or Cost (deflection stalls because the content underneath isn't reliable).

## Mapping findings to imperatives

| What the audit found | Imperative it hits |
| --- | --- |
| Conflicting eligibility, rates, terms, disclosures, safety or regulatory content; legal text that differs across pages or languages | Risk |
| Wrong instructions, numbers, or timelines customers act on; translation errors in another market | Risk if regulated, otherwise Customer Retention |
| Content that will feed an AI assistant or chatbot (the prospect has one, or is building one) | Risk or Cost |
| Contradictions and outdated steps that generate support contacts | Cost |
| Gaps in non-English content; broken localized links | Customer Retention, or Customer Acquisition in a market they're entering |
| Public docs as part of evaluation (developer tools, PLG, API-first companies): outdated or contradictory getting-started content | Customer Acquisition |
| Published internal notes, retired products still promoted | Customer Retention (trust), or Risk if it exposes process or misleads |

## Writing the three lines

Pick the three imperatives the findings support most strongly for this prospect, in order of severity (Risk first when it applies). Each line is a short bold lead plus one sentence of consequence, about 95 characters total:

- **Lead:** two to four words naming what's at stake, in plain language ("Customers act on it.", "Much of it is regulated.", "AI assistants repeat it.")
- **Consequence:** what happens to the business, specific to the prospect's industry and grounded in the findings ("Eligibility, credit reporting, and refund terms differ between articles.")

Rules:
- Every line must trace back to actual findings. Don't claim a regulatory exposure the audit didn't touch.
- Concrete over vague: name the kind of content and the consequence, not "improves efficiency" or "enhances the customer experience".
- Plain language for an executive. No jargon, no marketing tone, no superlatives.
- Don't mention Heretto or CCMS in these lines; the call to action does that.
- Don't name the imperatives on the page; they're your framework, not the reader's.

## The value-prop library

`value-prop-library.md` holds the team's own examples by imperative. Treat it as context for how the team frames business consequences, not a list to choose from. When one fits the prospect's findings (for example, conflicting disclosures at a lender relate to Liability for AI answers), you can borrow its consequence and wording; otherwise write your own.

## Industry prompts

Use what you know about the prospect's industry to sharpen the consequence. Examples of what's at stake:
- **Financial services and lending:** disclosures and terms across markets and products; regulators, complaints bodies, and AI-servicing liability
- **Medical devices and life sciences:** instructions for use tied to device versions; FDA and EU MDR audits; recalls
- **Aerospace, industrial, automotive:** maintenance and safety content; certification and product liability
- **Software, developer tools, PLG:** docs as the sales channel; activation and conversion; support load
- **Telecom, consumer tech, multi-market consumer brands:** translated content across countries; support volume; consumer protection rules
- **Self-regulating bodies (sports, standards organizations):** rules published in several languages and editions; disputes when editions disagree

## Worked example (Affirm, approved)

Findings included conflicting credit-reporting and eligibility statements, wrong phone numbers and timelines, a reversed French AutoPay instruction, and a chatbot that answers policy questions from the help center. Lines:

- **Customers act on it.** Wrong steps, numbers, and timelines lead to failed payments and support calls. *(Customer Retention / Cost)*
- **Much of it is regulated.** Eligibility, credit reporting, and refund terms differ between articles. *(Risk)*
- **AI assistants repeat it.** Answers drawn from these articles inherit every conflict. *(Risk via AI)*
