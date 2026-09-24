# Build and release

Run commands from the repository root. Keep Python environments, native build directories and generated packages outside the checkout. End users install the finished `.plugin` file and do not need these tools.

For a build that needs no local toolchain, use GitHub's **Build candidate** workflow. It builds both workers, validates the package, and provides the installable artifact. The `release-verification` PR carries a frozen candidate to the maintainer for approval; merging it into `main` publishes those exact bytes. See [GitHub maintenance](AUTOMATION.md#build-and-release-from-github).

## Windows worker and combined package

Use Windows x64 and the official CPython 3.11.9 distribution. Create a virtual environment outside the checkout and obtain `pdfsign-bridge.exe` from the upstream [v0.1.0 release](https://github.com/192d-Wing/pdf-sign/releases/tag/v0.1.0).

```powershell
python -m pip install -r requirements-build.txt
python -B tools/build_standalone.py --output ..\standalone-build --bridge ..\pdfsign-bridge.exe --linux-bundle ..\linux-bundle
```

The Linux bundle must be built first. The combined builder checks the bridge and license hashes, DLL inventory, dependency imports and both runtime manifests. It writes `CAC-PDF-Signer.plugin` and `SHA256SUMS.txt` outside the checkout.

`--reuse-executable` only repackages assets and source when the frozen worker's input hashes still match. Runtime code, dependency, build-tool or font changes require rebuilding the worker. Documentation-only changes can reuse a matching worker.

The build limits native-library lookup to Python and Windows directories. Windows supplies the Universal CRT and API-set libraries. Changes to Python, OpenSSL or native libraries require reviewing their notices and pinned inventory.

## Linux worker

Build in isolated x86_64 Linux with glibc 2.28 and GCC 8.3 or a compatible compiler. `native_linux/runtime.json` pins Python. Install both `requirements-build.txt` and `requirements-linux.txt`, plus Meson and Ninja, into its environment. This uses the same PyInstaller pin as Windows. Native build tools include make, pkg-config, flex, autoconf, automake, libtool, Perl and binutils (`readelf`).

Download the archives listed in `native_linux/sources.json` into `/opt/src`, then run `sh native_linux/build_middleware.sh`. The script verifies source checksums and builds into `/opt/native`. `CAC_NATIVE_PREFIX`, `CAC_NATIVE_SOURCES` and `CAC_NATIVE_WORK` can select other absolute paths. Use fresh output and work directories.

```sh
python -B tools/build_linux.py --output /opt/linux-bundle --prefix /opt/native --sources /opt/src --work /opt/freeze-work
```

The builder checks every ELF file for CPU architecture and required glibc symbols. Newer distributions may select incompatible wheels; use wheels matching the glibc 2.28 baseline. Successful imports on a newer build machine do not prove baseline compatibility.

Copy `linux-bundle` to the Windows build machine for the combined build. Required native source archives and the private PC/SC adaptation accompany the package. Both runtime manifests bind native payloads to their runtime source, dependencies and fonts.

## Test and publish

Follow [TESTING.md](TESTING.md) before submitting a research PR. `release/` is local build output and stays out of Git. The normal publication path is the three-branch GitHub workflow: qualified changes enter `research`, a frozen `release-verification` candidate waits for the owner's review, and an approved merge into `main` publishes the same tested package bytes. See [GitHub maintenance](AUTOMATION.md).

The release publisher verifies the source tree, native manifests, checksum, owner approval and artifact identity before creating or resuming a GitHub release. It does not rebuild after approval. Existing release assets and tags are immutable; changed source requires a new candidate and version. Editor installer pins in `tests/editor-installers.json` are test dependencies, not part of the plugin.
