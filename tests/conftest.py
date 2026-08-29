"""Session guard: no test may modify the shipped corpus.

One test used to apply `solution.patch` to `corpus/synthetic/bundles/csvlite-clean` and reverse it
in a `finally`. For the couple of seconds in between, a *clean* bundle was a *fixed* bundle on
disk — and every audit path materialises the bundle by copying it. A second pytest process,
`pytest -n auto`, or a `rewardgate audit` in another terminal would copy the patched tree, see the
no-op trial pass, and report `NOP_PASS → REJECT` on the corpus's own negative control.

It surfaced exactly that way: a run of `uv run pytest -q` alongside other work failed with
`assert 1 == 3` and a report claiming `csvlite-clean` "measures nothing". The bundle was fine; the
test suite had briefly made it not fine.

A comment saying "don't do this" is not a control, because the next person to write a test against
a real bundle will not have read it. This is the control: hash the corpus at session start, hash it
again at the end, and fail loudly naming the files that changed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

BUNDLES = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles"

# Only the files a mutation would touch. Hashing `.git` would make this flaky for no gain — the
# contamination checker reads history, it never writes it.
_WATCHED = ("src/**/*.py", "tests/**/*.py", "held_out/**/*.py", "solution.patch", "instruction.md")


def _digest() -> dict[str, str]:
    if not BUNDLES.exists():
        return {}
    out: dict[str, str] = {}
    for bundle in sorted(p for p in BUNDLES.iterdir() if p.is_dir()):
        for pattern in _WATCHED:
            for path in sorted(bundle.glob(pattern)):
                if path.is_file() and "__pycache__" not in path.parts:
                    key = str(path.relative_to(BUNDLES))
                    out[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


_COLLECTED: list[int] = []


def pytest_collection_modifyitems(items):
    """Record how many tests exist, so a test can hold the documentation to it.

    The suite size has been wrong in the docs three times — 258, then 294, then 296 — because it is
    a number that changes every time a test is added and lives in a dozen prose files that do not.
    Writing it down again by hand would be the fourth. `test_documented_test_count_is_current`
    reads this.
    """
    _COLLECTED.append(len(items))


@pytest.fixture(scope="session")
def collected_test_count() -> int:
    return _COLLECTED[0] if _COLLECTED else 0


@pytest.fixture(scope="session", autouse=True)
def corpus_is_left_exactly_as_it_was_found():
    """Fails the session if any test mutated a shipped bundle, naming the files."""
    before = _digest()
    yield
    after = _digest()
    if before == after:
        return

    changed = sorted(
        k for k in set(before) | set(after) if before.get(k) != after.get(k)
    )
    pytest.fail(
        "a test modified the shipped corpus, which makes every later audit of these bundles "
        "wrong until they are rebuilt:\n  "
        + "\n  ".join(changed)
        + "\n\nTests that need to patch a bundle must copy it to tmp_path first. "
        "Rebuild with: uv run python corpus/synthetic/build.py"
    )
