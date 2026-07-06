#!/usr/bin/env python3
"""
Verify that every link in symptom-index.md points to an existing page,
and that every pattern page under src/patterns/ is reachable from the index.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
SYMPTOM_INDEX = SRC / "symptom-index.md"


def find_md_links(text: str) -> list[str]:
    return re.findall(r'\]\(([^)]+\.md[^)]*)\)', text)


def resolve_link(link: str, base: Path) -> Path:
    # Strip anchors
    link = link.split('#')[0]
    return (base.parent / link).resolve()


def main() -> int:
    errors = []
    warnings = []

    # --- Check that all links in symptom-index.md resolve ---
    index_text = SYMPTOM_INDEX.read_text()
    linked_pages: set[Path] = set()

    for link in find_md_links(index_text):
        resolved = resolve_link(link, SYMPTOM_INDEX)
        linked_pages.add(resolved)
        if not resolved.exists():
            errors.append(f"symptom-index.md: broken link → {link} (resolved: {resolved})")

    # --- Check that every pattern page appears in symptom-index ---
    pattern_pages = list((SRC / "patterns").rglob("*.md"))
    pattern_pages = [p for p in pattern_pages if p.name != "index.md"]

    for page in sorted(pattern_pages):
        if page not in linked_pages:
            warnings.append(f"not in symptom-index: {page.relative_to(SRC)}")

    # --- Report ---
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  ✗ {e}")

    if warnings:
        print("WARNINGS (pattern pages not reachable from symptom-index):")
        for w in warnings:
            print(f"  ? {w}")

    if not errors and not warnings:
        print("✓ symptom-index check passed")
    elif not errors:
        print(f"\n✓ no broken links ({len(warnings)} pages not yet indexed)")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
