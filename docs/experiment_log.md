# Experiment log

Chronological record of every run, submission and finding. Raw outputs live in `kaggle_runs/<run>/`
(not in git: they contain competition data). Times are UTC unless noted.

| Date | ID | What | Agent / config | Result |
|---|---|---|---|---|
| 2026-10-13 | NB v1 | First push (API) | `submission/` v1 (single agent, 28 calls / 8 min, contract prompt) | ERROR: no GPU — API push cannot get L4 |
| 2026-10-13 | NB v2 | Dev run, web UI, GPU L4 x4 | v1 agent, 6 dev tasks | 0/6 resolved; 2669 s |
| 2026-10-13 | SUB 57149248 | Submit NB v2 | v1 agent | Kaggle Error (submitted before zip existed; no slot used) |
| 2026-10-13 | SUB 57151403 | Resubmit | v1 agent | **LB 0.15** |
| 2026-10-13 | ANALYSIS | Trace diagnosis of NB v2 | — | Failure modes: no edit before budget end 5/6, compaction amnesia 5/6, whole-file reads 5/6, malformed read_file args 3/6 (14 calls), protected-file edit 1/6 |
| 2026-10-14 | NB v4 | Dev run, web UI | `submission/` v4 (no read_file, sed reads, edit by call 8, compaction note, NOTES line), 10 dev tasks + gold check | 0/10 resolved; gold check 6/10 (httpx/requests not gradable locally) |
| 2026-10-17 | RESEARCH | Public notebooks + forum + literature | — | `docs/literature.md`; all 0.18–0.24 entries share one bundle; LB noise ±0.08; tool budget 50→25 costs 14/129 tasks |
| 2026-10-17 | GOLD v1 | CPU gold check on all 129 public tasks (`gemma-4-agent-gold-check`) | reference patches | **75/129 gradable** (rich 43/48, fastapi 31/67, requests 1/13, httpx 0/1); 24 min CPU; list in `dev/validated_tasks.txt` |
| 2026-10-17 | NB v6 | Submit-only (CPU) | `agents/public_baseline` (honghanhhh prompt, unchanged) | zip built |
| 2026-10-17 | SUB 57318831 | Submit NB v6 | public baseline | COMPLETE but **no score** (cause unknown; checked 2026-10-30) |
| 2026-10-17 | NB v7 | E1 anytime run (to start in web UI, L4 x4) | `agents/baseline_b50` (50 calls / 12 min), 75 validated tasks, concurrency 3, anytime recorder on | not started: Kaggle GPU cap reached 2026-10-18; start next session. 2026-10-30: still never ran; weekly GPU 27.75/30 h used by other projects |

| 2026-10-30 | REVIEW | Critic + inventor agents | — | Critic: unscored baseline likely from CPU-only submit notebook (scored v1 came from L4 notebook) and/or 12 h risk; rule 120*(T+0.5)<=11 h -> T<=4.5 min; submit from L4 notebooks; measure on paired fixed subsets. Inventor: Skill-Compressed Single agent (deterministic localizer/view/check skills) + hazard deadline; Ledger Relay (staged fresh contexts) as paper challenger. |
| 2026-10-30 | EDA v1/v2 | Public EDA `gemma-4-where-does-the-fix-go-eda` (CPU) | tasks/graphs/embeddings | 7.8% gold patches >200 lines; issue names edited symbol in 19-27% (fastapi/rich); 122 tasks have edited symbol in graph; 53% within 2 hops of an issue-mentioned symbol, 89% within 6; safe cap (1 h margin) 34 calls. Made public (v2). |
| 2026-10-30 | AGENT scs | `agents/scs`: our Skill-Compressed Single agent | skill swe-tools (start/locate/view/check, installed in .git/swe), contract prompt, edit by call 8, 30 calls / 4.5 min / 90 s cmd timeout, thinking 2048 | validated + compiled; ADK wrapper path tested locally; localizer on 3 local snapshots: file@6 3/3, symbol@10 2/3 |

| 2026-10-30 | INTEL | Rules/prizes page + leaderboards | — | Main LB top 0.24 (6-way tie). **Small Model Prize (, Gemma E2B/E4B only): top 0.10** (311 teams). **Paper track () deadline 2026-11-12**; topics: PEFT/RL, code-graph comprehension, tasks/benchmarks, graph reasoning; graph+embedding data encouraged. 12 h limit includes sandbox setup, excludes validation. |

| 2026-10-30 | NB v9 (pushed) | SCS agent notebook uploaded (API push after CPU-session limit cleared) | `agents/scs`, 10 stratified validated tasks, concurrency 1, anytime recorder | to run in web UI on L4 x4, then submit that version |

## Planned
- E1 anytime run: `agents/baseline_b50` (50 calls / 12 min) on gold-validated tasks with the anytime recorder
  (diff after every tool call) → CPU replay → curve P(resolved | stopped at call c) + per-call timing →
  chance-constrained choice of call/time caps under the 12 h limit.
