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

# `-p no:randomly` and `--color=no` are not cosmetic: the counts every verdict cites are parsed out
# of pytest's summary line, and both plugins rewrite it.
PYTEST_ARGV = ("-q", "--no-header", "--color=no", "-p", "no:cacheprovider", "-p", "no:randomly")

SANDBOX_IMAGE = "rewardgate-sandbox:1"

# What the engine *client* needs to reach its daemon. Rancher Desktop and colima both point at a
# non-default socket through DOCKER_HOST, so dropping it turns "contained run" into "cannot connect
# to the Docker daemon" on the two most common macOS setups.
_ENGINE_ENV = (
    "PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY",
)


@dataclass(frozen=True)
class ContainerConfig:
    """How to run the adjudication inside a container.

    Only the *adjudication* is containerised — the run where an agent-written patch is imported and
    its module scope executes. The agent session itself is not, and cannot be under `--network
    none`, because that session is an API call. See `docs/SANDBOXING.md`.
    """

    image: str = SANDBOX_IMAGE
    engine: str = "docker"
    network: str = "none"
    memory: str = "512m"
    cpus: str = "2"
    pids: int = 256


def container_create_argv(config: ContainerConfig, repo: Path, test_dir: Path) -> list[str]:
    """The engine invocation for one adjudication run.

    Split out as a pure function because it is the part worth pinning: every flag here is a
    containment property, and a silently dropped one still produces a perfectly green test run.
    Asserting on the argv is also the only check that survives on a machine with no engine
    installed, which is most CI.

    **The tree is copied in, not bind-mounted.** The first working version mounted the
    materialised bundle read-only, and the reward gate then reported the *oracle* run — the gold
    patch, which passes on the host — as 0 passed, 11 failed. The container was reading a stale
    view of a file the host had just rewritten: `return next(csv.reader([row]))` arrived inside as
    `return nex`, truncated to the previously cached length. macOS bind mounts are not coherent
    enough to write from the host and immediately read from a container.

    That is disqualifying for this particular workload. A container whose test results are wrong is
    worse than no container, because the wrong results are what the verdict cites. Copying the tree
    in through `docker cp` also removes the host path from the container's view entirely, which is
    the stronger containment property anyway.
    """
    try:
        relative = test_dir.resolve().relative_to(repo.resolve())
    except ValueError as exc:
        # Refuse rather than reach outside the bundle. A test directory elsewhere means the caller
        # has lost track of what is being adjudicated.
        raise ValueError(f"{test_dir} is not inside the materialised bundle {repo}") from exc

    return [
        config.engine, "create",
        # The containment, in the order it matters. `--network none` is the headline: an exploit
        # patch that phones home, fetches a second stage, or exfiltrates the reviewer's environment
        # has no socket to do it through.
        "--network", config.network,
        # Never root, even here: a root process is one mount away from writing host files as root.
        "--user", "1000:1000",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        # A fork bomb or a runaway allocation in a patch is a plausible accident, not only an
        # attack; without these it takes the reviewer's machine down with it.
        "--memory", config.memory, "--cpus", config.cpus, "--pids-limit", str(config.pids),
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-w", "/work",
        "-e", "PYTHONPATH=/work/src",
        config.image,
        "python", "-m", "pytest", f"/work/{relative}", *PYTEST_ARGV,
    ]


def run_in_container(
    config: ContainerConfig, repo: Path, test_dir: Path, timeout: int, env: dict[str, str]
) -> subprocess.CompletedProcess:
    """create → copy the tree in → start → remove. Returns the pytest process result.

    `start -a` propagates the container's exit code, which is what the reward gate reads.
    """
    created = subprocess.run(
        container_create_argv(config, repo, test_dir),
        capture_output=True, text=True, check=False, env=env,
    )
    if created.returncode != 0:
        return created
    container_id = created.stdout.strip()
    try:
        copied = subprocess.run(
            [config.engine, "cp", f"{repo}/.", f"{container_id}:/work"],
            capture_output=True, text=True, check=False, env=env,
        )
        if copied.returncode != 0:
            return copied
        return subprocess.run(
            [config.engine, "start", "-a", container_id],
            capture_output=True, text=True, timeout=timeout, check=False, env=env,
        )
    finally:
        subprocess.run(
            [config.engine, "rm", "-f", container_id],
            capture_output=True, check=False, env=env,
        )


def container_available(config: ContainerConfig) -> str:
    """'' if the engine and image are usable, else a reason the caller can print.

    Checked up front so `--docker` fails loudly at the start of a run rather than degrading to host
    execution partway through. Silently falling back would be the exact failure this flag exists to
    remove, and the report would still say the run was contained.
    """
    if not shutil.which(config.engine):
        return f"{config.engine} is not on PATH"
    probe = subprocess.run(
        [config.engine, "image", "inspect", config.image],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode != 0:
        return f"image {config.image} not built — run: {config.engine} build -t {config.image} docker/"
    return ""


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

    def __init__(self, root: Path, container: ContainerConfig | None = None) -> None:
        self.root = root
        self.container = container

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
        """Run pytest over `test_dir` with the bundle's `src` importable.

        Containerised when `self.container` is set. The two paths must stay behaviourally
        identical apart from where the code runs — same pytest flags, same PYTHONPATH, same
        deterministic hash seed — or the contained result is not evidence about the host result.
        """
        try:
            if self.container:
                # The engine *client* runs on the host, so it gets the same allowlist discipline;
                # the workload's own environment is set inside by `-e` and the image.
                result = run_in_container(
                    self.container, self.repo, test_dir, timeout,
                    {n: os.environ[n] for n in _ENGINE_ENV if n in os.environ},
                )
            else:
                # sys.executable, not "python": an ambient interpreter without pytest would make
                # every trial fail identically, which reads as "unsolvable task" rather than
                # "broken harness".
                result = _run(
                    [sys.executable, "-m", "pytest", str(test_dir), *PYTEST_ARGV],
                    self.repo, timeout=timeout, env=self._test_env(),
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
