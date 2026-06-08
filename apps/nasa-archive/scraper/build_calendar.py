"""
NASA Archive — build_calendar.py

Reads GitHub Issues labeled 'rally-submission' and writes data/calendar.json.

Run after new rally submissions come in:
    python scraper/build_calendar.py

Requires: gh CLI authenticated (gh auth login)

Output:
    data/calendar.json  -- community-submitted rally calendar
"""

import json
import re
import subprocess
from pathlib import Path

REPO = "rudi193-cmd/nasa-archive"
DATA_DIR = Path(__file__).parent.parent / "data"


def fetch_submissions():
    """Fetch all open issues labeled rally-submission via gh CLI."""
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--repo", REPO,
            "--label", "rally-submission",
            "--state", "open",
            "--json", "number,title,body,author,createdAt",
            "--limit", "200",
        ],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error fetching issues: {result.stderr}")
        return []
    return json.loads(result.stdout)


def parse_issue_body(body):
    """Extract structured fields from GitHub issue form body."""
    fields = {}
    if not body:
        return fields

    # GitHub issue forms render as "### Field Name\n\nValue\n"
    sections = re.split(r'###\s+', body)
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        key = lines[0].strip().lower().replace(' ', '_')
        value = '\n'.join(lines[1:]).strip()
        # Strip markdown blockquotes or no-response placeholders
        if value in ('_No response_', '', 'None'):
            value = ''
        fields[key] = value

    return fields


def issue_to_entry(issue):
    """Convert a GitHub issue to a calendar entry dict."""
    fields = parse_issue_body(issue.get('body', ''))

    return {
        "title": fields.get('rally_name') or issue['title'],
        "date_start": fields.get('start_date', ''),
        "date_end": fields.get('end_date', '') or None,
        "location": fields.get('location', ''),
        "region": fields.get('region', ''),
        "url": fields.get('event_url', '') or None,
        "rally_slug": None,
        "submitted_by": f"github:{issue['author']['login']}",
        "verified": False,
        "notes": fields.get('notes', '') or '',
        "issue_number": issue['number'],
    }


def main():
    print("=" * 50)
    print("  NASA Archive — Building calendar")
    print("=" * 50)

    print("\nFetching rally submissions from GitHub Issues...")
    issues = fetch_submissions()
    print(f"  Found {len(issues)} submissions")

    entries = [issue_to_entry(i) for i in issues]

    # Sort by start date
    entries.sort(key=lambda e: e.get('date_start') or '')

    out = DATA_DIR / "calendar.json"
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Wrote {len(entries)} entries to data/calendar.json")
    print("\nDone. Run 'python scraper/build_data.py' to rebuild index.json.")


if __name__ == "__main__":
    main()
