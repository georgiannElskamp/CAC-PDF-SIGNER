import json
from pathlib import Path
import subprocess
import sys
import unittest


class WorkerProtocolTests(unittest.TestCase):
    def test_result_is_delivered_before_worker_exits(self):
        worker = Path(__file__).resolve().parents[1] / "standalone_worker.py"
        child = subprocess.Popen([sys.executable, "-B", str(worker)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(json.loads(child.stdout.readline())["event"], "ready")
            child.stdin.write('{"op":"invalid-test-operation","acknowledgeResult":true}\n')
            child.stdin.flush()
            result = json.loads(child.stdout.readline())
            self.assertEqual(result["event"], "result")
            self.assertFalse(result["ok"])
            self.assertIsNone(child.poll())
            child.communicate('{"op":"ack"}\n', timeout=5)
            self.assertEqual(child.returncode, 1)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate()
