# Triage tiers

Propose a tier for every finding. A person confirms each one before anything is counted or built; their judgment on what counts wins, and their calls are appended to your feedback memory.

## Tiers

**Firm (counted).** Two statements a customer would read as giving opposite answers for the same situation; instructions that can't all match the app; translation changes of meaning or missing content; broken links; published internal notes; retired-product content with no scope. Count these in every total.

Lean toward counting **inconsistent messaging** even when the two statements might be reconcilable by someone who knows the policy, if a customer reading both would get two different answers. Example: "may go to escheatment after 2 years" vs. "3–5 years depending on your state" was kept as Medium.

Watch for "may" vs. "doesn't": "late payments may lower your score" vs. "loans opened after April 1 are not affecting your score" gives a post-April customer opposite answers. Counted.

Overstatements that are false for part of the audience are firm, not judgment. Example: "shares your entire payment history with TransUnion" when TransUnion only gets plans after a date.

**Items for review (listed separately, not counted).** Correctness depends on internal policy you can't see. Typical cases:
- Two thresholds that may apply to different features
- A general promise next to an exception that may be disclosed at checkout
- "No extra interest on late payments" next to daily accrual on principal (no penalty rate, but more days of interest)
- Disclosure differences that may be rounding (0–31.99% vs. 0–32%), or two representative examples that may both be valid
- A partner list that may be scoped differently from a footer
- Text that reads like a drafting error but whose intent you can't confirm
- Layout inconsistency (an observation, not a defect)
- An instruction that looks wrong but may be intentional (e.g., "close your main account instead")

**Drop.** Petty or not an error:
- A promotion that ended a day or two before the audit
- A rate stated in an article with an "effective as of" date in the footer
- Statements that address different situations and are both true

## Recount

After triage, recount by category and by severity. The one-sheet and report must use the triaged numbers, not the audit's. Check that firm + review + dropped = the audit's total. Report the denominators as distinct articles per locale; when a language has two versions (e.g., `fr` and `fr_CA`), count distinct articles and mention the page count separately.

## Picking the one-sheet examples

Pick three, each understandable in five seconds by someone who doesn't know the product:
1. A customer-impact contradiction or reversal (a translation that says the opposite is ideal)
2. Something concrete and checkable (a wrong phone number, a wrong number in a timeline)
3. Something a documentation head will feel personally (internal notes published, a retired product still promoted)

Avoid examples that need policy knowledge to judge, anything in the review tier, and anything the prospect could fix in minutes and dismiss as trivial. Keep a backup example in case a quote doesn't verify.

