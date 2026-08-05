# Model bake-off harness

Reusable metadata extractor for same-task / many-model subagent experiments.

Run one task across N models (each in its own git worktree, via the `Agent`
tool with a `model` override and `isolation: "worktree"`), then point this
harness at the results. It joins three legally-accessible, on-disk sources per
run — no privileged access, no reading whole transcripts into any model's
context:

| source | fields |
|---|---|
| subagent transcript `usage` | model, input/output/cache tokens, duration, turns, thinking/text blocks, tool errors |
| subagent transcript `content` | ordered tool-call event stream + inter-call latency |
| agent git worktree diff | files changed, insertions, deletions (untracked included) |

## Usage

```bash
python3 research/bakeoff/extract.py                 # auto-discover this session's runs
python3 research/bakeoff/extract.py \
    --transcripts-dir /path/to/tasks \              # dir of agent-*.jsonl or *.output symlinks
    --worktrees-dir  .claude/worktrees \            # default: <repo>/.claude/worktrees
    --since 2026-07-11 \                            # filter by run start date
    --out research/bakeoff/out
```

Auto-discovery resolves `*.output` symlinks to their real `.jsonl` targets and,
absent `--transcripts-dir`, walks `$CLAUDE_PROJECT_DIR/../subagents` then
`~/.claude/projects/**/subagents/`.

## Outputs (`out/`)

- **`summary.csv`** / **`summary.json`** — one row per run. CSV for notebooks;
  JSON additionally carries `tool_breakdown` and `changed_files`.
- **`events.jsonl`** — one line per tool call: `{run_id, model, ts, tool, arg, dt_s}`.
  `dt_s` is seconds since the previous call — use it for latency distributions
  and to spot "thinking pauses" (e.g. a long gap before a design decision).

## Design notes

- Stdlib only; no dependencies.
- Token totals sum per-message `usage` (counted once per assistant turn, not
  per content block) so cache-read vs. cache-create stays honest.
- Worktree stats use `git add -A -N` (intent-to-add) so new files appear in
  `numstat`, then clear the intent — never staging content or mutating files.
- Every run is self-labelling: model id comes from the transcript, so a mislabel
  in the dispatch layer can't corrupt the dataset.

`out/` is gitignored — it's per-session data. Commit the harness, regenerate the
data.
