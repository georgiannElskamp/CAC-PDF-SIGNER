# GitHub maintenance

All scheduled work runs on GitHub-hosted runners. No desktop automation, WSL installation or self-hosted runner is required.

## Workflows

- **ONLYOFFICE compatibility** downloads the approved plugin from `tests/approved-plugin.json`, verifies its checksum and corresponding release source, and tests an official Desktop Editors release. Its reports distinguish installation, worker startup and simulated signing. It does not change the approved editor pin or published plugin.
- **Checks** runs Python and JavaScript regression tests on Windows and Linux.
- **Dependency review** rejects new high/critical dependency vulnerabilities in pull requests. Dependabot proposes weekly Python and GitHub Actions updates.
- **Publish release** requires maintainer approval through the `release` environment after validation.

The private [scheduler](https://github.com/georgiannElskamp/cac-pdf-signer-automation) polls daily and checks its own health in a separate workflow. Install the scheduler App and configure its credentials before enabling it. See its README for setup. The public repository does not need a recurring schedule or artificial keepalive commits.

Run **Actions > ONLYOFFICE compatibility > Run workflow** to test a stable editor tag such as `v9.4.0`. Leave the discovery fingerprint blank for a manual run. Reports and synthetic previews expire after 14 days. Token databases and keys are never uploaded.

Passing automation does not establish physical CAC or reader compatibility. The accepted hardware evidence remains the recorded Windows validations; Linux signing uses a software token. A failed baseline control indicates an environment, harness or existing-plugin problem that needs investigation before attributing the failure to a new editor.

Implementation and acceptance checks are in progress. The [plan](AUTOMATION_PLAN.md) describes the remaining build, component-watch and optional diagnosis stages; their presence in the plan is not a claim that they have passed validation.
