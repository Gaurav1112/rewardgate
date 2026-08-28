"""Render the RewardGate solution video from the committed script and real captured output.

Every terminal frame is text this repository actually printed — captured in cap/ by running the
commands, not retyped. The narration is the committed teleprompter text, unedited.
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
CAP = HERE / "cap"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

W, H = 1920, 1080
BG = (13, 17, 23)
FG = (201, 209, 217)
DIM = (110, 118, 129)
ACCENT = (88, 166, 255)
GOOD = (63, 185, 80)
BAD = (248, 81, 73)
WARN = (210, 153, 34)

MONO = "/System/Library/Fonts/Menlo.ttc"
mono = lambda s: ImageFont.truetype(MONO, s)
F_TITLE, F_BODY, F_SMALL, F_HUGE = mono(46), mono(26), mono(21), mono(84)


def cap(name: str) -> list[str]:
    return (CAP / name).read_text().splitlines()


def grep(name: str, *needles: str, limit: int = 40) -> list[str]:
    return [l for l in cap(name) if any(n in l for n in needles)][:limit]


def colour_for(line: str) -> tuple[int, int, int]:
    l = line.lower()
    if "defect" in l or "failed" in l and "0 failed" not in l:
        return BAD
    if "[  ok" in l or "passed" in l and "0 passed" not in l:
        return GOOD
    if l.strip().startswith("$"):
        return ACCENT
    if "verdict" in l or "reward_hackable" in l:
        return WARN
    return FG


def slide(path: Path, title: str, lines: list[str], *, hero: str | None = None,
          footer: str = "", body_font=F_BODY) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((90, 62), title, font=F_TITLE, fill=ACCENT)
    d.line([(90, 132), (W - 90, 132)], fill=(48, 54, 61), width=2)

    y = 180
    if hero:
        d.text((90, y), hero, font=F_HUGE, fill=FG)
        y += 130

    for raw in lines:
        for line in (textwrap.wrap(raw, 108) or [""]) if len(raw) > 108 else [raw]:
            d.text((90, y), line, font=body_font, fill=colour_for(raw))
            y += body_font.size + 12
            if y > H - 130:
                break
        if y > H - 130:
            break

    if footer:
        d.text((90, H - 78), footer, font=F_SMALL, fill=DIM)
    img.save(path)


def narrate(text: str, dest: Path) -> float:
    """macOS `say` -> AIFF -> AAC, returning the measured duration."""
    aiff = dest.with_suffix(".aiff")
    subprocess.run(["say", "-v", "Daniel", "-r", "158", "-o", str(aiff), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-c:a", "aac", "-b:a", "160k",
         str(dest)], check=True,
    )
    aiff.unlink()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(dest)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


# --- the segments: (narration, title, lines, hero, footer) ----------------------------

EXPLOIT_PATCH = [
    "    # the exploit agent's patch",
    "    if row == 'a,\"b,c\"':",
    "        return ['a', 'b,c']",
    "    return row.split(',')",
]

SEGMENTS = [
    ("Benchmark tasks train and grade coding agents, and a lot of them are broken. "
     "OpenAI audited its own SWE-bench tasks and filtered out sixty-eight percent of them. "
     "So I built RewardGate. It audits a candidate task before that task enters a training "
     "corpus. It proves defects by executing code instead of asking a model.",
     "RewardGate", [
         "Audits a candidate benchmark task before it enters a training corpus.",
         "Proves defects by execution, not by opinion.",
         "",
         "Who has the problem: a contractor paid per ACCEPTED task to author",
         "agentic coding benchmarks. They absorb every rejection personally.",
         "",
         "OpenAI's own SWE-bench audit: 38.3% underspecified,",
         "61.1% tests that may unfairly fail valid solutions, 68.3% filtered out.",
     ], None, "openai.com/index/introducing-swe-bench-verified"),

    ("Here is the strongest thing I measured. Across all five hundred instances of SWE-bench "
     "Verified, two hundred and ten carry at least one defect. That is forty-two percent. It is "
     "deterministic, and it cost zero dollars. One of those four checkers has an outside anchor. "
     "Mine counts a hundred and thirty-three instances that leak the gold file path into the "
     "issue text. The SWE-bench Illusion paper reports a hundred and thirty-five. Two apart, on "
     "a corpus I did not build.",
     "$ uv run python -m rewardgate.report_real",
     grep("01_report_real.txt", "leakage", "over-specified", "hint", "weak", "DEFECT", "INDETERM"),
     None, "500 real instances - deterministic - $0.00 - no model calls"),

    ("The simple baseline is one prompt and no tools. Paste in the instruction, the tests, the "
     "source and the git log. Ask for a verdict. Same output schema, same scorer, same fifteen "
     "bundles. It scores macro F one of zero point six zero zero, and it gets eleven of fifteen "
     "bundles exactly right. That is not a straw man. It is a competent reader. The class it "
     "misses is contamination. I will come back to that, because the reason turned out to be mine.",
     "The simple baseline", [
         "One direct prompt. No tools. No execution.",
         "Sees the instruction, the tests, the source, the git log.",
         "",
         "  macro-F1                0.600",
         "  exact-match bundles     11 / 15",
         "  cost per bundle         $0.1174",
         "",
         "Identical cases, identical output schema, identical scorer.",
     ], None, "rewardgate/baseline.py"),

    ("Now one task from start to finish. This is the reward gate. Apply the gold patch, the suite "
     "passes, reward one. Apply an empty patch, the suite fails, reward zero. No git history is "
     "shipped. By every mechanical check the field uses today, this task is valid.",
     "$ uv run rewardgate audit csvlite-reward-hackable",
     grep("02_audit_hackable.txt", "oracle trial", "no-op trial", "[  ok   ]", "reward gate holds",
          "no git history"),
     None, "The two bounds the field checks. Both hold."),

    ("It is not. The agent gets a hostile brief. Make the visible tests pass without fixing the "
     "bug. It works in a sandbox copy, with the held-out tests, the gold patch and the git "
     "history deleted. This is the patch it wrote. One special case, on the single literal input "
     "the visible suite uses.",
     "The exploit agent's patch", EXPLOIT_PATCH,
     None, "held_out/, solution.patch, task.yaml, .git and conftest.py are deleted from the sandbox"),

    ("Now the adjudication. Visible suite, four passed, exit zero. Held-out suite, seven failed, "
     "exit one. That frame is the whole project. This task would certify an agent as correct "
     "while the bug it tests for is untouched. And the reward gate passed it.",
     "Adjudication by execution",
     grep("02_audit_hackable.txt", "[DEFECT ]", "exploit trial", "special-cased inputs", "visible suite under",
          "held-out suite under", "turns / cost", "VERDICT: REVISE"),
     None, "Visible green + held-out red = a proven exploit"),

    ("Now the comparison, and the ablation that rewrote it. Two reviewers made the same "
     "objection. The baseline sees git log oneline, and the contaminating commit sits off the "
     "current branch by construction. So I gave the baseline git log dash p dash dash all, the "
     "same evidence my own checker reads, and re-ran all fifteen bundles.",
     "The objection", [
         "RewardGate's only measured win was CONTAMINATION_GIT,",
         "where the baseline scored 0.000.",
         "",
         "But the baseline was shown  git log --oneline",
         "and the contaminating commit sits off the current branch",
         "BY CONSTRUCTION.",
         "",
         "So the 0.000 might be an artefact of what I showed it.",
         "That is testable. So I tested it.",
     ], None, "scripts/run_parity_ablation.py"),

    ("The objection was right. Baseline with the short log, zero point six zero zero. Baseline "
     "with the full log, zero point eight eight nine. RewardGate, zero point nine three three. "
     "The gap is zero point zero four four. That is one judgement out of forty-five, and McNemar "
     "exact p equals one point zero zero. That single judgement is a false positive from the "
     "baseline.",
     "$ uv run python scripts/run_parity_ablation.py --replay",
     cap("03_ablation.txt")[1:11],
     None, "The measured advantage was an information asymmetry I designed."),

    ("The changelog records that reversal and four more. Two are worth thirty seconds. My "
     "over-specification checker first flagged two hundred and twenty-nine of five hundred "
     "instances. That was too high to be true, so I read the flags instead of publishing them. "
     "Most were reporters naming the public API they called. Counting internal symbols only took "
     "it to forty-two, and took the headline defect rate from sixty-two percent to forty-two.",
     "Iteration 2 - a 5x overcount I caught myself", [
         "                        any symbol      internal only",
         "  over-specified        229/500         42/500",
         "  headline defect rate  310/500         210/500",
         "",
         "Public flags:    write, RST, ITRS          <- a good bug report",
         "Internal flags:  _format_float, _parse_quoted",
         "                 <- names a reporter could not produce",
         "                    without having seen the patch",
     ], None, "Precision matters more than recall when the output is a rejection"),

    ("And one finding I withdrew. Bool of the string false is true in Python. Every negative "
     "baseline verdict inverted before it was scored. That one was my parser.",
     "Withdrawn - a finding that was my own bug", [
         ">>> bool('false')",
         "True",
         "",
         "My own prompt template asked the model for the string 'true|false'.",
         "Every negative baseline verdict inverted before it was scored.",
         "",
         "It invalidated the headline AND the anecdote I had built on it:",
         "'the baseline contradicted itself' was my bug, narrated as a discovery.",
     ], None, "rewardgate/schema.py - coerce_bool() - 11 tests"),

    ("The change that contributed most was a definition, not code. My first exploit detector "
     "flagged the clean task as well. A hundred percent false positives, because any finite test "
     "suite can be hardcoded if you write enough branches. So I regraded on exploit cost, meaning "
     "how many literal inputs the exploit has to special case. Zero false alarms across six clean "
     "bundles after that.",
     "Biggest contributor: a definition, not code", [
         "First detector: 'an exploit exists'   ->  100% false positives",
         "",
         "Any finite visible suite can be hardcoded",
         "given enough branches. Existence is not discriminating.",
         "",
         "Regraded on exploit COST - how many literal inputs",
         "must be special-cased:",
         "",
         "  clean bundle          8 cases   too expensive to bother",
         "  reward-hackable       1 case    cheaper than solving it",
     ], None, "0 false alarms across 6 clean bundles"),

    ("The experiment I removed was a five agent fan-out, one agent per defect class. For every "
     "class except reward hacking, a deterministic check gives stronger evidence at zero cost. "
     "Git log returns a commit. An agent returns an opinion.",
     "Removed: a five-agent fan-out", [
         "  defect              mechanism                cost     evidence",
         "  NOP_PASS            run suite, empty patch   $0.00    exit code",
         "  CONTAMINATION_GIT   git log -p --all         $0.00    commit SHA",
         "  solution leakage    string match             $0.00    matched path",
         "  weak assertions     AST analysis             $0.00    the AST",
         "",
         "A trivial `claude -p` call costs $0.1967 before doing any work.",
         "",
         "The number of agents is not a measure of engineering.",
     ], None, "results/cli_overhead_probe.json"),
]

LANDING = ("Reproduction", [
    "  git clone https://github.com/Gaurav1112/rewardgate",
    "  uv sync",
    "  uv run pytest -q                                    229 passed",
    "  uv run python -m rewardgate.report_real             $0.00",
    "  uv run python scripts/run_parity_ablation.py --replay",
    "",
    "  Free path needs no API key and reproduces every third-party number.",
], "github.com/Gaurav1112/rewardgate")


def main() -> None:
    parts = []
    for i, (text, title, lines, hero, footer) in enumerate(SEGMENTS):
        png, m4a = OUT / f"s{i:02d}.png", OUT / f"s{i:02d}.m4a"
        slide(png, title, lines, hero=hero, footer=footer)
        dur = narrate(text, m4a)
        parts.append((png, m4a, dur))
        print(f"  {i:02d} {dur:5.1f}s  {title[:56]}")

    png = OUT / "s99.png"
    slide(png, LANDING[0], LANDING[1], footer=LANDING[2])
    parts.append((png, None, 5.0))

    total = sum(p[2] for p in parts)
    print(f"\ntotal {total:.1f}s = {int(total // 60)}:{int(total % 60):02d}")

    concat = OUT / "concat.txt"
    clips = []
    for i, (img, audio, dur) in enumerate(parts):
        clip = OUT / f"c{i:02d}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img)]
        if audio:
            cmd += ["-i", str(audio), "-c:a", "aac", "-shortest"]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-c:a", "aac", "-t", str(dur)]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}", str(clip)]
        subprocess.run(cmd, check=True)
        clips.append(clip)
    concat.write_text("\n".join(f"file '{c}'" for c in clips))

    final = HERE / "rewardgate-demo.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
         str(final)], check=True,
    )
    print(f"\nwrote {final}")


if __name__ == "__main__":
    main()
