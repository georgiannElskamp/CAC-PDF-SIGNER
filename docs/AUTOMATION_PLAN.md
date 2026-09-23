# Automation acceptance

See [GitHub maintenance](AUTOMATION.md) for operation and safeguards.

The three-branch workflow replaces direct publication and draft preparation. Acceptance requires source-policy tests, a complete research build, a controller dry-run, an exercised research PR and a frozen verification candidate. Publication itself is tested only after the maintainer approves and merges a release PR; setup does not authorize that merge.

The previous feasibility checks established Linux restart/virtual CAC, Windows CNG, bounded lifecycle/PDF/fault coverage and negative controls. Hosted Windows standard-user profile creation failed before plugin execution and remains an explicit diagnostic limit. Physical-card coverage remains the maintainer's Windows validations.

The App needs Contents, Pull requests, Commit statuses, Workflows and Actions write permissions on the public repository. `APP_ID`, `APP_PRIVATE_KEY` and the separately supplied `CODEX_TRIGGER_TOKEN` remain in the private scheduler. No secrets belong in either checkout or a release artifact.

Enable `PIPELINE_ENABLED` only after the private controller and public branch rules have passed their setup checks. Enable `HARNESS_BRANCH=research` after the research workflows are available. There are no local scheduled tasks or services.
