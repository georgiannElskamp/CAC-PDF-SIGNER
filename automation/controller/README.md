# CAC PDF Signer scheduler

Private GitHub-hosted release discovery and health checks. All editor tests and builds run in the public [plugin repository](https://github.com/georgiannElskamp/CAC-PDF-SIGNER).

## Setup

1. Create an owner-only GitHub App with **Actions: read and write**, webhooks disabled, and no other requested permissions. Install it only on `CAC-PDF-SIGNER`.
2. In this repository's Actions variables, set `APP_ID` to the App ID.
3. Generate an App private key and store its complete contents as the Actions secret `APP_PRIVATE_KEY`. Do not commit the key.
4. Set the Actions variable `AUTOMATION_ENABLED` to `true`.
5. Run **Discovery** manually, then **Scheduler health** after discovery and compatibility tests finish.

Discovery runs daily at 08:23 UTC. Health runs at 11:41 UTC. GitHub schedules are best effort. State is stored on the `state` branch. The scheduler processes up to three unseen releases per poll and rechecks successful combinations after seven days. Failed tests require review; they are not repeatedly retried.

Use **Discovery > Run workflow > Retest completed combinations** after resolving a failure. An ambiguous dispatch is preserved for reconciliation. Check its run before removing an unresolved record from `state.json`.

No desktop agent, self-hosted runner, webhook server or connection to a personal computer is used. The scheduler uses private-repository Actions minutes; heavy tests use standard public-repository runners. Optional AI diagnosis is configured separately in the public repository.

Workflow templates and scheduler tests are maintained in the public repository's `automation/controller/` directory. Copy reviewed changes here; never copy secrets back into source.
