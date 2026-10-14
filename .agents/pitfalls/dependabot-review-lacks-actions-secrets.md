---
id: dependabot-review-lacks-actions-secrets
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/37542266062
    observed_by: unknown
  - date: 2026-10-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/37543162270
    observed_by: unknown
  - date: 2026-10-14
    occurrence: https://github.com/endaye/lmdj/actions/runs/38503526013
    observed_by: claude-opus-5-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A Dependabot Pull Request's automatic PR Review run cannot read Actions secrets, so every review backend reports `missing_credential` and the run fails without reviewing anything.

## Why

GitHub runs workflows triggered by `dependabot[bot]` with the Dependabot
secret store instead of the repository's Actions secrets. `pr-review.yml` reads
`PR_AGENT_DEEPSEEK_API_KEY` and `PR_AGENT_ZAI_API_KEY` from Actions secrets.
The Dependabot store is empty, so both keys arrive as empty strings. DeepSeek
and GLM then both report `missing_credential`. Nothing is wrong with the keys,
the review host or the head. This happened on #1611, #1850 and #2191. Each time
it looked like a backend outage, and #2191 merged on an owner waiver even
though a real review could have run.

## How to apply

Absorbed into `issue-done` §5 step 2: for a Dependabot Pull Request, have the
repository owner dispatch the review for the unchanged head
(`gh workflow run pr-review.yml -f pr_number=<N>`). A dispatch from `main`
runs as the owner and reads Actions secrets. Then poll `review_wait`. Do not
waive review on the strength of this failure. Do not copy the review keys into
Dependabot secrets as a workaround without the owner's decision.
