#!/usr/bin/env python3
"""
Verify that every pattern page under src/patterns/ (excluding index.md)
contains all required template sections in the correct order.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"

REQUIRED_SECTIONS = [
    "## Symptom",
    "## Mechanism",
    "## Real-world sightings",
    "## Mitigations",
    "## Interactions",
    "## References",
]

LENGTH_MIN = 300   # chars, warn below this
LENGTH_MAX = 8000  # chars (~1600 words), warn above this


def check_page(path: Path) -> list[str]:
    issues = []
    text = path.read_text()
    rel = path.relative_to(SRC)

    # Check required sections present
    for section in REQUIRED_SECTIONS:
        if section not in text:
            issues.append(f"{rel}: missing section '{section}'")

    # Check sections in order
    positions = {s: text.find(s) for s in REQUIRED_SECTIONS if s in text}
    ordered = sorted(positions.items(), key=lambda x: x[1])
    expected_order = [s for s in REQUIRED_SECTIONS if s in positions]
    actual_order = [s for s, _ in ordered]
    if actual_order != expected_order:
        issues.append(f"{rel}: sections out of order")

    # Warn on length
    char_count = len(text)
    if char_count < LENGTH_MIN:
        issues.append(f"{rel}: very short ({char_count} chars) — may be a stub")

    return issues


def main() -> int:
    pattern_pages = [
        p for p in (SRC / "patterns").rglob("*.md")
        if p.name != "index.md"
    ]

    all_issues = []
    for page in sorted(pattern_pages):
        all_issues.extend(check_page(page))

    if all_issues:
        print(f"Template issues found ({len(all_issues)}):")
        for issue in all_issues:
            print(f"  ! {issue}")
        return 1

    print(f"✓ template check passed ({len(pattern_pages)} pattern pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
