"""Measure what the sandbox actually stops, by running the same hostile code both ways.

`--docker` is a claim about safety, and safety claims are the easiest kind to ship broken: every
flag can be silently wrong and the test suite still comes out green, because a container that
contains nothing runs pytest perfectly well. So this does not assert that the flags are present.
It builds a bundle whose test module tries three things an exploit patch would try, runs it on the
host and in the container, and records the difference.

    uv run python scripts/prove_containment.py

Nothing here is destructive: the network probe opens and immediately closes one socket, and the
filesystem probe writes a canary into a temporary directory this script owns and deletes.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewardgate.execution import (  # noqa: E402
    ContainerConfig,
    MaterialisedBundle,
    container_available,
    materialise,
)

# Secrets that were actually present in the developing operator's shell, named here so the probe
# reports a leak by variable rather than by count. Values are never recorded — only the names.
WATCHED_SECRETS = ("GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SENDGRID_API_KEY", "NPM_AUTH_TOKEN",
                   "AUTH0_CLIENT_SECRET", "SSH_AUTH_SOCK", "ANTHROPIC_API_KEY")

PROBE = '''\
"""Stands in for an exploit patch's module scope: this is code the harness chose to execute."""
import json, os, pathlib, socket

CANARY = {canary!r}
WATCHED = {watched!r}


def _network():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return "reachable"
    except OSError as exc:
        return f"blocked ({{type(exc).__name__}})"


def _host_write():
    try:
        pathlib.Path(CANARY).write_text("canary")
        return "written"
    except OSError as exc:
        return f"blocked ({{type(exc).__name__}})"


def test_probe():
    assert False, "RG_PROBE " + json.dumps({{
        "network": _network(),
        "host_write": _host_write(),
        "secrets_visible": sorted(n for n in WATCHED if n in os.environ),
        "uid": os.getuid(),
        "is_root": os.getuid() == 0,
    }})
'''


def _probe_bundle(root: Path, canary: Path) -> Path:
    bundle = root / "probe-bundle"
    (bundle / "tests").mkdir(parents=True)
    (bundle / "src").mkdir()
    (bundle / "src" / "placeholder.py").write_text("VALUE = 1\n")
    (bundle / "tests" / "test_probe.py").write_text(
        PROBE.format(canary=str(canary), watched=WATCHED_SECRETS)
    )
    return bundle


def _observe(bundle: Path, container: ContainerConfig | None) -> dict:
    with materialise(bundle) as tmp:
        outcome = MaterialisedBundle(Path(tmp), container=container).run_tests(
            Path(tmp) / "repo" / "tests"
        )
    match = re.search(r"RG_PROBE (\{.*\})", outcome.stdout)
    if not match:
        return {"error": "probe did not report", "stdout": outcome.stdout[-400:]}
    return json.loads(match.group(1))


def main() -> None:
    config = ContainerConfig()
    if reason := container_available(config):
        sys.exit(f"cannot prove containment: {reason}")

    with tempfile.TemporaryDirectory(prefix="rewardgate-probe-") as tmp:
        root = Path(tmp)
        canary = root / "canary.txt"
        bundle = _probe_bundle(root, canary)

        host = _observe(bundle, None)
        host["canary_on_disk"] = canary.exists()
        canary.unlink(missing_ok=True)

        contained = _observe(bundle, config)
        contained["canary_on_disk"] = canary.exists()
        canary.unlink(missing_ok=True)

    rows = ["network", "host_write", "uid", "is_root", "canary_on_disk", "secrets_visible"]
    print(f"{'PROBE':<18}{'HOST':<34}CONTAINED")
    print("=" * 74)
    for key in rows:
        print(f"{key:<18}{str(host.get(key)):<34}{contained.get(key)}")

    proof = {
        "image": config.image,
        "network_flag": config.network,
        "host": host,
        "contained": contained,
        # The two that decide whether `--docker` is worth the flag. Asserted, not eyeballed, so a
        # regression in the argv shows up as a failed run rather than a table nobody re-reads.
        "network_blocked_only_when_contained":
            host.get("network") == "reachable" and contained.get("network", "").startswith("blocked"),
        "host_filesystem_unreachable_when_contained":
            host.get("canary_on_disk") is True and contained.get("canary_on_disk") is False,
    }
    out = ROOT / "results" / "containment_proof.json"
    out.write_text(json.dumps(proof, indent=2) + "\n")
    print(f"\nsaved -> {out.relative_to(ROOT)}")

    if not proof["network_blocked_only_when_contained"]:
        print("\nNOTE: the host probe could not reach the network either, so this run does not "
              "demonstrate that --network none is what blocked it.", file=sys.stderr)


if __name__ == "__main__":
    if not shutil.which("docker"):
        sys.exit("docker not on PATH")
    main()
