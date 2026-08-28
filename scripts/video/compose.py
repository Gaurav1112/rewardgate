"""Render the slides and compose the final video.

Reuses whatever narration sits in `out/sNN.m4a`, so re-recording in a human voice needs no
re-editing here.

Design notes, because the first cut failed a blunt test — "could a viewer follow this with the
sound off?" — and the answer was no:

* Every slide states its point in plain English above the terminal output. A raw `stdout` dump with
  a title is evidence, not an explanation, and a judge scanning at speed sees only the dump.
* The narration is burned in as captions. Captions also make the video legible in a noisy room, on
  mute, and to anyone who is not a native English speaker.
* Key numbers get a labelled callout, so the one line that matters is not the same weight as the
  fifteen lines around it.
* A progress bar shows where you are in five minutes.

Two rendering bugs are also fixed here and worth naming: colour was keyed on the substring
"failed", so `failed=0` — the *good* outcome — rendered red; and the mp4 concat demuxer doubled the
runtime (279s of clips became 559s), so composition is now from an image sequence against one
continuous audio track.
"""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import build as B

OUT = B.OUT
CAPTION_BG = (22, 27, 34)
PANEL = (17, 22, 29)
BORDER = (48, 54, 61)

F_TAKE = B.mono(31)
F_CAP = B.mono(28)
F_TERM = B.mono(23)
F_TINY = B.mono(19)

# (takeaway, [(substring to find, callout label)]) per section index.
META: dict[int, tuple[str, list[tuple[str, str]]]] = {
    0: ("Benchmark tasks train coding agents. A lot of them are broken.", []),
    1: ("42% of a real, widely-used benchmark carries at least one defect.",
        [("AT LEAST ONE DEFECT", "the headline: 210 of 500, for $0.00"),
         ("solution leakage", "published figure is 135 — mine is 133, on a corpus I did not build")]),
    2: ("The baseline is a competent reader, not a straw man.", []),
    3: ("Both bounds the field checks today are satisfied. The task still looks valid.",
        [("oracle trial", "gold patch applied -> suite passes"),
         ("no-op trial", "empty patch -> suite fails")]),
    4: ("The agent is told to make the tests pass WITHOUT fixing the bug.", []),
    5: ("Visible tests green, held-out tests red. That is a proven exploit.",
        [("visible suite under", "the graded suite passes"),
         ("held-out suite under", "the bug is still there")]),
    6: ("My own headline might have been an artefact of what I showed the baseline.", []),
    7: ("Given the same evidence, the baseline nearly matches. The gap is one judgement.",
        [("git log -p --all", "same evidence my checker reads -> 0.889"),
         ("McNemar", "p = 1.00. Not distinguishable from zero.")]),
    8: ("A number too high to be true, so I read the flags instead of publishing them.", []),
    9: ("bool('false') is True in Python. That one was my parser.", []),
    10: ("Any suite can be hardcoded. The question is what it costs.", []),
    11: ("The cheapest mechanism that can prove a claim is usually not a model.", []),
}
LANDING_TAKE = "Everything above reproduces from a clean clone, free, with no API key."


def colour_for(line: str) -> tuple[int, int, int]:
    l = line.lower().strip()
    if not l:
        return B.FG
    if l.startswith("$") or l.startswith("git clone") or l.startswith("uv "):
        return B.ACCENT
    if "[defect" in l or "reject" in l:
        return B.BAD
    if "[  ok" in l or "accept" in l:
        return B.GOOD
    if "verdict" in l or "[skipped" in l or "revise" in l or "indeterminate" in l:
        return B.WARN
    # exit=1 / failed=N (N>0) is the red signal; failed=0 is not.
    if re.search(r"failed=(?!0\b)\d+", l) or "exit=1" in l:
        return B.BAD
    if re.search(r"passed=(?!0\b)\d+", l) or "exit=0" in l or " passed" in l:
        return B.GOOD
    return B.FG


def wrap(raw: str, width: int) -> list[str]:
    if len(raw) <= width:
        return [raw]
    indent = " " * (len(raw) - len(raw.lstrip()) + 4)
    out, cur = [], ""
    for w in raw.split():
        nxt = f"{cur} {w}".strip()
        if len(nxt) > width and cur:
            out.append(cur)
            cur = indent + w
        else:
            cur = nxt
    if cur:
        out.append(cur)
    return out


def slide(path: Path, title: str, lines: list[str], takeaway: str, caption: str,
          callouts: list[tuple[str, str]], footer: str, progress: float) -> None:
    img = Image.new("RGB", (B.W, B.H), B.BG)
    d = ImageDraw.Draw(img)

    d.text((90, 48), title, font=B.F_TITLE, fill=B.ACCENT)
    for i, ln in enumerate(wrap(takeaway, 92)[:2]):
        d.text((90, 118 + i * 40), ln, font=F_TAKE, fill=B.FG)

    top = 118 + 40 * len(wrap(takeaway, 92)[:2]) + 22
    # Fit the panel to its content. A fixed-height box left a third of the frame empty on the
    # short slides, which reads as an unfinished template rather than a considered layout.
    rendered = sum(len(wrap(raw, 96)) for raw in lines)
    bottom = min(B.H - 240, top + 52 + rendered * (F_TERM.size + 11))
    d.rounded_rectangle([80, top, B.W - 80, bottom], radius=10, fill=PANEL, outline=BORDER, width=2)

    y = top + 26
    note_targets = dict(callouts)
    for raw in lines:
        fill = colour_for(raw)
        for ln in wrap(raw, 96):
            if y > bottom - 40:
                break
            d.text((112, y), ln, font=F_TERM, fill=fill)
            for needle, label in list(note_targets.items()):
                if needle in ln:
                    x = 112 + int(d.textlength(ln, font=F_TERM)) + 26
                    if x < B.W - 340:
                        d.text((x, y + 3), f"<- {label}", font=F_TINY, fill=B.WARN)
                    note_targets.pop(needle, None)
            y += F_TERM.size + 11
        if y > bottom - 40:
            break

    if footer:
        d.text((90, bottom + 14), footer, font=F_TINY, fill=B.DIM)

    if caption:
        d.rectangle([0, B.H - 190, B.W, B.H - 46], fill=CAPTION_BG)
        for i, ln in enumerate(textwrap.wrap(caption, 88)[:3]):
            d.text((90, B.H - 172 + i * 42), ln, font=F_CAP, fill=B.FG)

    d.rectangle([0, B.H - 8, B.W, B.H], fill=BORDER)
    d.rectangle([0, B.H - 8, int(B.W * progress), B.H], fill=B.ACCENT)
    img.save(path)


def caption_chunks(text: str, max_chars: int = 150) -> list[str]:
    """Split narration into caption-sized pieces on sentence boundaries."""
    chunks, cur = [], ""
    for sentence in re.split(r"(?<=[.?!]) +", text.strip()):
        if len(cur) + len(sentence) + 1 > max_chars and cur:
            chunks.append(cur.strip())
            cur = sentence
        else:
            cur = f"{cur} {sentence}".strip()
    if cur:
        chunks.append(cur.strip())
    return chunks or [""]


def duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def main() -> None:
    frames: list[tuple[Path, float]] = []
    audios: list[Path] = []
    section_secs = [duration(OUT / f"s{i:02d}.m4a") for i in range(len(B.SEGMENTS))]
    total_secs = sum(section_secs) + 6.0
    elapsed = 0.0

    for i, (text, title, lines, _hero, footer) in enumerate(B.SEGMENTS):
        take, callouts = META.get(i, ("", []))
        chunks = caption_chunks(text)
        weights = [max(len(c), 1) for c in chunks]
        span = section_secs[i]
        for j, chunk in enumerate(chunks):
            share = span * weights[j] / sum(weights)
            png = OUT / f"f{i:02d}_{j:02d}.png"
            slide(png, title, lines, take, chunk, callouts, footer,
                  min((elapsed + share / 2) / total_secs, 1.0))
            frames.append((png, share))
            elapsed += share
        audios.append(OUT / f"s{i:02d}.m4a")
        print(f"  {i:02d} {span:5.1f}s  {len(chunks)} captions  {title[:48]}")

    landing = OUT / "f99.png"
    slide(landing, B.LANDING[0], B.LANDING[1], LANDING_TAKE, "", [], B.LANDING[2], 1.0)
    frames.append((landing, 6.0))

    print(f"\ntotal {total_secs:.1f}s = {int(total_secs // 60)}:{int(total_secs % 60):02d}"
          f" across {len(frames)} frames")

    silence = OUT / "silence.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "anullsrc=r=44100:cl=stereo", "-t", "6", "-c:a", "aac", str(silence)], check=True,
    )

    # Decode to PCM and join in the filter graph. Stream-copying the AAC files appends each one's
    # encoder priming padding, which added 16 seconds and walked the slides out of sync.
    voice = OUT / "voice.wav"
    inputs: list[str] = []
    for p in audios + [silence]:
        inputs += ["-i", str(p)]
    n = len(audios) + 1
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", "".join(f"[{k}:a]" for k in range(n)) + f"concat=n={n}:v=0:a=1[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", str(voice)], check=True,
    )
    print(f"  voice {duration(voice):.1f}s against {total_secs:.1f}s of slides")

    # The concat demuxer drops the final frame unless it is repeated without a duration.
    ilist = OUT / "images.txt"
    ilist.write_text(
        "".join(f"file '{p}'\nduration {d:.3f}\n" for p, d in frames)
        + f"file '{frames[-1][0]}'\n"
    )

    final = B.HERE / "rewardgate-demo.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(ilist), "-i", str(voice),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-r", "25", "-fps_mode", "cfr", "-c:a", "aac", "-b:a", "160k",
         "-shortest", "-movflags", "+faststart", str(final)], check=True,
    )
    print(f"wrote {final}  ({duration(final):.1f}s)")


if __name__ == "__main__":
    main()
