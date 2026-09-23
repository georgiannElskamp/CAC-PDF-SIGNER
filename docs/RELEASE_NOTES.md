# Release 0.8.1

Changes through research commit `0ae45e36b8237b8625dac46c9b67bd65bf9c2ae6`.

- Sync accepted release into research (#18)
- Fix publishing and resuming draft releases (#17)

Release candidate **0.8.1** (patch).

Research snapshot: `0ae45e36b8237b8625dac46c9b67bd65bf9c2ae6`.

This PR requires the maintainer's approval and manual merge. Automation will not merge it. The candidate is frozen while review is pending. New research changes wait for the next release.

The final candidate build is pending.

Coverage includes Windows hosted installation/CNG, Linux installation/restart, simulated CAC signing, PDF integrity/layout and recovery failures. Windows standard-user profile initialization remains a diagnostic limit; physical reader/CAC coverage is not established by simulation. See docs/TESTING.md.

After the approved merge, publication promotes the same tested bytes. If the candidate changes, tests and approval must be repeated.
