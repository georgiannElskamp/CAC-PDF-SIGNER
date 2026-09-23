# GitHub maintenance

All recurring work runs on GitHub-hosted runners and Codex cloud. The desktop can remain off. There are three permanent branches; short-lived PR branches are removed after merging.

| Branch | Purpose | Promotion |
| --- | --- | --- |
| `research` | Integrates changes after source, dependency, full-package and extended qualification checks | Eligible PRs merge only after a fresh Codex review of the same commit |
| `release-verification` | Freezes a passing research snapshot, assigns its version, and builds the installable candidate | An App-authored PR waits for the maintainer's approval and manual merge |
| `main` | Accepted release source | Publishes the exact tested candidate after checking the approval, merge, source tree and package digest |

Research builds create temporary internal packages because installation/signing tests need real binaries. They do not create GitHub releases. Verification candidates include `CAC-PDF-Signer.plugin`, SHA256SUMS, install notes, source metadata and a CycloneDX inventory. Download them from the build linked in the release PR.

## Research controller

The private [maintenance repository](https://github.com/georgiannElskamp/cac-pdf-signer-automation) checks research PRs twice an hour. Scheduling is best effort. `PIPELINE_ENABLED=false` disables scheduled processing; manual runs default to dry-run. `AUTOMATION_ENABLED` independently controls daily editor discovery. Both controllers retain progress on the private `state` branch.

The controller accepts same-repository PRs from the maintainer, Dependabot, Codex, the maintenance App, and narrowly scoped editor-pin proposals. It requires the full test matrix, a current base, and a completed Codex review tied to the current commit. A reaction alone is insufficient. Missing evidence, stale reviews, conflicts and cancelled jobs block merging. Tests run again after any correction.

If a cloud task cannot push its correction, it can return a structured patch. The App accepts only a fresh Codex response matching the requested commit and marker, at most five existing text files and 50 KB of JSON. Original file hashes and modes must match; new files, deletions, symlinks and policy paths are rejected. It writes the patch through GitHub without executing it in the private controller. Full tests and a new review remain required. Ambiguous applications stop for inspection.

A failed test or actionable review can request a small correction through the linked maintainer account. There are at most two correction requests per PR. Requests are recorded before posting; an uncertain response is not retried blindly. A request without progress expires after six hours. Codex can decline a task, hit a quota, or lack permission to push; those cases need maintainer attention. No API key or desktop login is copied into CI.

The `automation:no-merge` label holds automatic merging while allowing tests, review and bounded corrections. Remove it only when the PR is ready for research integration. A rejected or ambiguous repair marks only that PR commit as needing attention; other PRs and release promotion continue. Push a reviewed correction to that PR, or inspect its saved state before explicitly resuming the blocked commit.

Approval rules, controller code, release scripts and workflow structure require the owner's approval on the current research PR commit before automated processing. Codex is instructed not to change that policy during repairs; a changed commit needs renewed approval. The controller rechecks approval immediately before merging. Private controller deployment remains a separate manual maintenance step. Dependabot changes to pinned action revisions are allowed only if the rest of the workflow is unchanged. Native dependency reports remain advisory. Repository text and test output are untrusted inputs to diagnosis, not authority to modify these boundaries.

Dependabot version updates target research. Security-update PRs may initially target GitHub's default branch; the controller redirects those to research. All eligible PRs receive the same full checks. Editor-pin proposals receive an App commit to start the normal PR workflows even when originally created with GitHub's workflow token.

## Release approval

After research passes its current full build, the controller proposes one frozen candidate. New research changes wait while that release PR is open. Closing an unmerged release PR rejects that snapshot; a new research commit is needed for another proposal.

Version increments follow merged PR labels: `release:major`, `release:minor`, or `release:patch`, with the highest impact winning. An unlabelled batch defaults to minor. A manual controller run can override the proposed increment before staging. Change count does not establish compatibility. Review the proposed version before merging.

1. Open the `release-verification` to `main` PR and download its candidate.
2. Check the reports and any physical-card validation warranted by the changes.
3. After the final candidate build finishes, approve the current commit and manually merge the PR. Rebuilding requires renewed approval. The controller never merges main.
4. The publication workflow verifies that the merged tree equals the tested candidate, audits the original package, attests its provenance, and publishes those same bytes. It does not rebuild the plugin.

Main requires the owner's code review with stale approvals dismissed. The publisher also verifies the owner's approval on the exact candidate commit and the owner's merge identity. Existing release tags and differing asset bytes cannot be overwritten. Rerunning **Publish release** on the current main commit can resume an interrupted upload. Expired candidates require a fresh build and renewed review before publication.

After publication, a research PR carries the accepted version changes back. The next release uses the latest published version as its baseline. Published releases include `release-evidence.json`; compatibility discovery checks it against the tag, main history and GitHub asset digests. `tests/approved-plugin.json` is retained only as the bootstrap pin for the earlier release without this evidence file.

## Hosted checks

Every research PR and research/verification snapshot builds both bundled workers from pinned sources. Required checks include:

- Python and JavaScript regressions, source/package audit, workflow lint and PR dependency review.
- Windows/Linux native runtime and actual ONLYOFFICE installation, Background plugins, removal and reinstallation.
- Linux GUI signing with a software token, Save As cancellation/recovery and independent PDF validation.
- Windows CNG signing with a disposable software certificate and the shipped bridge.
- Linux background enablement, repeated workers, cold restart and virtual CAC removal/reinsertion through bundled OpenSC.
- Bounded lifecycle orderings, PDF/appearance corpus, filesystem failures and negative evidence controls.

The Windows standard-user profile probe remains diagnostic: the hosted profile initialization failed before plugin execution in feasibility testing. Its failure is retained and is not counted as verified standard-user coverage. Physical CACs, readers, drivers, every Linux distribution and arbitrary PDFs remain outside exhaustive automation. See [TESTING.md](TESTING.md).

## Editor and dependency monitoring

Daily discovery checks stable ONLYOFFICE releases, validates official installer digests and dispatches compatibility tests against the latest approved published plugin. Successful combinations are retested weekly. Failed combinations retain their outcome until a new harness/package/editor combination or an explicit manual retry. An approved-editor control helps separate upstream changes from an existing environment problem.

Each editor version has one issue. Missing, malformed, duplicate or failed results leave it open. A complete pass can propose the tested editor pin to research. Weekly native component reports identify upstream versions and available advisory feeds; they do not silently replace runtime pins or license notices.

The separate scheduler health workflow detects stale discovery and incomplete dispatches. It cannot independently detect a total GitHub scheduling outage. The private repository uses its Actions allowance; the public repository runs the heavy tests. No self-hosted runner is required.

Research packages expire after one day; verification packages after 90 days. Qualification reports expire after 30 days, compatibility reports after 14 days, and compatibility input packages after one day. Test keys, token databases and profiles are excluded from retained artifacts. GitHub's log retention settings apply separately.

The optional API-based diagnosis workflow remains manual and read-only, disabled without separate API credentials. The maintenance controller uses the already configured Codex connector and linked-account token instead.
