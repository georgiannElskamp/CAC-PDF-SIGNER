# Release-test feasibility probes

Run only in disposable GitHub-hosted jobs on the test branch. These probes do not
publish a release or change the plugin. Candidate input is pinned to an already
tested artifact; generated keys and certificate-store entries stay in the disposable
runner. Reports distinguish source integration, shipped-runtime tests and hardware gaps.

The workflow runs selected lanes from commit markers: `[probe:all]`,
`[probe:core]`, `[probe:windows]`, `[probe:desktop]`, or `[probe:virtual]`.
Negative controls deliberately break a test copy or its data; production files are
never rewritten.
