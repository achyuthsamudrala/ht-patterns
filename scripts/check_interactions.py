#!/usr/bin/env python3
"""
Verify that every page referenced in src/interactions.yml exists under src/.
Optionally regenerate the Mermaid block in interaction-map.md.
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
INTERACTIONS_YAML = SRC / "interactions.yml"
INTERACTION_MAP = SRC / "interaction-map.md"

MERMAID_START = "```mermaid"
MERMAID_END = "```"


def slug_to_path(slug: str) -> Path:
    """Convert 'patterns/overload/retry-storms' to src/patterns/overload/retry-storms.md"""
    return SRC / (slug + ".md")


def slug_to_node_id(slug: str) -> str:
    """'patterns/overload/retry-storms' → 'retry-storms'"""
    return slug.split("/")[-1]


def main() -> int:
    data = yaml.safe_load(INTERACTIONS_YAML.read_text())
    edges = data.get("edges", [])
    errors = []

    for i, edge in enumerate(edges):
        for field in ("from", "to"):
            slug = edge.get(field)
            if not slug:
                errors.append(f"Edge {i}: missing '{field}' field")
                continue
            p = slug_to_path(slug)
            if not p.exists():
                errors.append(f"Edge {i} ({field}={slug!r}): page not found at {p}")

    if errors:
        print("ERRORS in interactions.yml:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    print(f"✓ interactions check passed ({len(edges)} edges, all pages exist)")

    # --- Optionally: generate Mermaid snippet and compare to what's in interaction-map.md ---
    lines = ["graph TD"]
    for edge in edges:
        src_id = slug_to_node_id(edge["from"])
        dst_id = slug_to_node_id(edge["to"])
        label = edge.get("label", "")
        src_label = edge["from"].split("/")[-1].replace("-", " ").title()
        dst_label = edge["to"].split("/")[-1].replace("-", " ").title()
        lines.append(
            f'    {src_id}["{src_label}"] -->|"{label}"| {dst_id}["{dst_label}"]'
        )
    generated = "\n".join(lines)

    # Check if the interaction-map.md contains a mermaid block and compare
    map_text = INTERACTION_MAP.read_text()
    m = re.search(r'```mermaid\n(.*?)```', map_text, re.DOTALL)
    if m:
        current = m.group(1).strip()
        if current != generated:
            print("\nNote: Mermaid block in interaction-map.md differs from interactions.yml.")
            print("Run `python scripts/gen_interactions.py` to regenerate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
