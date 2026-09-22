# Compatibility and maintenance automation plan

Status: implementation approved. See [AUTOMATION.md](AUTOMATION.md) for deployed workflows, setup requirements and verified coverage.

## Recommendation

Run the entire maintenance pipeline on GitHub-hosted infrastructure. Use GitHub Actions to detect ONLYOFFICE releases, test compatibility and build candidates; Dependabot and dependency review to monitor supported dependencies; and the Codex GitHub Action for optional investigation and repair PRs. Keep publishing a replacement plugin under maintainer control.

**Execution requirement:** this PC can be powered off throughout discovery, testing, diagnosis, building and publication. Do not create Codex desktop automations, Windows scheduled tasks, local services, self-hosted runners, remote connections to this PC or WSL test installations. Reviews and release approvals happen through GitHub from any device. No recurring local execution is part of the design.

The normal outcome of a compatible ONLYOFFICE update should be a compatibility report, not a new plugin release. Rebuild the plugin only when its code, bundled dependencies or shipped content needs to change.

## Starting point

Reviewed on 2026-09-22 at repository commit `4c28ffbf040f987b7947968a0fe097306ebae39a`.

- The approved plugin is `v0.7.0-rc.6`. Its download SHA-256 is `e0af01f17b70c30efe4790ef01aa51c7b9105ba1c3a00d2e5f98f0a876b8f3e7`.
- The latest official Desktop Editors release is currently `v9.4.0`, matching `tests/editor-installers.json`. The Windows EXE and Linux DEB hashes match the repository pins. Monitor [Desktop Editors releases](https://github.com/ONLYOFFICE/DesktopEditors/releases), not the separate ONLYOFFICE Docs server product.
- `.github/workflows/checks.yml` runs source checks on Windows and Linux for pushes and pull requests.
- `.github/workflows/release.yml` tests uploaded draft assets, both workers and fresh editor installation before publishing. It validates prebuilt packages; it does not build both native runtimes from source.
- `tests/editor_ci.py` installs one pinned editor version on disposable GitHub-hosted runners. `tests/editor_smoke.js` checks installation, Background plugins, startup, preflight, removal and reinstallation. It does not sign a PDF.
- The adapter and smoke test both depend on internal PDF interfaces such as `jf`, `Mp` and `Vh`. A changed interface can break the plugin, the test harness, or both. The adapter's compatibility checks must remain intact.
- The fresh Debian simulated-card signing test succeeded, but its disposable harness was deleted with the test installation. It must be recreated as a maintainable test before it becomes a CI gate.
- The checkout has no upstream-release watcher or Dependabot configuration. GitHub security settings have not been audited as part of this planning task.

## Options

| Option | Best use | Limitation | Decision |
| --- | --- | --- | --- |
| Public-repository schedule | Detect upstream releases directly in the plugin repository | Can stop after 60 days without repository activity | Simplest setup, but needs occasional re-enabling through GitHub |
| Private GitHub scheduler plus public test workflows | Keep lightweight polling separate from the public repository's activity | Adds one private repository and cross-repository authentication | Recommended for unattended operation |
| Dependabot plus dependency review | Python and GitHub Actions updates and known-vulnerability checks | Does not understand this project's custom native-library and editor manifests | Add alongside the watcher |
| Codex GitHub Action | Investigate a confirmed failure and produce a patch on a GitHub-hosted Linux runner | Requires configured API authentication and an AI usage budget | Optional later phase; no desktop Codex dependency |
| Renovate custom managers | Track versions embedded in custom manifests | Additional configuration; still needs project-specific checksum, build and license handling | Alternative to custom tracking, not required initially |

Dependabot supports `pip` and commit-pinned GitHub Actions. Renovate supports custom managers for dependencies outside standard manifests. Use one updater per dependency family to avoid competing PRs. [Dependabot support](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories), [Renovate custom managers](https://docs.renovatebot.com/modules/manager/regex/).

## GitHub hosting design

Keep the plugin source and heavy test/build jobs in the existing public repository. Add a small private repository, provisionally named `cac-pdf-signer-automation`, containing only the scheduler and its operational state. The private repository is configured during implementation.

| Component | Runs or lives in | Purpose |
| --- | --- | --- |
| Daily release discovery and weekly native-dependency scan | Private repository, GitHub-hosted Linux runner | Poll official upstream sources and dispatch work only when needed |
| Scheduler health check | Separate daily workflow in the private repository | Detect a missing or failed discovery run and update one health issue |
| Windows editor/runtime tests and Windows worker build | Public repository, standard GitHub-hosted Windows runners | Test and build without this desktop's installed software |
| Linux editor/signing tests and Linux worker build | Public repository, standard GitHub-hosted Linux runners | Use disposable Debian containers and a pinned glibc-compatible build image |
| Optional Codex diagnosis | Public repository, isolated GitHub-hosted Linux job | Call the OpenAI API and produce a bounded patch |
| Reports, review and candidate downloads | GitHub issues, PRs, Actions artifacts and draft releases | Provide everything needed to review through GitHub |
| Final publication | Public repository, protected release job | Publish approved, already-tested bytes |

GitHub supplies and maintains hosted Windows and Linux machines, with a fresh VM per standard multi-CPU job. Select explicit OS image versions and record the actual runner image. Linux containers run on GitHub's runner, not in local Docker or WSL. The Debian GUI test will use its own virtual display and synthetic card. [GitHub-hosted runners](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners).

Use a GitHub App installation token for the private scheduler to dispatch `compatibility-test.yml` in the public repository. Grant the App Actions write permission only on that target repository; it needs no code or release write permission. Store its private key in the private repository's Actions secrets and mint short-lived tokens per run. A GitHub App used this way does not need a separately hosted webhook server. The target workflow independently validates supplied release IDs, hashes and allowed references. [GitHub App authentication in Actions](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/making-authenticated-api-requests-with-a-github-app-in-a-github-actions-workflow), [Workflow dispatch API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

Use the public repository's own job-scoped token for reports and draft PRs in separate publishing jobs. Test jobs receive no write credentials or OpenAI key. A dispatch acknowledgement is not a successful test: record the run ID and reconcile its completion on the next scheduler run. Keep all authoritative state on GitHub, with no local file, cache, authentication session or desktop callback required.

## 1. Detect new editors without changing the supported baseline

Create `compatibility-watch.yml` in the private scheduler repository, scheduled daily at an off-hour minute, with a manual Run workflow option. Dispatch `compatibility-test.yml` in the public repository for new combinations. Query the official release API; enumerate stable releases newer than the last processed release so missed days do not skip versions. Keep beta releases in an optional, non-blocking test lane.

Record the upstream release ID, tag, commit, platform asset IDs, asset hashes and update times. Download only the expected official Windows x64 EXE and Linux amd64 DEB. Verify each against the upstream digest or a separately published official checksum. If an asset is missing or has no verifiable digest, report an incomplete release and wait. A tag's existing asset changing must trigger a fresh review, not reuse an old pass. A checksum verifies the downloaded bytes against upstream metadata; it is not an independent guarantee that upstream is uncompromised. [GitHub release API](https://docs.github.com/en/rest/releases/releases).

Use a dedicated bot-managed state branch in the private repository for compact JSON discovery/results records, not commits to the plugin's `main` branch on every poll. Key results by editor asset hashes, plugin hash, OS image and harness commit. Update one public tracking issue per upstream release only when status changes. Preserve separate states for pending assets, environment failure, harness failure, plugin incompatibility and passed coverage. Add a concurrency lock and bounded retries for downloads; do not retry a deterministic signing failure into a pass.

Pass the discovered installer manifest into the test job as an artifact. Keep the approved `tests/editor-installers.json` pin unchanged until review. Refactor the test runner to accept that manifest and the plugin's independently supplied version, while retaining its disposable-runner restriction and host/asset validation.

GitHub documents automatic schedule disabling after 60 days of inactivity for public repositories. The private scheduler avoids that specific rule without artificial keepalive commits or a desktop monitor. Schedules can still be delayed or dropped, and account restrictions, exhausted allowances or GitHub outages can stop them. A daily polling target is not a notification SLA. [Scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The private repository's separate health workflow checks the last successful discovery run, flags a gap over 48 hours and reports dispatches with no completed result. Use one GitHub health issue and standard GitHub notifications. Both workflows depend on GitHub, so this is not independent outage detection; an outage of all GitHub scheduling cannot reliably report itself. A manual catch-up button remains available. A third-party cloud watchdog is an optional future improvement, not a requirement and never a fallback to this PC.

## 2. Test the artifact users actually install

Start each run with the approved published `.plugin`, downloaded and checksum-verified. Do not silently rebuild it with newer dependencies before testing compatibility. Keep a separate candidate lane for changes under review.

| Test layer | Initial coverage | Pass condition |
| --- | --- | --- |
| Source regression | Existing Python and JavaScript suites, Windows and Linux | Required tests pass; skips are reported |
| Packaged runtime | Both shipped workers, spaced Unicode paths | Runtime inventory, imports, startup and preflight pass |
| Fresh editor installation | New editor on explicit Windows/Ubuntu runner images | Native install, background listing, start, disable, remove and reinstall pass |
| Linux simulated signing | Clean Debian 12 environment with the compatible software-token provider | PIN, existing field, valid signature, appearance, Save As, cancel/retry and reopen pass |
| Windows synthetic signing | Existing software-provider and PDF-core tests initially | Signature math, layout and save/recovery checks pass; no claim of a full hardware path |
| Baseline control | Approved editor version when the new editor fails | Identifies runner/harness regressions versus new-editor incompatibility |

Hosted Windows runners are not a substitute for every Windows client installation. Keep the existing physical Windows validations as separately reported evidence. Further automate the native Windows PIN path only if a faithful test provider can be introduced outside the shipping plugin; never relax hardware-only certificate selection just to satisfy CI. Hardware coverage remains an explicitly separate, occasional manual activity, not a reason to install a runner or monitoring service on this PC.

Recreate the Linux test with a pinned, reproducible SoftHSM build compatible with the bundled C++ runtime. Generate all token keys, certificates and PDFs during the job. Use fictitious names and identifiers. Keep system OpenSC/PCSC absent in the private-reader check and confirm the signing process uses bundled Python and signing libraries. Install ONLYOFFICE's ordinary OS dependencies, including `libgbm1` where needed. Test-only tools and the simulator must never enter the plugin archive.

Separate editor discovery from adapter-specific inspection. Capture the actual editor build, plugin error and failing stage before interpreting a timeout. Add a UI-level check that the field is clickable; invoking an internal handler alone is insufficient to prove the user interaction still works. Do not treat simply removing the adapter fingerprint check as a compatibility fix.

Expand fixtures to wide, narrow, shallow, rotated and already-signed fields, ambiguous names, Unicode paths and Save As cancellation. Validate signature integrity independently of the signing library, verify the original file hash, and inspect appearance bounds and rendered output. Do not require byte-identical screenshots across OS font renderers; use text/bounds checks and review unexpected visual differences.

Persist a small JSON summary with stage results, versions, hashes and links. Retain sanitized logs and synthetic screenshots for 14 days. Exclude token databases, private keys, PINs and machine profiles from uploaded artifacts. Teardown must run on failure and timeout. Hosted tests must never access this PC's ONLYOFFICE install, files, CAC, existing WSL distributions or remote-control connections.

Audit a released package against its immutable release tag, not today's default branch: documentation has changed on `main` since the current artifact was packaged. For a new candidate, enforce exact correspondence with its own source commit.

## 3. Propose a repair only after a confirmed incompatibility

If the release passes, update the compatibility report and propose the new editor pin/documentation in a PR. Leave the plugin download unchanged.

If the new editor fails but the baseline passes, open or update one issue with reproduction steps and sanitized evidence. Distinguish adapter breakage from installer or test-harness problems before starting an agent.

Codex should receive a bounded task: reproduce the specific failure, inspect official upstream changes, make the smallest justified fix, and add a meaningful regression test. Give it no merge or release authority. It must not weaken signature verification, bypass adapter checks, suppress failures or broaden supported-platform claims to obtain a green result.

Use the official Codex GitHub Action on a disposable Linux runner. It calls the OpenAI API from GitHub; it does not require the Codex desktop app, an open chat, or this machine's login session. Start with a GitHub Run workflow action for diagnosis, then optionally allow a confirmed compatibility failure to dispatch the same job. Do not run an AI task on every uneventful poll.

Its documented setup uses an OpenAI key stored as a GitHub secret. Configure that credential and a usage budget separately from the desktop subscription; do not copy local Codex authentication files into CI. Set a job timeout and a limit on repair attempts. Run the agent without elevated privileges and with no repository write token in its process; use a separate controlled job to publish a draft PR. Keep Windows execution in ordinary test jobs. Treat logs and upstream text as evidence, not instructions. [Codex GitHub Action](https://learn.chatgpt.com/docs/github-action).

Permit the agent only on trusted, explicitly selected source commits and validated internal test results. It must not receive arbitrary public-PR code together with an API key. Tests of its proposed patch run afterward in fresh Windows/Linux jobs without AI or release credentials. All changes and review evidence stay on GitHub.

Use the same workflow's downstream jobs or explicit dispatch to validate the exact candidate SHA. Do not rely on an ordinary bot push to trigger CI: GitHub's token suppresses most follow-on events, while token-created PR runs can require approval. Start with that approval model for PR checks; the explicitly dispatched candidate tests still run without this PC. Do not broaden the scheduler App's permissions to grant it code or release write access. [Workflow triggering rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

## 4. Track dependencies separately from editor compatibility

Add `.github/dependabot.yml` for weekly `pip` updates at the repository root and weekly `github-actions` updates. Separate runtime/security-sensitive changes from test/build-tool updates. Keep major changes separate and cap open PRs. Confirm discovery of all four requirement files and their shared includes before relying on coverage.

Enable or verify the dependency graph, Dependabot alerts and security updates. Add the dependency review action as a required PR check, initially blocking new high/critical vulnerabilities and reporting lower-severity findings for review. It compares dependency changes; alerts cover known vulnerabilities already present. Neither proves that a new package works with the plugin. This action is available for public repositories. [Dependency review](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review).

Maintain a separate watch list for `native_linux/sources.json`, `native_linux/runtime.json`, the Windows bridge, bundled OpenSSL/C++ runtimes, fonts and vendored SDK files. Dependabot cannot infer these custom inventories as ordinary package dependencies. Start with explicit upstream version/advisory checks and issues; consider Renovate custom managers when tracking becomes repetitive. Generate a release component inventory/SBOM with exact versions and hashes, and document any components for which advisory matching is incomplete.

A runtime dependency PR must rebuild the affected native workers, regenerate manifests and notices, check redistribution/source requirements, and validate the combined `.plugin`. The existing builder deliberately checks exact Python/OpenSSL versions and license inventory: updating a requirement alone will not necessarily build successfully. Preserve the Linux glibc 2.28 compatibility check. Test tooling updates need the relevant CI checks, but do not automatically justify rebuilding a user artifact.

Keep ordinary public PR tests read-only and without release/API secrets. Do not use privileged `pull_request_target` execution of proposed code. Pin new actions to reviewed commits as the existing workflows do.

## 5. Build candidates and approve publication

Before unattended repair can produce a dependable installable artifact, add GitHub-hosted build jobs for the existing Windows and Linux builders. Use a pinned Linux build image that preserves the declared glibc baseline, verified middleware sources and the pinned Windows toolchain/bridge. Build images in GitHub Actions and, if retained, store them in GitHub's container registry. Every job must also work from a cold cache. No stage may require a bundle uploaded from this PC. Package the tested output once and carry the same bytes through validation and publication.

Retain the current release workflow's source/package/runtime checks. Add the new compatibility/signing suite for candidates. Generate a draft plugin, checksum, install notes and concise compatibility report. Release changes require a new version and tag; never overwrite the accepted artifact.

The current release workflow publishes automatically after its checks. A compatibility watcher must not invoke that publication path unattended. Put the final publish job behind a protected GitHub environment with a required maintainer reviewer, or use an explicitly invoked publication workflow if environment rules are unavailable. The public repository supports required-reviewer environments under GitHub's documented plan rules. For a sole maintainer, do not require a different person to approve a run that the maintainer started. Review and approval happen in GitHub; no local command is needed. Once approved, publish only the exact artifact that passed the gates and retains the matching source and dependency notices. [GitHub environment protection](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

For changes to card selection, cryptography or Windows middleware, request targeted Windows hardware validation before release. Keep Linux simulated signing as the accepted baseline unless physical Linux testing becomes available; automation cannot turn that into a hardware-compatibility guarantee.

## Delivery order and effort

| Stage | Deliverable | Relative effort |
| --- | --- | --- |
| 1 | Private GitHub scheduler, scoped dispatch credential, health check, public fresh-editor tests, result issue and manual catch-up | Medium; includes one-time GitHub setup |
| 2 | Dependabot, dependency review and component watch list | Small to medium |
| 3 | Reproducible Linux simulation, independent PDF/appearance checks and durable reports | Medium; recreate the deleted one-off harness |
| 4 | Fully GitHub-hosted builds for both runtimes, tested candidate artifacts and protected publication | Medium to large; highest build-environment risk |
| 5 | Optional Codex GitHub Action for diagnosis, then bounded draft repair PRs | Medium; separate API credential and budget |

Use standard hosted runners and run the expensive matrix only for a new editor/artifact combination, a candidate change or a scheduled baseline check. GitHub currently provides free standard-runner minutes for public repositories. The private repository's short scheduler and health jobs consume its included private-repository allowance; monitor that allowance and set spending controls before enabling overage. Artifact/cache storage and larger runners have separate limits or charges. Keep retention short. Codex-in-CI usage needs its own budget; no AI execution is required for release detection or deterministic tests. [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

One-time setup can be completed in GitHub's web interface: create the private repository, install the narrowly scoped GitHub App, add its secret, enable the public dispatch workflow, configure notifications and the release environment, and optionally add the OpenAI API secret. Secrets belong in GitHub settings, never in repository files or plugin artifacts. The maintainer approved implementation; API credentials remain a separate one-time setup.

## Acceptance criteria

- A manually supplied unseen editor release goes through the same path as scheduled discovery.
- The unchanged current plugin passes the approved-editor baseline; a deliberately incompatible adapter fixture produces a specific failure and one tracking issue.
- Missing platform assets, changed asset hashes, network failure and a broken harness cannot be reported as compatibility passes.
- Repeating a completed combination creates neither duplicate issues nor unnecessary builds.
- A stopped discovery workflow is flagged by the private GitHub health workflow; the shared GitHub-outage limitation is documented.
- A dependency PR cannot pass solely on source tests when shipped runtime bytes need rebuilding.
- A proposed fix is tested against both the new editor and the retained baseline before review.
- The final publication gate preserves the tested artifact hash and requires maintainer action.
- Every result distinguishes installation, simulated signing and physical hardware evidence.
- With this PC shut down and no self-hosted runners registered, a manual GitHub dispatch completes discovery, tests, a candidate build and the approved publication path.
- A cold-cache build succeeds using only versioned source, verified upstream downloads and GitHub-hosted resources.
- No workflow depends on a local drive, desktop Codex session, local WSL distribution, physical CAC or remotely reachable service on this PC.

The first useful milestone is Stage 1: detect a new ONLYOFFICE release, test the existing plugin and report the outcome. Automatic repair should follow evidence from that system rather than precede it.
