# Build and release

Run commands from the repository root. Keep Python environments, native build directories and generated packages outside the checkout. End users install the finished `.plugin` file and do not need these tools.

## Windows worker and combined package

Use Windows x64 and the official CPython 3.11.9 distribution. Create a virtual environment outside the checkout and obtain `pdfsign-bridge.exe` from the upstream [v0.1.0 release](https://github.com/192d-Wing/pdf-sign/releases/tag/v0.1.0).

```powershell
python -m pip install -r requirements-build.txt
python -B tools/build_standalone.py --output ..\standalone-build --bridge ..\pdfsign-bridge.exe --linux-bundle ..\linux-bundle
```

The Linux bundle must be built first. The combined builder checks the bridge and license hashes, DLL inventory, dependency imports and both runtime manifests. It writes `CAC-PDF-Signer.plugin` and `SHA256SUMS.txt` outside the checkout.

`--reuse-executable` only repackages assets and source when the frozen worker's input hashes still match. Runtime code, dependency or font changes require rebuilding the worker. Documentation and build-tool changes do not alter the signing runtime.

The build limits native-library lookup to Python and Windows directories. Windows supplies the Universal CRT and API-set libraries. Changes to Python, OpenSSL or native libraries require reviewing their notices and pinned inventory.

## Linux worker

Build in isolated x86_64 Linux with glibc 2.28 and GCC 8.3 or a compatible compiler. `native_linux/runtime.json` pins Python. Install `requirements-linux.txt`, PyInstaller 6.19.0, Meson and Ninja into its environment. Native build tools include make, pkg-config, flex, autoconf, automake, libtool, Perl and binutils (`readelf`).

Download the archives listed in `native_linux/sources.json` into `/opt/src`, then run `sh native_linux/build_middleware.sh`. The script verifies source checksums and builds into `/opt/native`. `CAC_NATIVE_PREFIX`, `CAC_NATIVE_SOURCES` and `CAC_NATIVE_WORK` can select other absolute paths. Use fresh output and work directories.

```sh
python -B tools/build_linux.py --output /opt/linux-bundle --prefix /opt/native --sources /opt/src --work /opt/freeze-work
```

The builder checks every ELF file for CPU architecture and required glibc symbols. Newer distributions may select incompatible wheels; use wheels matching the glibc 2.28 baseline. Successful imports on a newer build machine do not prove baseline compatibility.

Copy `linux-bundle` to the Windows build machine for the combined build. Required native source archives and the private PC/SC adaptation accompany the package. Both runtime manifests bind native payloads to their runtime source, dependencies and fonts.

## Test and publish

Follow [TESTING.md](TESTING.md). Put the final plugin, checksum and matching `INSTALL.txt` in `release/`. That directory stays out of Git; assets are distributed through GitHub Releases.

```sh
python -B tools/publish_release.py
```

This command checks the local release without changing GitHub. After review and validation, commit the source and run:

```sh
python -B tools/publish_release.py --publish
```

Publishing pushes the commit and version tag, uploads a draft and starts the release workflow. Publication requires Windows/Linux source tests, checks of both uploaded workers, installation tests in fresh editors, and an exact match between tagged source and packaged source. Editor installers and checksums are pinned in `tests/editor-installers.json`; they are test dependencies and are not shipped in the plugin.

Versions containing a hyphen are initially published as prereleases. A failed check leaves the release in draft. Retry an unchanged draft through **Actions > Publish release > Run workflow** with its tag. If source or package content changes after tagging, use a new version and tag. Do not replace published assets or move release tags.

After validation, an existing candidate can be marked as the current release in GitHub while retaining its tag and assets. Record the completed validation and accepted limits in its release notes. Documentation updates on the default branch do not change the tagged source or the documentation embedded in that artifact.
