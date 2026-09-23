# CAC PDF Signer maintenance controller

Runs discovery, bounded Codex review/repair and research-to-release promotion on GitHub-hosted runners. Heavy tests run in the public [plugin repository](https://github.com/georgiannElskamp/CAC-PDF-SIGNER). Nothing runs on a personal computer.

## Credentials and controls

Install the maintenance GitHub App only on the public plugin repository. It needs Actions, Contents, Pull requests, Commit statuses and Workflows read/write permissions; Metadata read is implicit. Disable webhooks. After changing requested permissions, accept the installation update too.

Private Actions configuration:

| Setting | Kind | Purpose |
| --- | --- | --- |
| `APP_ID` | Variable | Numeric GitHub App ID |
| `APP_PRIVATE_KEY` | Secret | App authentication; never copy into source |
| `CODEX_TRIGGER_TOKEN` | Secret | Separately supplied linked-account GitHub token for Codex comments |
| `AUTOMATION_ENABLED` | Variable | `true` enables daily editor discovery |
| `PIPELINE_ENABLED` | Variable | `true` enables scheduled research processing/promotion |
| `HARNESS_BRANCH` | Variable | `research` after migration; defaults to `main` |

Start with the pipeline disabled. Run **Research and release controller** manually with dry-run enabled. After permissions, branch protections and a controlled research PR pass, enable scheduled processing. Dry-run posts no requests and writes no state. Manual runs can select one PR or propose a version increment.

The controller runs at minutes 17 and 47 each hour; discovery runs daily at 08:23 UTC and health at 11:41 UTC. Scheduling is best effort. Separate files on the private `state` branch record discovery and PR/candidate progress. Requests with uncertain acknowledgements require reconciliation, not blind retries. Two Codex correction requests per PR are allowed; stalled requests require maintainer attention after six hours.

Only eligible research PRs can merge automatically. Controller/approval/release-policy changes require manual maintenance. A versioned candidate is frozen on `release-verification`; its App-authored PR always waits for the owner's approval and manual merge into `main`. No controller path merges main. See the public [operation guide](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/blob/research/docs/AUTOMATION.md) for required checks and coverage limits.

Release notes include merged PRs whose merge commits are in research after the last accepted snapshot. The controller rejects an incomplete or diverged comparison instead of guessing from publication dates.

Use **Discovery > Retest completed combinations** only after investigating a failure. An approved editor control distinguishes environment/harness failures from new upstream behavior. Health detects stale discovery but cannot independently detect an outage of all GitHub scheduling.

Reviewed source templates live in `automation/controller/` in the public repository. Copy its Python modules and README to this repository's root and its workflow templates to `.github/workflows/`. No public PR code is executed in this repository with credentials. Changes here are not deployed automatically from public PRs.
