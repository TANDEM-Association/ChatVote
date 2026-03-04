<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# specs

## Purpose
Project specifications and test plans. Contains comprehensive E2E test scenarios covering all ChatVote user flows — landing, chat, authentication, i18n, donations, and more.

## Key Files

| File | Description |
|------|-------------|
| `chatvote-test-plan.md` | Full E2E test plan with detailed scenarios, steps, and expected outcomes for Playwright tests |
| `README.md` | Directory description |

## For AI Agents

### Working In This Directory
- Reference `chatvote-test-plan.md` when writing new E2E tests or understanding expected user flows
- Test plan maps test scenarios to specific spec files in `CHATVOTE-FrontEnd/e2e/`
- Seed data is defined in root `seed.spec.ts`

### Common Patterns
- Test scenarios are numbered hierarchically (1.1, 1.2, 2.1, etc.)
- Each scenario specifies the seed file, target test file path, steps, and expected outcomes

## Dependencies

### Internal
- `seed.spec.ts` (root) — seed data referenced by test plan
- `CHATVOTE-FrontEnd/e2e/` — Playwright test implementations matching this plan

<!-- MANUAL: -->
