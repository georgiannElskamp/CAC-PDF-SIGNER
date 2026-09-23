# Release 0.8.0

Changes through research commit `83410abc67acc7a6763d504bc35497509eda1de1`.

- Complete research controller setup and permanent-branch guards (#14)

Release candidate **0.8.0** (minor).

Research snapshot: `83410abc67acc7a6763d504bc35497509eda1de1`.

This PR requires the maintainer's approval and manual merge. Automation will not merge it. The candidate is frozen while review is pending. New research changes wait for the next release.

The final candidate build is pending.

Coverage includes Windows hosted installation/CNG, Linux installation/restart, simulated CAC signing, PDF integrity/layout and recovery failures. Windows standard-user profile initialization remains a diagnostic limit; physical reader/CAC coverage is not established by simulation. See docs/TESTING.md.

After the approved merge, publication promotes the same tested bytes. If the candidate changes, tests and approval must be repeated.
