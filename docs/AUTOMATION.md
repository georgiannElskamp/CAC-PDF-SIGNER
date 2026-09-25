# GitHub maintenance

All recurring work runs on GitHub-hosted runners and Codex cloud. The desktop can remain off. There are three permanent branches; short-lived PR branches are removed after merging.

| Branch | Purpose | Promotion |
| --- | --- | --- |
| `research` | Integrates changes after source, dependency, full-package and extended qualification checks | Eligible PRs merge only after a fresh Codex review of the same commit |
| `release-verification` | Freezes a passing research snapshot, assigns its version, and builds the installable candidate | An App-authored PR waits for the maintainer's approval and manual merge |
| `main` | Accepted release source | Publishes the exact tested candidate after checking the approval, merge, source tree and package digest |

Research builds create temporary internal packages because installation/signing tests need real binaries. They do not create GitHub releases. Verification candidates include `CAC-PDF-Signer.plugin`, SHA256SUMS, install notes, source metadata and a CycloneDX inventory. Download them from the build linked in the release PR.

## Research controller

The private [maintenance repository](https://github.com/georgiannElskamp/cac-pdf-signer-automation) runs routine maintenance on the 30th in America/Chicago time, or the last day of February. Discovery and dependency updates start at 01:17. Two later kickoff opportunities recover a dropped schedule; a durable monthly claim prevents duplicate scans. Short controller passes at minutes 17 and 47 from 02:00 through 20:00 reconcile completed work. New scheduled work stops at 21:00, and the monthly report runs at 21:07. GitHub scheduling, external reviews and failing tests can prevent same-day completion; the report identifies unfinished work instead of treating it as passed.

`AUTOMATION_ENABLED` controls monthly discovery and dependency proposals. `PIPELINE_ENABLED` controls monthly and PR-event reconciliation. Manual workflows remain available, with dry-run enabled by default. Progress survives on the private `state` branch. Scheduled Codex work has a shared limit of 12 review requests and six correction requests per month, plus the existing two-correction limit per PR. An unchanged commit does not receive repeated requests.

Codex and Copilot reviews remain available for PRs and explicit requests throughout the month. The controller adopts supported automatic Codex evidence tied to the current commit before requesting another review. PR checks continue on changed code; redundant feature-branch push tests are removed.

The public **Research PR activity** workflow carries no credentials and runs no PR code. Its completion, test completion and relevant PR comments wake **Research controller wakeup** on the default branch. That workflow reads only `main`, rechecks the PR through GitHub's API, and dispatches a PR-only pass. It checks all eligible existing research PRs so coalesced notifications do not lose an approval, but cannot discover dependencies or stage a release. Configure and test the relay before removing the frequent polling fallback. Without its credential, native connector reviews and CI still run, but the required controller status needs a manual run between monthly windows.

To enable event notifications after these workflows reach `main`:

1. Create a public-repository environment named `controller-dispatch`. Use selected deployment branches and allow only `main`, with branch type (no tags).
2. Store `CONTROLLER_DISPATCH_TOKEN` as an **environment secret**, not a repository secret. Use a fine-grained token restricted to `cac-pdf-signer-automation`, with only Actions read/write and implicit Metadata read. Track its expiry and replace it before it expires. Do not use the maintainer's general token or the signing App's private key.
3. Deploy the controller template's `pipeline.yml` to the private repository, then set public variable `PIPELINE_WAKEUP_ENABLED=true`. Keep private `PIPELINE_ENABLED=true`.
4. Run **Research controller wakeup** for an open research PR and verify the private run and linked `Research review` status. Test approval and Codex completion notifications before relying on unattended merging.

GitHub's repository-wide native auto-merge remains disabled to preserve manual release merges. The private controller merges eligible research PRs automatically. Normal web merging is available when required statuses pass. A maintainer approval does not replace the `Research review` check. That check links to the controller run; an absent check means the PR has not yet been evaluated. For recovery, run the private controller with the PR number and dry-run disabled, then run it again after any pending tests or Codex review finish.

The controller accepts same-repository PRs from the maintainer, Dependabot, Codex, the maintenance App, and narrowly scoped editor-pin proposals. It requires the full test matrix, a current base, and a completed Codex review tied to the current commit. A reaction alone is insufficient. Missing evidence, stale reviews, conflicts and cancelled jobs block merging. Tests run again after any correction.

If a cloud task cannot push its correction, it can return a structured patch. The App accepts only a fresh Codex response matching the requested commit and marker, at most five existing text files and 50 KB of JSON. Original file hashes and modes must match; new files, deletions, symlinks and policy paths are rejected. It writes the patch through GitHub without executing it in the private controller. Full tests and a new review remain required. Ambiguous applications stop for inspection.

A failed test or actionable review can request a small correction through the linked maintainer account. There are at most two correction requests per PR. Requests are recorded before posting; an uncertain response is not retried blindly. A request without progress expires after six hours. Codex can decline a task, hit a quota, or lack permission to push; those cases need maintainer attention. No API key or desktop login is copied into CI.

The `automation:no-merge` label holds automatic merging while allowing tests, review and bounded corrections. Once tests and review pass, `Research review` succeeds and the maintainer can merge from the web. Remove the label to permit automatic integration. A rejected or ambiguous repair marks only that PR commit as needing attention; other PRs and release promotion continue. Push a reviewed correction to that PR, or inspect its saved state before explicitly resuming the blocked commit.

Approval rules, controller code, release scripts and workflow structure require the owner's approval on the current research PR commit before automated processing. Codex is instructed not to change that policy during repairs; a changed commit needs renewed approval. The controller rechecks approval immediately before merging. Private controller deployment remains a separate manual maintenance step. Dependabot changes to pinned action revisions are allowed only if the rest of the workflow is unchanged. Native dependency reports remain advisory. Repository text and test output are untrusted inputs to diagnosis, not authority to modify these boundaries.

Monthly dependency proposals target research. If an existing or manually requested Dependabot security PR targets main, a full controller pass redirects it to research. All eligible PRs receive the same full checks. Editor-pin proposals receive an App commit to start the normal PR workflows even when originally created with GitHub's workflow token.

## Release approval

After research passes its current full build, the controller proposes one frozen candidate. New research changes wait while that release PR is open. Closing an unmerged release PR rejects that snapshot; a new research commit is needed for another proposal.

Version increments follow merged PR labels: `release:major`, `release:minor`, or `release:patch`, with the highest impact winning. An unlabelled batch defaults to minor. A manual controller run can override the proposed increment before staging. Change count does not establish compatibility. Review the proposed version before merging.

1. Open the `release-verification` to `main` PR and download its candidate.
2. Check the reports and any physical-card validation warranted by the changes.
3. After the final candidate build finishes, approve the current commit and manually merge the PR. Rebuilding requires renewed approval. The controller never merges main.
4. The publication workflow verifies that the merged tree equals the tested candidate, audits the original package, attests its provenance, and publishes those same bytes. It does not rebuild the plugin.

Main requires the owner's code review with stale approvals dismissed. The publisher also verifies the owner's approval on the exact candidate commit and the owner's merge identity. Existing release tags and differing asset bytes cannot be overwritten. Rerunning **Publish release** on the current main commit can resume an interrupted upload. Expired candidates require a fresh build and renewed review before publication.

After publication, a research PR carries the accepted version changes back. The next release uses the latest published version as its baseline. Release notes select merged research PRs by commit ancestry since the last accepted research snapshot, so later synchronization PRs are included. Published releases include `release-evidence.json`; compatibility discovery checks it against the tag, main history and GitHub asset digests. `tests/approved-plugin.json` is retained only as the bootstrap pin for the earlier release without this evidence file.

## Hosted checks

Every research PR and research/verification snapshot builds both bundled workers from pinned sources. Required checks include:

- Python and JavaScript regressions, source/package audit, workflow lint and PR dependency review.
- Windows/Linux native runtime and actual ONLYOFFICE installation, Background plugins, removal and reinstallation.
- A real ONLYOFFICE form-box click, card-free preparation, and a standard signature field in the review PDF, with source-page comparison against the editor's loaded snapshot.
- Linux GUI signing with a software token, Save As cancellation/recovery and independent PDF validation.
- Windows CNG signing with a disposable software certificate and the shipped bridge.
- Linux background enablement, repeated workers, cold restart and virtual CAC removal/reinsertion through bundled OpenSC.
- Bounded lifecycle orderings, PDF/appearance corpus, filesystem failures and negative evidence controls.

The Windows standard-user profile probe remains diagnostic: the hosted profile initialization failed before plugin execution in feasibility testing. Its failure is retained and is not counted as verified standard-user coverage. Physical CACs, readers, drivers, every Linux distribution and arbitrary PDFs remain outside exhaustive automation. See [TESTING.md](TESTING.md).

## Editor and dependency monitoring

Monthly discovery checks stable ONLYOFFICE releases, validates official installer digests and dispatches compatibility tests against the latest approved published plugin. At most three editor combinations run per discovery pass. Untested combinations take priority, newest version first; remaining slots rotate passing controls by their last tested month. The closing report lists deferred combinations. Failed combinations retain their outcome until a new harness/package/editor combination or an explicit manual retry. An approved-editor control helps separate upstream changes from an existing environment problem.

Each editor version has one issue. Missing, malformed, duplicate or failed results leave it open. A complete pass can propose the tested editor pin to research. Monthly native component reports identify upstream versions and available advisory feeds; they do not silently replace runtime pins or license notices.

The dependency job uses the official Dependabot CLI and pinned updater images. Its read-only scan groups Python and GitHub Actions updates, including the private controller's Actions. A separate job accepts only version changes to existing requirements entries or commit-pin changes in existing workflows. It never executes updater output or force-pushes an existing PR. Conflicting bases, unexpected edits and ambiguous interrupted proposals require attention.

These are code updates: proposals change the lockfile and runtime/build/test requirements consumed by worker builds. They must pass dependency review, Windows/Linux builds, signing/install tests and Codex review before research integration. A failed resolution or build blocks integration. Private controller workflow updates are proposed against identical public source templates and require separate maintainer review and deployment; template drift blocks the proposal. This avoids giving the updater private workflow-write access. Only one proposal per ecosystem remains open at a time.

Native libraries, CPython, the Windows bridge, SDK and license inventories remain explicit component-review items. Their report identifies newer releases and advisories; it does not blindly replace archives or hashes. The monthly report links those findings. The Dependabot CLI/image pins also need reviewed refreshes as the upstream engine evolves.

Native Dependabot version-PR creation is disabled in both repositories to avoid duplicate schedules. At cutover, disable automatic Dependabot security-fix PR creation separately, while retaining vulnerability alerts, secret scanning and push protection. Existing Dependabot PRs may continue automatic rebases temporarily. GitHub-managed alerts can arrive outside the window; they do not start a full maintenance batch.

The closing workflow creates a private monthly review issue with dependency/editor results, open PRs, component findings and incomplete work. Controller freshness requires a completed full pass and its successful workflow conclusion; PR-only notifications cannot satisfy it. It cannot detect a total GitHub scheduling outage. A report is not release approval: use the build/artifact evidence linked in the release PR before approving and manually merging main. The private repository uses its Actions allowance; the public repository runs the heavy tests. No self-hosted runner is required.

Research packages expire after one day; verification packages and qualification/compatibility/component reports after 90 days. Compatibility input packages still expire after one day. Test keys, token databases and profiles are excluded from retained artifacts. GitHub's log retention settings apply separately. Nothing recurring is installed on a desktop or WSL instance.

The optional API-based diagnosis workflow remains manual and read-only, disabled without separate API credentials. The maintenance controller uses the already configured Codex connector and linked-account token instead.
