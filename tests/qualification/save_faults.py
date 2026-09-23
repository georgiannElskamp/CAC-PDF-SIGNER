"""Exercise recovery with real permission/disk failures and injected write faults."""
import errno
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
from common import hosted, record
from test_standalone import StandaloneRecoveryTests

hosted()
assert os.getuid() != 0, "Permission checks require an ordinary user"
outcomes = []
fixture = StandaloneRecoveryTests()
fixture.setUp()
try:
    original = fixture.original.read_bytes()

    def preserved():
        assert fixture.original.read_bytes() == original
        assert fixture.recovery.read_bytes() == fixture.content
        assert fixture.session.pending(fixture.metadata["sourceHash"], "PreparedBy")

    def rejected(name, target, expected_errno=None):
        try:
            fixture.session.save(fixture.identifier, fixture.metadata, target)
        except OSError as error:
            if expected_errno is not None:
                assert error.errno == expected_errno, (name, error)
        except ValueError:
            assert expected_errno is None
        else:
            raise AssertionError(name + " unexpectedly succeeded")
        preserved()
        assert not list(target.parent.glob(".cac-*.tmp"))
        outcomes.append(name)

    protected = fixture.root / "permission changed"
    protected.mkdir()
    protected.chmod(0o500)
    try:
        rejected("destination permission denied", protected / "signed.pdf", errno.EACCES)
    finally:
        protected.chmod(0o700)

    for kind in ("symlink", "hardlink"):
        alias = fixture.root / (kind + ".pdf")
        if kind == "symlink":
            alias.symlink_to(fixture.original)
        else:
            os.link(fixture.original, alias)
        rejected(kind + " to original rejected", alias)

    for operation in ("fsync", "replace"):
        target = fixture.root / (operation + ".pdf")
        target.write_bytes(b"existing destination")
        with patch("standalone_worker.os." + operation, side_effect=OSError(errno.EIO, "injected I/O failure")):
            rejected(operation + " failure", target, errno.EIO)
        assert target.read_bytes() == b"existing destination"

    with tempfile.TemporaryDirectory(prefix="cac-bounded-disk-") as directory:
        mount = Path(directory)
        subprocess.run(["sudo", "mount", "-t", "tmpfs", "-o",
                        f"size=1m,uid={os.getuid()},gid={os.getgid()},mode=0700", "tmpfs", str(mount)], check=True)
        try:
            fixture.content = original + b"x" * (2 * 1024 * 1024)
            fixture.recovery.write_bytes(fixture.content)
            fixture.metadata["sha256"] = hashlib.sha256(fixture.content).hexdigest()
            fixture.session.record(fixture.identifier, fixture.metadata)
            rejected("real filesystem capacity exhausted", mount / "signed.pdf", errno.ENOSPC)
        finally:
            subprocess.run(["sudo", "umount", str(mount)], check=True)

    target = fixture.root / "retry.pdf"
    with patch("platform_card.card_signer", side_effect=AssertionError("Recovery must not access a card")):
        _, metadata, recovered = fixture.session.sign(fixture.request)
        assert recovered
        fixture.session.save(fixture.identifier, metadata, target)
    assert target.read_bytes() == fixture.content
    outcomes.append("retry reused recovery without card access")
finally:
    fixture.tearDown()
    fixture.doCleanups()
record("save-faults", status="passed", cases=outcomes,
       scope="Production recovery/save source under ordinary Linux account; synthetic bytes, not a hardware signing test.",
       limits=["No power loss simulation", "No Windows destination ACL or network-filesystem test", "No concurrent recovery test"])
