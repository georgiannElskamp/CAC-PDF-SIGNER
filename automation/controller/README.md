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
| `AUTOMATION_ENABLED` | Variable | `true` enables monthly editor and dependency discovery |
| `PIPELINE_ENABLED` | Variable | `true` enables scheduled research processing/promotion |
| `HARNESS_BRANCH` | Variable | `research` after migration; defaults to `main` |

Start with the pipeline disabled. Run **Research and release controller** manually with dry-run enabled. After permissions, branch protections and a controlled research PR pass, enable scheduled processing. Dry-run posts no requests and writes no state. Manual runs can select one PR or propose a version increment.

Maintenance runs on the 30th in America/Chicago time, with the last day of February as a fallback. Discovery starts at 01:17; two recovery starts are deduplicated by a durable claim. Controller passes run at minutes 17 and 47 from 02:00 through 20:00. Scheduled mutations stop at 21:00; the monthly report starts at 21:07. Scheduling and same-day completion are best effort. Separate files on the private `state` branch record discovery and PR/candidate progress. Requests with uncertain acknowledgements require reconciliation, not blind retries. Two Codex correction requests per PR are allowed; stalled requests require maintainer attention after six hours.

Public PR activity, completed tests and Codex replies can dispatch this controller with `event_wakeup=true`. These notifications require `PIPELINE_ENABLED=true`; explicit manual runs remain available when it is disabled. Notifications request a PR-only sweep because GitHub may replace a pending controller run with a newer one. They cannot discover dependencies or prepare a release. Set up the public `controller-dispatch` environment and its narrowly scoped Actions token using the [operation guide](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/blob/main/docs/AUTOMATION.md). The monthly schedule is the only polling fallback; configure and test the relay before cutover. No new credential belongs in source.

Only eligible research PRs can merge automatically. The `automation:no-merge` label stops automatic merging; passing evidence still clears `Research review` for manual web merging. Controller/approval/release-policy changes require manual maintenance. A versioned candidate is frozen on `release-verification`; its App-authored PR always waits for the owner's approval and manual merge into `main`. No controller path merges main. See the public [operation guide](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/blob/research/docs/AUTOMATION.md) for required checks and coverage limits.

Release notes include merged PRs whose merge commits are in research after the last accepted snapshot. The controller rejects an incomplete or diverged comparison instead of guessing from publication dates.

Use **Discovery > Retest completed combinations** only after investigating a failure. An approved editor control distinguishes environment/harness failures from new upstream behavior. Health detects stale discovery but cannot independently detect an outage of all GitHub scheduling.

Reviewed source templates live in `automation/controller/` in the public repository. Copy its Python modules, JSON tool pins and README to this repository's root, workflow templates to `.github/workflows/`, and `config/dependabot.yml` to `.github/dependabot.yml`. No public PR code is executed in this repository with write credentials. Changes here are not deployed automatically from public PRs.

## Dependency jobs and cutover

The discovery workflow runs Dependabot in separate read-only jobs, then validates pin-only output before creating public research PRs through the maintenance App. No App key or write token reaches the updater containers. Private workflow updates target their identical public source templates; deployment remains a separate maintainer step. Template drift blocks publication. The App stays installed only on the public repository, and Actions does not need permission to create private PRs.

1. Run discovery on the implementation branch with `dry_run=true`; inspect all three ecosystems and proposal validation.
2. Review the public policy/tests and deploy the matching controller source explicitly. Do not deploy arbitrary public PR content automatically.
3. Configure and test the public `controller-dispatch` environment credential. Keep native Codex PR reviews and user requests enabled. Keep Copilot review of new PRs; repeated push reviews are unnecessary.
4. Disable native Dependabot version PRs using the bundled configuration and automatic security-fix PR creation in repository settings. Keep security alerts and push protection enabled.
5. Verify the monthly cron definitions, timezone, February guard and report. Run a manual PR-only reconciliation to prove required statuses still complete between monthly windows.

Inspect the first live monthly run before relying on unattended completion. A failed scan or missing credential is reported; it never restores daily/hourly polling. An ambiguously dispatched job needs reconciliation, not an automatic replay. The CLI version and container digests in `dependency-tools.json` are maintenance dependencies, not plugin runtime dependencies.
