# GitHub maintenance

All scheduled work runs on GitHub-hosted runners. No desktop automation, WSL installation or self-hosted runner is required.

## Workflows

| Workflow | Trigger | Result |
| --- | --- | --- |
| ONLYOFFICE compatibility | Scheduler or manual | Tests the approved plugin, updates one issue per editor release and proposes a draft editor-pin PR when appropriate |
| Checks | Push, PR or manual | Python and JavaScript regression tests on Windows and Linux |
| Dependency review | PR | Rejects newly introduced high/critical dependency vulnerabilities |
| Bundled component watch | Weekly scheduler dispatch or manual | Reports custom native version changes, recent upstream advisory feeds and a component inventory |
| Build candidate | Manual | Builds both workers, packages one plugin and validates installation and simulated signing |
| Prepare release draft | Manual, successful candidate run ID | Stages the exact tested bytes under a new version and starts release checks |
| Publish release | Manual dispatch from draft preparation | Rechecks the draft and waits for maintainer approval before publication |
| Diagnose compatibility failure | Manual, optional API setup | Produces a read-only Codex investigation report on a hosted Linux runner |

Dependabot proposes weekly Python and GitHub Actions updates. Native version reports are advisory; they do not replace runtime pins or regenerate license notices automatically.

The private [scheduler](https://github.com/georgiannElskamp/cac-pdf-signer-automation) polls daily and checks its own health in a separate workflow. Install the scheduler App and configure its credentials before enabling it. See its README for setup. The public repository does not need a recurring schedule or artificial keepalive commits. The private jobs use its included Actions allowance; standard public jobs run the heavier tests. Schedules are best effort, and the GitHub health check cannot independently detect an outage of all GitHub scheduling.

Run **Actions > ONLYOFFICE compatibility > Run workflow** to test a stable editor tag such as `v9.4.0`. Leave the discovery fingerprint blank for a manual run. The workflow downloads the unchanged asset pinned in `tests/approved-plugin.json`; the package audit uses its immutable source commit. Candidate installer checksums come from official release metadata. Missing assets, mismatched hashes and incomplete results fail closed.

Windows and Linux checks install the editor, confirm Background plugins, start the worker, remove the plugin and reinstall it. The Debian 12 test builds its own software-token provider, generates disposable keys, clicks the visible signature field, handles PIN and Save As, cancels and retries saving without signing again, verifies the PDF independently and checks the rendered certificate text. A separate no-card control starts the bundled reader stack without system OpenSC or PC/SC services. Source tests cover sizing, rotation and ambiguous/already-signed fields; those cases are not all separate GUI tests.

Failures run an approved-editor control and update the same tracking issue. A failure is not retried into a pass. The private scheduler reconciles dispatch results, preserves ambiguous dispatches and retests successful combinations after seven days. Main-source or installer changes create a new test combination. Read the recorded runner image when comparing weekly results.

Reports and synthetic previews expire after 14 days; compatibility input packages expire after one day. Token databases, keys and test profiles are excluded from uploads. Workflow log retention follows GitHub repository settings.

Passing automation does not establish physical CAC or reader compatibility. The accepted hardware evidence remains the recorded Windows validations; Linux signing uses a software token. A failed baseline control indicates an environment, harness or existing-plugin problem that needs investigation before attributing the failure to a new editor.

## Build and release from GitHub

1. Merge a reviewed change with a new version in the plugin and worker configuration and release notes.
2. Run **Build candidate** on `main`. Both builds work without desktop-produced bundles or warm caches. The Linux build verifies its glibc 2.28 ceiling. The `candidate` artifact includes the `.plugin`, checksum, install notes, source metadata and a CycloneDX component inventory.
3. After all candidate checks pass, run **Prepare release draft** with its run ID. A published version cannot be reused. Existing draft bytes and tags must match; the workflow never overwrites them.
4. Review the release checks and approve the `release` environment in GitHub. Publication carries the tested bytes forward. Any physical-card validation required by the change remains a maintainer decision.

After approving a new plugin release, update `tests/approved-plugin.json` with its immutable commit and asset hash so future compatibility runs test that release. This pin does not follow an arbitrary latest download automatically.

## Optional diagnosis

Store a dedicated OpenAI API key as the public repository's `OPENAI_API_KEY` secret, configure its API usage controls, then set `CODEX_ENABLED=true`. The desktop subscription and desktop authentication are not used. The workflow accepts only failed compatibility runs from trusted `main` history, makes one diagnosis attempt with a 15-minute job limit, and has no code-write or release permissions in the agent job. A time limit is not a monetary spending cap.

Diagnosis is initially manual and read-only. Automatic agent-generated repair PRs are deferred until the diagnostic workflow has been exercised with configured API access. Editor-pin PRs are deterministic and do not use Codex. No workflow auto-merges PRs or publishes releases without the maintainer gate.

## Coverage limits

The component inventory records declared Python/native sources and font/SDK hashes; it is not a binary reachability analysis or an exhaustive native vulnerability scan. The watch reports supported upstream versions and published repository advisory feeds. Fonts, Python subcomponents, Microsoft/GCC runtimes and the bridge's embedded Go dependencies still need manual advisory review. See [third-party notices](../THIRD_PARTY_NOTICES.md).

The [implementation checklist](AUTOMATION_PLAN.md) records remaining setup and acceptance work.
