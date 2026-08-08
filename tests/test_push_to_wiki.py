import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import push_to_wiki  # noqa: E402


class PushToWikiTests(unittest.TestCase):
    def test_skips_when_wiki_repository_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            (reports_dir / "2026-04.md").write_text("# Monthly report")

            clone_result = subprocess.CompletedProcess(
                args=["git", "clone", "url", "/tmp/wiki"],
                returncode=128,
                stdout="",
                stderr="remote: Repository not found.\nfatal: repository not found",
            )

            with (
                patch.object(push_to_wiki, "REPORTS_DIR", reports_dir),
                patch.object(push_to_wiki, "get_target_month", return_value="2026-04"),
                patch.dict("os.environ", {"REPO": "dvoina/company-management", "GH_TOKEN": "token"}),
                patch.object(push_to_wiki.subprocess, "run", return_value=clone_result) as run_mock,
            ):
                push_to_wiki.main()

            self.assertEqual(run_mock.call_count, 1)
            self.assertEqual(run_mock.call_args[0][0][:2], ["git", "clone"])


if __name__ == "__main__":
    unittest.main()
