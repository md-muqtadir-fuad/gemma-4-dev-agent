# Literature notes (collected 2026-10-17)

IDs marked (v) were checked on arXiv; others are from memory and must be verified before citing.

## SWE agents for small/open models
- Agentless — Xia et al. 2024, arXiv:2407.01489. Localize (file→function→line) → sample repairs → filter with reproduction/regression tests. Kimi-Dev (v) arXiv:2509.23045: Agentless-style skills transfer to agents.
- SWE-agent — Yang et al. 2024, arXiv:2405.15793 (agent-computer interface design: windowed viewer, lint-guarded edit).
- AutoCodeRover arXiv:2404.05427; SpecRover arXiv:2408.02232; OpenHands arXiv:2407.16741.
- SWE-Search (MCTS + value agent) arXiv:2410.20285; CodeMonkeys arXiv:2501.14723.
- Gyms/training: SWE-Gym arXiv:2412.21139; R2E-Gym arXiv:2504.07164; SWE-smith arXiv:2504.21798; SWE-RL arXiv:2502.18449; Satori-SWE (v) arXiv:2505.23604. Verifier/selection adds ~10–17 pts.
- Localization: LocAgent arXiv:2503.09089 (graph search); OrcaLoca arXiv:2502.00350.
- Reproduction tests: SWT-bench arXiv:2406.12952; Otter arXiv:2502.05368.
- Overthinking / analysis paralysis predicts failure: Cuadron et al. arXiv:2502.08235.
- Survey: test-time scaling for SWE arXiv:2601.22129.

## Budget-aware / compute-optimal
- Snell et al. 2024 arXiv:2408.03314 (compute-optimal test-time scaling).
- s1 budget forcing arXiv:2501.19393.
- BATS / Budget Tracker (v) arXiv:2511.17006 — continuous remaining-budget signal + dig-deeper/pivot rule.
- Optimal stopping vs best-of-N (Pandora's box) (v) arXiv:2510.01394; BEACON arXiv:2510.15945; CAM-DF arXiv:2607.27083.
- Fail-Fast, Restart-Smart arXiv:2608.03222 — learned failure monitor on SWE-bench Verified (closest prior art to restarts).
- SWE-Effi arXiv:2509.09853 — unresolved runs consume most resources.

## Context management
- The Complexity Trap (v) arXiv:2508.21433 — observation masking ≈ or > LLM summarization at half the cost.
- ACON (v) arXiv:2510.00615 — context compression guideline optimization, small LMs +46%.
- MemGPT arXiv:2310.08560; ACE arXiv:2510.04618.
- ADK: `include_contents: none` + `output_key`/`{var}` = staged fresh contexts with explicit state handoff.

## OR / game theory / bandits / evolution
- OPRO arXiv:2309.03409; EvoPrompt arXiv:2309.08532; PromptBreeder arXiv:2309.16797; GEPA arXiv:2507.19457.
- TRIPLE (bandit prompt selection) arXiv:2402.09723; successive halving arXiv:1502.07943; Hyperband arXiv:1603.06560.
- AFlow arXiv:2410.10762; ADAS arXiv:2408.08435.
- Consensus Game arXiv:2310.09139; multi-agent debate arXiv:2305.14325.
- Luby, Sinclair & Zuckerman 1993, Optimal speedup of Las Vegas algorithms (restart cutoffs for heavy-tailed run times).

## Candidate paper angles
A. Restart-optimal stage decomposition ("Las Vegas agents"): staged sub-agents with fresh contexts and a carried sufficient statistic; cutoff τ* derived from empirical run-time distribution (Luby).
B. Hazard-derived exploration deadline + budget tracker: optimal-stopping step t* for the explore→edit switch estimated from logged trajectories (Kaplan–Meier).
C. Paired successive halving (McNemar elimination) + GEPA-style reflective mutation for evaluation-limited agent config search.
Recommended: A+B as the method, C as the tuning procedure. Caveat: n≈120 → SE ≈ 4.5 pts; use paired tests.

## Competition evidence (public notebooks + forum, 2026-10-17)
- All 0.18-0.24 public entries use the same bundle: 31B single agent, temp 0.2, top_p 0.95, max_output 8192, thinking_budget 4096 + include_thoughts true; eval_config 240 s / 28 calls / 8 min / 80 turns; only the prompt differs (contract-first, edit by call 8-12, batched short greps, sed reads <=40 lines, edit-failure fallback, parallel implementations, never empty diff).
- LB noise ~+-2 tasks (~+-0.08 at 95%) on ~58-60 public tasks; same package re-scored 0.15/0.13/0.15. Leaderboard spread may be binomial noise.
- Ayush Thakur ablations (129 tasks): thinking off 48->23 solved; thought summaries off 51->35; tool budget 50->25 cost 14 tasks; temperature/top_p/thinking budget +-0-3; analyzer sub-agent +1.
- Gluzdov (692 local runs): 28% no patch; all 75 context overflows had empty patches; runs ending <=14 calls resolved 52%, 15-20 calls 5%. Temp 0.4 scored 0.12 vs 0.18 at 0.2.
- Kaggle 4xL4: ~8.68 s per model call with thinking; 4.5-min cap took ~10 h total (~0.5 min/task overhead); >12 h errors the whole submission.
- Localization: first identifier-grep hit correct 30%; grep+BM25 top-5 61%, top-10 74%; 35/128 issues contain no code identifier.
- Wheelhouse v29/v30: thinking_budget 0 disables thinking (include_thoughts false no longer does).
