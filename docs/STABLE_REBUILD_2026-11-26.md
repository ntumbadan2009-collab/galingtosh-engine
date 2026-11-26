# Galingtosh stable reconstruction — 2026-11-26
Status: candidate only. No production deployment authorized by this branch until release gates pass.

## Reference and rollback
Render was running 2d7412168d5ee82069a0565881c56291fd121050 at the times of the two completed missions on 23 November (86.304 s and 87.36 s). This identifies the engine revision, not the exact historical Edge function revision. Backups: backup/2026-11-23-render-reference, backup/2026-11-26-main, backup/2026-11-26-live-v32. Main's engine retains all levels 1–12 and historical checkpoint/render safeguards. The branch is based on the exact deployed v32 agent archive to avoid silently losing newer capabilities.

## Architecture and gates
Server-owned phases: script -> research from real passages -> measured voice -> deterministic scene layout -> scoped creative visual decisions and bounded actual-media evidence -> montage -> independent plan review -> rendering -> technical and cinematic review. No fabricated evidence, no code-only complete movie, no disabled strict gates. Provider unavailability is distinct from editorial failure; backoff is recorded in the durable task ledger and not charged to the logical retry count. Do not rotate into cooling models. Provider failure still has a finite budget. Media choices are scoped by shot; rejected candidates are not reused within the slot. Research evidence uses server-selected literal passages and sentence claims, not model-transcribed quotations. Research still requires two different works/organizations including one publication. No promise that this validates semantic entailment without the model.

## Release checklist
1. Deno check and unit tests, Python engine integration tests, verify wake RPC can wake preparation as well as render.
2. Separate staging database / worker and test credentials; exercise 429, interrupted worker, rejected media, duplicate task, unavailable evidence and replay.
3. New 30 s, 60 s, 180 s missions: all reach verified output, no manual Continue; inspect playback, narration/visual alignment, audio, subtitles, aspect and duration. Record metrics and actual output paths.
4. No main merge or production release until those gates pass. Roll back via backups rather than modifying a working deployment blindly.
Known limitations: estimated beats and subtitle timing are not word-level alignment; no evidence of current provider capacity; current V32 mission failed research. Exact historical Edge source is not recovered merely from engine commit. No production end-to-end test claimed in this PR.
