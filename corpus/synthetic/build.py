"""Build the synthetic task corpus.

Every bundle is produced by copying a clean base repository and then applying zero or more
*scripted* mutations. The label is the mutation record, so ground truth is exact by construction —
there is no annotation step and therefore no annotator disagreement.

Run:  uv run python corpus/synthetic/build.py

The corpus is regenerable, so a judge can rebuild it and confirm the labels match rather than
taking a checked-in YAML file on trust.
"""

from __future__ import annotations

import difflib
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
BASE_DIR = ROOT / "base"
OUT_DIR = ROOT / "bundles"

sys.path.insert(0, str(ROOT.parent.parent))

from rewardgate.mutations import MUTATIONS  # noqa: E402


def generate_patch(original_root: Path, fixed_root: Path, rel_paths: list[str]) -> str:
    """Produce a git-applicable unified diff from two source trees."""
    chunks: list[str] = []
    for rel in rel_paths:
        before = (original_root / rel).read_text().splitlines(keepends=True)
        after = (fixed_root / rel).read_text().splitlines(keepends=True)
        body = list(
            difflib.unified_diff(before, after, fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3)
        )
        if body:
            chunks.append(f"diff --git a/{rel} b/{rel}\n" + "".join(body))
    return "".join(chunks)


def solution_files(base: Path) -> list[str]:
    """Paths, relative to the bundle root, that the gold patch rewrites."""
    solution_root = base / "solution"
    return [
        str(p.relative_to(solution_root))
        for p in sorted(solution_root.rglob("*"))
        if p.is_file()
    ]


def build_clean_bundle(base: Path, dest: Path) -> None:
    """Copy a base repo into `dest` and attach its generated gold patch."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, ignore=shutil.ignore_patterns("solution", "__pycache__"))
    rel_paths = solution_files(base)
    (dest / "solution.patch").write_text(generate_patch(base, base / "solution", rel_paths))


def build() -> list[dict]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    for base in sorted(p for p in BASE_DIR.iterdir() if p.is_dir()):
        name = base.name

        clean_id = f"{name}-clean"
        build_clean_bundle(base, OUT_DIR / clean_id)
        manifest.append({"id": clean_id, "base": name, "defects": []})

        for mutation in MUTATIONS:
            bundle_id = f"{name}-{mutation.slug}"
            dest = OUT_DIR / bundle_id
            build_clean_bundle(base, dest)
            if not mutation.apply(dest):
                shutil.rmtree(dest)
                continue
            # A negative control carries no defect label; its correct verdict is "clean".
            defects = [mutation.defect] if mutation.defect else []
            manifest.append({"id": bundle_id, "base": name, "defects": defects})

    for entry in manifest:
        (OUT_DIR / entry["id"] / "task.yaml").write_text(yaml.safe_dump(entry, sort_keys=False))

    (OUT_DIR / "labels.yaml").write_text(yaml.safe_dump({"bundles": manifest}, sort_keys=False))
    return manifest


if __name__ == "__main__":
    built = build()
    print(f"built {len(built)} bundles in {OUT_DIR}")
    for entry in built:
        print(f"  {entry['id']:<32} defects={entry['defects'] or ['none']}")
