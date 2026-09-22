# Automation implementation checklist

Approved design: GitHub-hosted execution only. The desktop may be powered off. Operational details are in [AUTOMATION.md](AUTOMATION.md).

## Delivered

- Private scheduler repository with daily discovery, weekly component dispatch, a separate health check and a durable state branch.
- Official editor release discovery with asset checksums, duplicate suppression, run reconciliation and explicit handling of incomplete results.
- Public Windows/Linux compatibility checks against the unchanged approved plugin, plus an approved-editor failure control.
- Reusable Debian 12 simulated-card harness, synthetic fixtures and independent PDF verification.
- Dependabot, dependency review, native component reporting and generated CycloneDX inventory.
- Cold-cache Windows/Linux worker builds and a combined candidate artifact, without desktop-built inputs.
- Runtime changes in PRs require full candidate builds and installation/signing checks.
- Hosted draft preparation and a maintainer-protected publication environment.
- Deterministic draft PRs for successfully tested editor pins.
- Optional, manual, read-only Codex diagnosis with separate API credentials and no release authority.

## Acceptance and setup

- [x] Windows and Linux source suites pass on GitHub.
- [x] Exact approved package audit passes against its release commit.
- [x] Published plugin installation, background startup, removal and reinstallation pass on both hosted platforms.
- [x] Both workers build from a cold cache on GitHub; the resulting package passes native/runtime, installation and simulated signing checks in the [full candidate run](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/actions/runs/35768968046).
- [x] Component watcher creates one report issue and identifies current Python/SDK review items.
- [x] Unit checks reject incomplete/mismatched release metadata, preserve uncertain dispatch intent and suppress duplicate dispatches.
- [x] Both repositories have zero self-hosted runners; no desktop automation was created.
- [x] Simulated GUI signing, Save As cancellation/retry, independent signature verification and signed-field reopening [pass](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/actions/runs/35768964456).
- [x] Scheduler App credentials are configured and daily monitoring is enabled. [Discovery](https://github.com/georgiannElskamp/cac-pdf-signer-automation/actions/runs/35771546090) and [Scheduler health](https://github.com/georgiannElskamp/cac-pdf-signer-automation/actions/runs/35771665985) pass.
- [x] Required PR checks pass; a regression test proves published versions are rejected before any release write.
- [ ] Configure an OpenAI API key and usage controls if optional diagnosis is wanted.

The released plugin is unchanged. Test containers, token databases and generated keys remain disposable CI data. Retained artifacts include only allowlisted reports, synthetic previews and candidate packages.

Automatic agent-generated repair PRs are deferred until the optional diagnosis workflow has been exercised. Physical CAC/reader checks, exhaustive native advisory matching and an independent watchdog for a full GitHub outage remain outside automated coverage.
