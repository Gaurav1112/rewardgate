# How the solution video was made

`../../docs/VIDEO_SCRIPT.md` is the script. This directory is the renderer, so the video is
reproducible on the same terms as every other number in this project.

```bash
uv run --with pillow python scripts/video/build.py     # narration + first pass
uv run --with pillow python scripts/video/compose.py   # slides + final mux
```

Output: `rewardgate-demo.mp4`, 1920×1080, 4:46.

## Stated plainly: the voice is synthetic, the content is not

The narration is read by macOS `say` (the `Daniel` voice). Saying so here rather than letting a
viewer work it out is the point of this section.

What that does and does not cover. **The script is written, not generated** — it is
`docs/VIDEO_SCRIPT.md`, committed, unedited, and read verbatim. **Every frame on screen is output
this repository actually produced**: `cap/` holds the captured `stdout` of the real commands and
the slides are rendered from those files, so nothing was retyped into a mockup. The one exception
is the exploit-patch slide, transcribed from
`trajectories/exploit-agent-csvlite-reward-hackable.md` because the report truncates the patch for
display.

So the voice is a rendering choice over authored, verifiable content. `record_narration.py`
replaces the twelve audio clips with a human reading and `compose.py` re-times the slides around
the new pacing — the path is built and documented, and it was a deliberate decision not to take it
before the deadline rather than an oversight.

## What is and is not generated

Everything on screen is **real output this repository produced**. `cap/` holds the captured
`stdout` of four commands, verbatim, and the slides are rendered from those files — no text was
retyped into a mockup. The narration is the committed script, unedited.

The exception is the exploit patch slide, which is transcribed from
`trajectories/exploit-agent-csvlite-reward-hackable.md` rather than captured, because the report
truncates the patch for display.

## Two bugs worth recording, since both were invisible until the video was built

**The agent tier was broken.** Capturing a live `rewardgate audit` for the demo failed with
`mcpServers: Invalid input: expected record, received undefined` — a Claude Code CLI change had
made `--mcp-config '{}'` invalid, so *every* exploit trial errored. The audit correctly returned
`INDETERMINATE` rather than `ACCEPT`, so the fail-closed design held, but the test suite never touches the
real CLI invocation and none of them noticed. Recording a demo exercised a boundary the test suite
mocks.

**The first render was 9:18, not 4:39.** The mp4 concat demuxer doubled the runtime, and
stream-copying the per-segment AAC files appended 16 seconds of encoder priming padding that walked
the slides out of sync with the voice reading them. Both are fixed in `compose.py`; the durations
are asserted against the audio track at build time rather than assumed.

## Recording it in your own voice

The composer times each slide to the length of its audio clip, so replacing the narration needs no
re-editing — the slides re-time themselves around your pacing.

```bash
uv run python scripts/video/record_narration.py        # 12 clips, ENTER to start/stop each
uv run python scripts/video/record_narration.py 3 7    # retake only 3 and 7
uv run --with pillow python scripts/video/compose.py   # rebuild
```

Twelve clips, 11–34 seconds each, ~4.6 minutes of speech in total. Each section prints its own
text before recording, so no separate teleprompter is needed. Terminal needs microphone permission
under System Settings → Privacy & Security → Microphone the first time.

`tts_backup/` holds the synthetic take. Copy it back over `out/` to restore it.
