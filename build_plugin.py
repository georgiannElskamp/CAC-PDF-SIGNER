"""Build the legacy per-installation plugin package."""

import argparse
import json
import zipfile
from pathlib import Path

from runtime_config import VERSION, load_settings, outside_checkout, state_directory

FILES = [
    "config.json",
    "background.html",
    "background.js",
    "desktop-adapter.js",
    "plugins.js",
    "icon.png",
    "icon@2x.png",
]


def build(directory=None):
    directory = outside_checkout(directory or state_directory())
    settings = load_settings(directory)
    source = Path(__file__).resolve().parent / "plugin"
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    if config["version"] != VERSION or config["variations"][0]["type"] != "background":
        raise ValueError(
            "Plugin version/type must match the background helper release."
        )
    target = directory / "CAC-PDF-Signer.plugin"
    url = "http://127.0.0.1:" + str(settings["port"])
    connection = (
        "window.CAC_CONNECTION = "
        + json.dumps({"url": url, "token": settings["token"], "version": VERSION})
        + ";\n"
    )
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            content = (source / name).read_bytes()
            if name == "background.html":
                content = content.replace(
                    b"http://127.0.0.1:47831", url.encode("ascii")
                )
            archive.writestr(name, content)
        archive.writestr("connection.js", connection)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(FILES + ["connection.js"])
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    print("Private package (do not upload):", build(args.data_dir))
