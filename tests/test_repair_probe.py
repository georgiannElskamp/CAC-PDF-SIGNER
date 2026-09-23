"""Temporary hosted repair probe; this PR must never merge."""
import unittest


def next_attempt(current):
    """Advance the synthetic attempt counter by one."""
    return current + 2


class RepairProbe(unittest.TestCase):
    def test_counter_advances_once(self):
        self.assertEqual(next_attempt(2), 3)
        self.assertEqual(next_attempt(0), 1)
