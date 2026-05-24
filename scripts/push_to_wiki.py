"""
push_to_wiki.py
Pushes the latest monthly report to the GitHub wiki.
Requires GITHUB_TOKEN and REPO env vars.
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))
from monthly_report import get_target_month

REPORTS_DIR = Path(__file__).parent.parent / "generated" / "reports"


def main():
    repo      = os.environ.get("REPO", "")
    gh_token  = os.environ.get("GH_TOKEN", "")
    ym        = get_target_month()

    report_path = REPORTS_DIR / f"{ym}.md"
    if not report_path.exists():
        print(f"Report {report_path} not found, skipping wiki push.")
        return

    wiki_url = f"https://{gh_token}@github.com/{repo}.wiki.git"

    # Clone wiki
    subprocess.run(["git", "clone", wiki_url, "/tmp/wiki"], check=True)

    # Copy report
    dest = Path(f"/tmp/wiki/Report-{ym}.md")
    dest.write_text(report_path.read_text())

    # Update Home.md with links
    home = Path("/tmp/wiki/Home.md")
    home_content = home.read_text() if home.exists() else "# Company Reports\n\n"

    link = f"* [Report {ym}](Report-{ym})"
    if link not in home_content:
        home_content += f"\n{link}"
        home.write_text(home_content)

    # Commit and push
    subprocess.run(["git", "-C", "/tmp/wiki", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "-C", "/tmp/wiki", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "-C", "/tmp/wiki", "add", "."], check=True)
    result = subprocess.run(["git", "-C", "/tmp/wiki", "diff", "--staged", "--quiet"])
    if result.returncode != 0:
        subprocess.run(["git", "-C", "/tmp/wiki", "commit", "-m", f"report: {ym}"], check=True)
        subprocess.run(["git", "-C", "/tmp/wiki", "push"], check=True)
        print(f"Wiki updated with report {ym}")
    else:
        print("No wiki changes.")


if __name__ == "__main__":
    main()
