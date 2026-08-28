"""Materialising and running task bundles.

Everything in this module is deterministic and produces the mechanical artifacts the audit report
cites: exit codes, test counts, applied-patch SHAs. No model is involved.

A bundle is materialised into a fresh temporary git repository for every run, so a patch that
corrupts the tree cannot affect the next trial or the corpus on disk.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Trials are tiny; anything slower than this is a hang, not a slow test.
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class TestOutcome:
    """Result of running one test directory against one tree state."""

    # Stops pytest collecting this as a test class on account of its name.
    __test__ = False

    exit_code: int
    passed: int
    failed: int
    errors: int
    stdout: str
    timed_out: bool = False

    @property
    def all_passed(self) -> bool:
        """pytest exits 0 only when it collected tests and all of them passed."""
        return self.exit_code == 0 and not self.timed_out and self.passed > 0

    @property
    def reward(self) -> float:
        """Benchmark-harness convention: 1.0 for a fully green suite, 0.0 otherwise."""
        return 1.0 if self.all_passed else 0.0

    @property
    def summary(self) -> str:
        if self.timed_out:
            return "timed out"
        return f"exit={self.exit_code} passed={self.passed} failed={self.failed} errors={self.errors}"


def _run(
    cmd: list[str],
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False, env=env
    )


def _parse_pytest_counts(output: str) -> tuple[int, int, int]:
    """Read passed/failed/error counts from pytest's summary line.

    Parsing the summary rather than using a plugin keeps the bundle's dependency surface to pytest
    alone, which matters because every bundle must run in the same minimal environment.
    """
    passed = failed = errors = 0
    for line in reversed(output.splitlines()):
        if "passed" not in line and "failed" not in line and "error" not in line:
            continue
        tokens = line.replace("=", " ").replace(",", " ").split()
        for i, token in enumerate(tokens[1:], start=1):
            if not tokens[i - 1].isdigit():
                continue
            count = int(tokens[i - 1])
            if token.startswith("passed"):
                passed = count
            elif token.startswith("failed"):
                failed = count
            elif token.startswith("error"):
                errors = count
        if passed or failed or errors:
            break
    return passed, failed, errors


class MaterialisedBundle:
    """A bundle checked out into a disposable git repository."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def repo(self) -> Path:
        return self.root / "repo"

    def apply_patch(self, patch_text: str) -> str:
        """Apply a unified diff to the working tree. Returns '' on success, else the git error."""
        if not patch_text.strip():
            return ""
        patch_file = self.root / "candidate.patch"
        patch_file.write_text(patch_text)
        result = _run(["git", "apply", "--whitespace=nowarn", str(patch_file)], self.repo)
        return "" if result.returncode == 0 else (result.stderr or "git apply failed")

    def _test_env(self) -> dict[str, str]:
        """Environment with the bundle's `src` on PYTHONPATH.

        Set explicitly rather than relying on the bundle's `conftest.py`: pytest derives rootdir
        from its arguments, so passing an absolute path to `tests/` puts the bundle-root conftest
        above confcutdir and it is silently never loaded.
        """
        # ALLOWLIST, not a denylist. This started as `os.environ.copy()` with a handful of
        # pytest-cosmetic variables popped, which meant every secret in the operator's shell
        # reached module-scope code in an agent-written patch. On the machine this was developed
        # on that included GH_TOKEN, AUTH0_CLIENT_SECRET, SENDGRID_API_KEY, NPM_AUTH_TOKEN and a
        # live SSH_AUTH_SOCK -- an agent socket that can sign as the user.
        #
        # A denylist can only ever enumerate the variables its author happened to think of. The
        # harness needs five variables to run pytest; everything else is the operator's business
        # and none of the agent's.
        env = {
            name: os.environ[name]
            for name in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
            if name in os.environ
        }
        env["PYTHONPATH"] = str(self.repo / "src")
        # Deterministic hashing, so set and dict iteration order cannot move a test outcome.
        env["PYTHONHASHSEED"] = "0"
        return env

    def run_tests(self, test_dir: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> TestOutcome:
        """Run pytest over `test_dir` with the bundle's `src` importable."""
        try:
            result = _run(
                # sys.executable, not "python": an ambient interpreter without pytest would make
                # every trial fail identically, which reads as "unsolvable task" rather than
                # "broken harness".
                # `--color=no` belt-and-braces alongside the env scrub: pytest also auto-enables
                # colour from a tty, and the counts are parsed out of that line.
                [sys.executable, "-m", "pytest", str(test_dir), "-q", "--no-header",
                 "--color=no", "-p", "no:cacheprovider", "-p", "no:randomly"],
                self.repo,
                timeout=timeout,
                env=self._test_env(),
            )
        except subprocess.TimeoutExpired:
            return TestOutcome(exit_code=-1, passed=0, failed=0, errors=0, stdout="", timed_out=True)

        output = result.stdout + result.stderr
        passed, failed, errors = _parse_pytest_counts(output)
        return TestOutcome(result.returncode, passed, failed, errors, output)

    def head_sha(self) -> str:
        return _run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()


def materialise(bundle_dir: Path) -> tempfile.TemporaryDirectory:
    """Copy a bundle into a fresh temp dir and initialise git history.

    Returns the TemporaryDirectory handle so the caller controls its lifetime; use
    `with materialise(d) as tmp:` and wrap the path in `MaterialisedBundle`.
    """
    tmp = tempfile.TemporaryDirectory(prefix="rewardgate-")
    # Excluding bytecode caches is not tidiness. A stale __pycache__ copied into the fresh tree
    # shadows the patched source, so trials intermittently execute the previous run's code.
    shutil.copytree(
        bundle_dir,
        Path(tmp.name) / "repo",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )
    repo = Path(tmp.name) / "repo"

    if not (repo / ".git").exists():
        _run(["git", "init", "-q"], repo)
        _run(["git", "add", "-A"], repo)
        _run(
            [
                "git", "-c", "user.name=rewardgate", "-c", "user.email=rewardgate@localhost",
                "commit", "-q", "-m", "baseline",
            ],
            repo,
        )
    return tmp
