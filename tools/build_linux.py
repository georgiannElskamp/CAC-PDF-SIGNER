"""Freeze the native Linux worker and collect its redistributable components."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _paths import ROOT
from build_standalone import licenses
from runtime_config import VERSION, outside_checkout
from bundle_manifest import write_manifest


def verify_elfs(runtime, architecture, baseline):
    expected_machine = {"x86_64": 62, "aarch64": 183}[architecture]
    maximum = tuple(map(int, baseline.split(".")))
    count = 0
    for path in runtime.rglob("*"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            header = stream.read(20)
        if header[:4] != b"\x7fELF":
            continue
        if header[4:6] != b"\x02\x01" or int.from_bytes(header[18:20], "little") != expected_machine:
            raise ValueError("Wrong CPU architecture in Linux runtime: " + path.name)
        versions = subprocess.check_output(["readelf", "--version-info", str(path)], text=True)
        required = [tuple(map(int, value.split("."))) for value in re.findall(r"\bGLIBC_([0-9.]+)", versions)]
        if required and max(required) > maximum:
            raise ValueError(f"{path.name} requires a newer glibc than {baseline}. Build with baseline-compatible wheels and libraries.")
        count += 1
    if not count:
        raise ValueError("No native Linux executables were found.")
    return count


def build(output, prefix, sources, work):
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise ValueError("Build natively on 64-bit Linux.")
    output, work = outside_checkout(output), outside_checkout(work)
    runtime = output / "native" / ("linux-" + platform.machine())
    if runtime.exists() and any(runtime.iterdir()):
        raise ValueError("Use an empty output directory to avoid retaining old runtime files.")
    runtime.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-B", "-m", "PyInstaller", "--noconfirm", "--clean",
               "--onedir", "--console", "--noupx", "--name", "cac-signer",
               "--distpath", str(work / "dist"), "--workpath", str(work / "freeze"),
               "--specpath", str(work), "--collect-data", "pyhanko", "--collect-data", "tzdata",
               "--hidden-import", "pkcs11", "--hidden-import", "pyhanko.sign.pkcs11",
               "--add-data", str(ROOT / "fonts") + ":fonts"]
    for path in [prefix / "sbin/pcscd", prefix / "lib/opensc-pkcs11.so",
                 *sorted((prefix / "lib").glob("libpcsclite*.so.*"))]:
        if path.is_file() and not path.is_symlink():
            command += ["--add-binary", str(path) + ":."]
        elif path.name == "opensc-pkcs11.so":
            command += ["--add-binary", str(path) + ":."]
    drivers = prefix / "lib/pcsc/drivers"
    for path in drivers.rglob("*"):
        if path.is_file():
            target = "pcsc-drivers/" + path.relative_to(drivers).parent.as_posix()
            command += ["--add-binary" if ".so" in path.name else "--add-data", str(path) + ":" + target]
    command += [str(ROOT / "standalone_worker.py")]
    env = dict(os.environ, LD_LIBRARY_PATH=str(prefix / "lib"))
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    subprocess.run(command, env=env, cwd=work, check=True)
    # Dereference symlinks: Plugin Manager's ZIP extraction need not preserve them.
    shutil.copytree(work / "dist/cac-signer", runtime, dirs_exist_ok=True, symlinks=False)
    baseline = json.loads((ROOT / "native_linux/runtime.json").read_text())["glibcBaseline"]
    verify_elfs(runtime, platform.machine(), baseline)
    executable = runtime / "cac-signer"
    result = subprocess.run([str(executable)], input='{"op":"health"}\n', text=True,
                            capture_output=True, timeout=60, check=True,
                            env={k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"})
    events = [json.loads(line) for line in result.stdout.splitlines()]
    if not events or not events[-1].get("ok") or events[-1].get("version") != VERSION:
        raise RuntimeError("Linux runtime check failed: " + result.stdout + result.stderr)
    collect_notices(output, sources)
    if any(p.suffix.lower() in (".dll", ".exe") for p in runtime.rglob("*")):
        raise ValueError("A Windows binary was included in the Linux worker.")
    write_manifest(runtime, ROOT, "linux", platform.machine())
    print("Linux runtime built and checked:", executable)


def collect_notices(output, sources):
    for name, content in licenses().items():
        target = output / "licenses/linux" / name.removeprefix("licenses/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for item in json.loads((ROOT / "native_linux/sources.json").read_text()):
        source = sources / item["file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Source checksum changed: " + source.name)
        if source.name.startswith(("opensc-", "libusb-", "pcsc-lite-", "ccid-")):
            target = output / "native-sources/linux" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("output", "prefix", "sources", "work"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    build(args.output, args.prefix, args.sources, args.work)
