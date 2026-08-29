"""The containerised adjudication.

A container is the easiest thing in this repository to ship broken, because a container that
contains nothing runs pytest perfectly well and every other test stays green. So the flags are
pinned as data (which works on a machine with no engine installed), the host/contained *agreement*
is pinned by execution, and `scripts/prove_containment.py` measures what is actually blocked.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from rewardgate.cli import EXIT_USAGE, main
from rewardgate.execution import (
    ContainerConfig,
    MaterialisedBundle,
    container_available,
    container_create_argv,
    materialise,
)

BUNDLES = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles"
CONFIG = ContainerConfig()

needs_engine = pytest.mark.skipif(
    shutil.which(CONFIG.engine) is None or container_available(CONFIG) != "",
    reason=f"needs {CONFIG.engine} and: {CONFIG.engine} build -t {CONFIG.image} docker/",
)
needs_corpus = pytest.mark.skipif(
    not (BUNDLES / "labels.yaml").exists(),
    reason="run: uv run python corpus/synthetic/build.py",
)


# --- the argv, which is where the containment lives -------------------------------------


def _argv(tmp_path: Path) -> list[str]:
    (tmp_path / "tests").mkdir()
    return container_create_argv(CONFIG, tmp_path, tmp_path / "tests")


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--network", "none"),        # the headline: an exploit patch has no socket
        ("--user", "1000:1000"),      # never root, even in a disposable container
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges"),
        ("--memory", "512m"),         # a runaway allocation is a plausible accident
        ("--pids-limit", "256"),      # so is a fork bomb
    ],
)
def test_every_containment_flag_is_present(tmp_path, flag, value):
    """Data-driven so a dropped flag fails by name. Each of these can vanish silently: the tests
    still pass, the report still says the run was contained, and it was not."""
    argv = _argv(tmp_path)
    assert flag in argv, f"{flag} missing"
    assert argv[argv.index(flag) + 1] == value


def test_no_host_path_is_mounted_into_the_container(tmp_path):
    """The tree is copied in with `cp`, not bind-mounted, and that is load-bearing twice.

    Correctness first: with a read-only bind mount the *oracle* run — the gold patch, which passes
    on the host — came back 0 passed, 11 failed, because the container read a stale view of a file
    the host had just rewritten. `return next(csv.reader([row]))` arrived as `return nex`, cut to
    the previously cached length. A container whose results are wrong is worse than none, since
    those results are what the verdict cites.

    Containment second: with no mount there is no host path to reach at all.
    """
    argv = _argv(tmp_path)
    assert "-v" not in argv and "--mount" not in argv
    assert not any(str(tmp_path) in part for part in argv)


def test_a_test_directory_outside_the_bundle_is_refused(tmp_path):
    """Silently reaching outside the materialised copy would mean adjudicating something else."""
    (tmp_path / "repo").mkdir()
    with pytest.raises(ValueError, match="not inside the materialised bundle"):
        container_create_argv(CONFIG, tmp_path / "repo", tmp_path / "elsewhere")


def test_the_missing_image_message_tells_the_reader_how_to_build_it():
    reason = container_available(ContainerConfig(image="rewardgate-nonexistent:0"))
    assert "build -t rewardgate-nonexistent:0 docker/" in reason


def test_docker_requested_but_unavailable_fails_instead_of_falling_back(monkeypatch, capsys):
    """A `--docker` run that quietly degrades to host execution is worse than no flag at all: the
    reviewer asked for containment, did not get it, and nothing in the report says so."""
    monkeypatch.setattr("rewardgate.cli.container_available", lambda _c: "engine is not on PATH")
    monkeypatch.setattr(
        "rewardgate.cli.audit_bundle",
        lambda *a, **k: pytest.fail("audit ran despite the container being unavailable"),
    )
    assert main(["audit", "csvlite-clean", "--no-exploit", "--docker"]) == EXIT_USAGE
    assert "--docker requested but unavailable" in capsys.readouterr().err


# --- executed: the contained run must agree with the host run ---------------------------


@needs_engine
@needs_corpus
@pytest.mark.parametrize("bundle_name", ["csvlite-clean"])
def test_the_contained_reward_gate_reproduces_the_host_result(bundle_name):
    """Soundness, not safety. If containment changed the verdict, every number this project
    reports would depend on which way it happened to be run."""
    bundle = BUNDLES / bundle_name
    patch = (bundle / "solution.patch").read_text()

    def gate(container):
        with materialise(bundle) as tmp:
            nop = MaterialisedBundle(Path(tmp), container).run_tests(Path(tmp) / "repo" / "tests")
        with materialise(bundle) as tmp:
            m = MaterialisedBundle(Path(tmp), container)
            assert not m.apply_patch(patch)
            return nop.reward, m.run_tests(m.repo / "tests").reward

    assert gate(None) == (0.0, 1.0), "the host baseline itself is wrong"
    assert gate(CONFIG) == (0.0, 1.0), "containment changed the reward gate's answer"


def _probe_repo(tmp_path: Path, body: str) -> MaterialisedBundle:
    """A one-test bundle laid out the way `materialise` leaves one: `<root>/repo/tests`."""
    tests = tmp_path / "repo" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_probe.py").write_text(body)
    return MaterialisedBundle(tmp_path, CONFIG)


@needs_engine
def test_the_container_genuinely_has_no_network(tmp_path):
    """The single claim `--network none` makes, executed rather than read off the argv."""
    bundle = _probe_repo(
        tmp_path,
        "import socket\n"
        "def test_net():\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3).close()\n",
    )
    outcome = bundle.run_tests(bundle.repo / "tests")
    assert outcome.failed == 1, outcome.stdout[-400:]


@needs_engine
def test_the_container_cannot_write_to_a_host_path(tmp_path):
    """A patch that drops a file into the reviewer's checkout is the other half of the threat."""
    canary = tmp_path / "canary.txt"
    bundle = _probe_repo(
        tmp_path,
        "import pathlib\n"
        "def test_write():\n"
        f"    pathlib.Path({str(canary)!r}).write_text('canary')\n",
    )
    bundle.run_tests(bundle.repo / "tests")
    assert not canary.exists(), "the container reached the host filesystem"


@needs_engine
def test_nothing_is_left_running_afterwards():
    """`create`/`start`/`rm` is three commands where `run --rm` was one; a leaked container per
    trial would be 15 per corpus run, each holding its memory reservation."""
    listed = subprocess.run(
        [CONFIG.engine, "ps", "-a", "--filter", f"ancestor={CONFIG.image}", "-q"],
        capture_output=True, text=True, check=False,
    )
    assert not listed.stdout.strip(), "adjudication containers were left behind"
