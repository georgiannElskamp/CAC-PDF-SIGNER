"""Select the native signing backend."""

import sys
from contextlib import contextmanager


@contextmanager
def card_signer(bridge):
    if sys.platform == "linux":
        from linux_card import card_signer as linux_signer

        with linux_signer() as signer:
            yield signer
        return
    if sys.platform != "win32":
        raise RuntimeError("This package supports Windows and Linux desktop editors.")
    from card_selection import choose_certificate
    from signing import CardSigner, certificates

    yield CardSigner(choose_certificate(certificates(bridge)), bridge)
