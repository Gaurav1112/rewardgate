# Sandboxing

This tool's central operation is: ask an adversarial agent to write a patch, then **execute that
patch**. Everything below is about the gap between "the agent's tools are restricted" and "the
code the agent writes is contained", because those are different claims and only the first one was
ever true here by default.

## What executes what

| Stage | What runs | Contained by `--docker`? |
|---|---|---|
| Reward gate — no-op trial | the bundle's own tests, unpatched | **yes** |
| Reward gate — oracle trial | the bundle's tests with the gold patch | **yes** |
| Agent session | the `claude` CLI, holding Read/Edit/Write/Glob/Grep and `pytest` | **no** |
| Adjudication | the bundle's tests **with the agent's patch applied** | **yes** |

The agent session is the exception, and it is not an oversight. That session *is* a network call:
under `--network none` it cannot reach the API and every trial fails identically, which reads as
"this task is unsolvable" rather than "the harness is broken" — the exact failure mode this
project exists to catch. It is contained by three weaker measures instead:

1. a disposable temp directory, never the corpus on disk;
2. a tool allowlist with the operator's MCP servers and settings excluded
   (`--strict-mcp-config`, empty `--mcp-config`);
3. an **environment allowlist** (`exploit.agent_env`) rather than the operator's shell.

The row that matters is the last one in the table. Adjudication is where an agent-written patch is
imported and its module scope executes, and that needs no network at all.

## What `--docker` actually does

```bash
docker build -t rewardgate-sandbox:1 docker/     # once; needs network
uv run python -m rewardgate.cli audit csvlite-clean --no-exploit --docker
```

Per test run: `docker create` with the flags below → `docker cp` the tree in → `docker start -a`
→ `docker rm -f`. Every flag is pinned by name in `tests/test_container_sandbox.py`, because each
one can vanish silently while the suite stays green and the report still says "contained".

| Flag | Against |
|---|---|
| `--network none` | a patch that phones home, fetches a second stage, or exfiltrates |
| `--user 1000:1000`, `--cap-drop ALL`, `--security-opt no-new-privileges` | privilege escalation |
| `--memory 512m`, `--cpus 2`, `--pids-limit 256` | a fork bomb or runaway allocation — as likely an accident as an attack |
| `--tmpfs /tmp:rw,noexec,nosuid` | executing a payload written at run time |
| no bind mount at all | reaching the reviewer's checkout |

**The tree is copied in, not mounted.** The first working version bind-mounted the materialised
bundle read-only, and the *oracle* trial — the gold patch, which passes on the host — came back
`0 passed, 11 failed`. The container was reading a stale view of a file the host had just
rewritten: `return next(csv.reader([row]))` arrived inside as `return nex`, truncated to the
previously cached length. macOS bind mounts are not coherent enough to write from the host and
immediately read from a container. A container whose results are wrong is worse than no container,
because those results are what every verdict cites. Copying in fixes the coherence problem and
removes the host path entirely, which is the stronger containment property anyway.

**It fails rather than falls back.** If the engine or image is missing, `--docker` exits 2 with the
build command. A run that quietly degrades to host execution is worse than no flag: the reviewer
asked for containment, did not get it, and nothing in the report says so.

## Measured, not asserted

`scripts/prove_containment.py` builds a bundle whose test module tries three things an exploit
patch would try, runs it **both ways**, and writes `results/containment_proof.json`:

| probe | host | contained |
|---|---|---|
| open a socket to 1.1.1.1:53 | `reachable` | `blocked (OSError)` |
| write a canary to a host path | `written` | `blocked (FileNotFoundError)` |
| canary present on disk afterwards | `True` | `False` |
| uid | 501 | 1000 |
| watched secrets visible | `[]` | `[]` |

The last row is the environment allowlist showing up on *both* sides: `GH_TOKEN`,
`AWS_SECRET_ACCESS_KEY`, `SENDGRID_API_KEY`, `NPM_AUTH_TOKEN`, `AUTH0_CLIENT_SECRET` and
`SSH_AUTH_SOCK` are all present in the developing operator's shell and none of them reach the test
process even without a container.

Nothing in the probe is destructive: one socket opened and closed, one canary written into a
temporary directory the script owns and deletes.

## What is still not covered

- **The agent session runs on the host**, as above. Containing it needs the API key inside the
  container and a network policy that permits exactly one endpoint. Not implemented.
- **The container is not a security boundary against a kernel exploit.** It is a boundary against
  the realistic threat here — a patch that reads the environment, writes files, or opens sockets.
- **`--docker` is opt-in.** The default path still executes agent-written code on the host, and the
  approval banner says so in those words. Making it the default would mean every judge needs a
  working engine and a built image before the tool runs at all.
