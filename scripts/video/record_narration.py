"""Record the narration in your own voice, one section at a time.

The composer reads whatever audio sits in `scripts/video/out/sNN.m4a` and times each slide to the
length of its clip. So replacing the synthetic narration is just a matter of overwriting those
twelve files — the slides re-time themselves around your pacing, and nothing needs re-editing.

    uv run python scripts/video/record_narration.py          # all twelve, in order
    uv run python scripts/video/record_narration.py 3 7      # retake only sections 3 and 7
    uv run --with pillow python scripts/video/compose.py     # rebuild the video

Press ENTER to start a section, ENTER again to stop. Anything you dislike, record again — the
composer only ever reads the current file.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build as B  # noqa: E402

MIC = ":0"  # `ffmpeg -f avfoundation -list_devices true -i ""` to confirm the index
BOLD, DIM, GREEN, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[0m"


def record(index: int, text: str, title: str) -> None:
    dest = B.OUT / f"s{index:02d}.m4a"
    print(f"\n{BOLD}── Section {index:02d} — {title}{RESET}")
    print(DIM + "─" * 78 + RESET)
    for para in text.split(". "):
        print(textwrap.fill(para.strip().rstrip(".") + ".", 76, initial_indent="  ",
                            subsequent_indent="  "))
    print(DIM + "─" * 78 + RESET)
    print(f"{DIM}~{len(text.split()) / 2.5:.0f}s at a natural pace. "
          f"Read it flat; the reversals are results, not apologies.{RESET}")

    if input(f"\n  ENTER to record, or 's' to skip: ").strip().lower() == "s":
        print("  skipped, existing clip kept")
        return

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "avfoundation", "-i", MIC,
         "-ac", "1", "-ar", "44100", "-c:a", "aac", "-b:a", "160k", str(dest)],
        stdin=subprocess.PIPE,
    )
    input(f"  {GREEN}● recording{RESET} — ENTER to stop ")
    proc.communicate(b"q")

    if dest.exists() and dest.stat().st_size > 4096:
        print(f"  saved {dest.name}")
    else:
        print("  nothing captured. Check Terminal has microphone permission in "
              "System Settings > Privacy & Security > Microphone.")


def main() -> None:
    wanted = {int(a) for a in sys.argv[1:] if a.isdigit()}
    print(__doc__.split("\n\n")[0])
    print(f"{DIM}Microphone {MIC}. Terminal needs mic permission the first time.{RESET}")

    for i, (text, title, *_rest) in enumerate(B.SEGMENTS):
        if wanted and i not in wanted:
            continue
        record(i, text, title)

    print(f"\n{BOLD}Done.{RESET} Rebuild with:")
    print("  uv run --with pillow python scripts/video/compose.py")


if __name__ == "__main__":
    main()
