# Extended qualification

These hosted tests consume the candidate built in the same workflow run and verify
its source commit and package hash. Core, CNG, Linux desktop/restart and virtual-CAC
lanes are required. The Windows standard-user experiment runs as a diagnostic;
its profile setup limitation is recorded and does not count as verified coverage.

Synthetic keys stay in disposable runners. Reports and synthetic previews are
retained for 30 days. The complete package is a temporary test build on research
and a review candidate on release-verification. Neither branch publishes releases.
