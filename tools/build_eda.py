"""Generate the public EDA notebook (kaggle_eda/) for the Gemma 4 Developer Agent competition.

Question it answers: how much do the issue text, the released code graph and the node embeddings
reveal about WHERE the fix goes, and what does the 12 h limit allow per task?

Usage:  .venv\\Scripts\\python.exe tools\\build_eda.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / 'kaggle_eda'
SLUG = 'gemma-4-where-does-the-fix-go-eda'
TITLE = 'Gemma 4: Where Does the Fix Go? (EDA)'

CELLS = []


def md(text):
    CELLS.append(('markdown', text.strip('\n')))


def code(text):
    CELLS.append(('code', text.strip('\n')))


md("""
# Where does the fix go? Issue text, code graph and embeddings vs. the gold patches

Most failed agent runs we inspected never reached the right function before their tool budget ran out.
This notebook measures, on the 129 public tasks, **how much localization signal is available before the
agent makes a single tool call**:

1. **Task anatomy**: what the gold patches touch (files, symbols, new files, size), and what the hidden tests look like.
2. **Issue-text leakage**: how often the issue names the edited file or symbol.
3. **Code graph**: whether edited symbols exist as graph nodes and how far they are from the symbols the issue mentions.
4. **Retrieval baselines**: BM25 over node source text, embedding similarity, and graph proximity. We report recall@k of the edited symbol.
5. **Budget arithmetic**: what the 12-hour limit allows per task.
6. **Which tasks can be graded locally**: reference solutions that pass the subprocess grader.

Everything runs on CPU using only the competition data.
""")

code("""
import json, math, re, collections
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx

DATA = next(p for p in [Path('/kaggle/input/competitions/gemma-4-developer-agent'), Path('data')]
            if (p / 'tasks.jsonl').exists())
tasks = pd.DataFrame([json.loads(l) for l in open(DATA / 'tasks.jsonl', encoding='utf-8')])
tasks['repo_short'] = tasks.repo.str.split('/').str[-1].str.lower()
print(len(tasks), 'tasks from', DATA)
tasks.groupby('repo').size().rename('tasks').to_frame()
""")

md("## 1. Task anatomy")

code("""
def parse_patch(patch):
    \"\"\"Files, added/removed line counts, new files and touched symbol names from a unified diff.\"\"\"
    files, new_files, added, removed, symbols = [], set(), 0, 0, set()
    for line in patch.splitlines():
        if line.startswith('+++ '):
            path = line[4:].strip()
            if path.startswith('b/'):
                path = path[2:]
            files.append(path)
        elif line.startswith('@@'):
            if line.startswith('@@ -0,0 ') and files:  # hunk creating a whole new file
                new_files.add(files[-1])
            m = re.search(r'@@.*@@\\s*(?:async\\s+)?(?:def|class)\\s+([A-Za-z_]\\w*)', line)
            if m:
                symbols.add(m.group(1))
        elif line.startswith('+') and not line.startswith('+++'):
            added += 1
            m = re.match(r'\\+\\s*(?:async\\s+)?(?:def|class)\\s+([A-Za-z_]\\w*)', line)
            if m:
                symbols.add(m.group(1))
        elif line.startswith('-') and not line.startswith('---'):
            removed += 1
    return files, len(new_files), added, removed, sorted(symbols)

anat = tasks.patch.apply(parse_patch).apply(pd.Series)
anat.columns = ['files', 'n_new_files', 'added', 'removed', 'symbols']
tasks = pd.concat([tasks, anat], axis=1)
tasks['n_files'] = tasks.files.str.len()
tasks['churn'] = tasks.added + tasks.removed
tasks['docs_src_only'] = tasks.files.apply(lambda fs: bool(fs) and all(f.startswith('docs_src/') for f in fs))
tasks['n_test_funcs'] = tasks.test_patch.str.count(r'\\n\\+\\s*(?:async\\s+)?def test_')
tasks['issue_chars'] = tasks.problem_statement.str.len()

summary = tasks.groupby('repo').agg(
    tasks=('instance_id', 'size'), median_files=('n_files', 'median'), median_churn=('churn', 'median'),
    p90_churn=('churn', lambda s: s.quantile(.9)), with_new_file=('n_new_files', lambda s: (s > 0).mean()),
    docs_src_only=('docs_src_only', 'mean'), median_new_tests=('n_test_funcs', 'median'),
    median_issue_chars=('issue_chars', 'median'), has_hints=('hints_text', lambda s: (s.str.len() > 0).mean()))
summary.round(2)
""")

code("""
fig, ax = plt.subplots(1, 3, figsize=(15, 3.6))
for repo, g in tasks.groupby('repo_short'):
    ax[0].hist(np.log10(g.churn + 1), bins=20, alpha=.55, label=repo)
ax[0].set(title='Gold patch size (log10 changed lines + 1)', xlabel='log10(lines)')
ax[0].legend()
ax[1].hist(tasks.n_files.clip(upper=15), bins=15, color='C4')
ax[1].set(title='Files touched by gold patch (clipped at 15)', xlabel='files')
ax[2].scatter(tasks.issue_chars, tasks.churn, s=12, alpha=.6)
ax[2].set(xscale='log', yscale='log', title='Issue length vs patch size', xlabel='issue chars', ylabel='changed lines')
plt.tight_layout(); plt.show()
print('Share of tasks with a gold patch over 200 changed lines:', round((tasks.churn > 200).mean(), 3))
""")

md("""
A minority of tasks need very large gold patches (new modules, generated tables, many files). Under a budget of
about 28 tool calls these are close to infeasible, while the median task changes only a few dozen lines.
""")

md("## 2. Does the issue text name the location?")

code("""
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{3,}')
STOP = set('self None True False return import from class with this that have should when where which there '
           'their would could about using value values issue issues fixes fixed error errors test tests '
           'python code docs example examples default param params function method change changes'.split())

def identifiers(text):
    return {t for t in IDENT.findall(text or '') if t.lower() not in STOP}

def leak(row):
    text = (row.problem_statement or '') + '\\n' + (row.hints_text or '')
    ids = identifiers(text)
    low = text.lower()
    file_named = any(Path(f).name.lower() in low or f.lower() in low for f in row.files)
    sym_named = any(s in ids for s in row.symbols)
    return pd.Series({'issue_identifiers': len(ids), 'names_file': file_named, 'names_symbol': sym_named,
                      'names_any': file_named or sym_named})

tasks = pd.concat([tasks, tasks.apply(leak, axis=1)], axis=1)
tasks.groupby('repo')[['names_file', 'names_symbol', 'names_any']].mean().round(2)
""")

md("## 3. The code graph: are the edited symbols in it, and how close are they to what the issue mentions?")

code("""
def graph_path(row, kind):
    ext = 'json' if kind == 'graphs' else 'npz'
    return DATA / kind / f'{row.repo_short}_{row.base_commit}.{ext}'

def module_of(path):
    p = path[:-3] if path.endswith('.py') else path
    parts = [x for x in p.split('/') if x not in ('src',)]
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)

def gold_nodes(row, names):
    \"\"\"Graph nodes for symbols the gold patch defines or edits (module-aware suffix match).\"\"\"
    mods = [module_of(f) for f in row.files if f.endswith('.py')]
    hits = set()
    for n in names:
        last = n.rsplit('.', 1)[-1]
        if last in row.symbols:
            mod_ok = any(n.startswith(m + '.') or ('.' + m.split('.', 1)[-1] + '.') in ('.' + n) for m in mods)
            if mod_ok or not mods:
                hits.add(n)
    return hits

rows = []
for row in tasks.itertuples():
    gp = graph_path(row, 'graphs')
    if not gp.exists() or not row.symbols:
        continue
    g = json.load(open(gp, encoding='utf-8'))
    names = [n['id'] for n in g['nodes']]
    gold = gold_nodes(row, names)
    ids = identifiers((row.problem_statement or '') + ' ' + (row.hints_text or ''))
    mentioned = {n for n in names if n.rsplit('.', 1)[-1] in ids}
    G = nx.Graph()
    G.add_nodes_from(names)
    G.add_edges_from((e['source'], e['target']) for e in g['edges'])
    dist = None
    if gold and mentioned:
        lengths = nx.multi_source_dijkstra_path_length(G, list(mentioned)[:200], cutoff=6)
        d = [lengths[n] for n in gold if n in lengths]
        dist = min(d) if d else math.inf
    rows.append({'instance_id': row.instance_id, 'repo': row.repo, 'graph_nodes': len(names),
                 'graph_edges': len(g['edges']), 'gold_symbols': len(row.symbols), 'gold_in_graph': len(gold),
                 'mentioned_nodes': len(mentioned), 'hop_distance': dist})
graph_df = pd.DataFrame(rows)
print(len(graph_df), 'tasks with a graph and at least one edited symbol')
graph_df.groupby('repo').agg(nodes=('graph_nodes', 'median'), edges=('graph_edges', 'median'),
                             gold_found=('gold_in_graph', lambda s: (s > 0).mean()),
                             mentioned=('mentioned_nodes', 'median')).round(2)
""")

code("""
hd = graph_df.hop_distance.dropna()
counts = hd.replace(math.inf, 7).value_counts().sort_index()
ax = counts.rename(index={7: '>6 / none'}).plot.bar(figsize=(7, 3), color='C2',
     title='Graph hops from an issue-mentioned symbol to the nearest edited symbol')
ax.set_xlabel('hops (0 = the issue names the edited symbol)'); plt.tight_layout(); plt.show()
print('Within 2 hops:', round((hd <= 2).mean(), 3), '| reachable within 6:', round(np.isfinite(hd).mean(), 3))
""")

md("""
## 4. Retrieval baselines: recall@k of the edited symbol

For each task we rank all graph nodes and report whether an edited symbol lands in the top k:
- **BM25**: BM25 between the issue text and each node's source text (the `text` field of the graph).
- **Embedding**: cosine similarity to the mean embedding of the nodes the issue mentions. The released vectors index
  code nodes, not free text, so they need at least one mentioned symbol to act as a query.
- **Graph**: nodes ordered by hop distance from the mentioned nodes, ties broken by BM25.
- **Hybrid**: rank fusion (RRF) of the three.
""")

code("""
TOK = re.compile(r'[A-Za-z][a-z0-9]+|[A-Z]+(?![a-z])|\\d+')

def tokens(text):
    out = []
    for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text or ''):
        out.append(w.lower())
        out += [p.lower() for p in TOK.findall(w.replace('_', ' ')) if len(p) > 2]
    return out

def bm25_scores(query, docs, k1=1.2, b=0.75):
    dtoks = [collections.Counter(tokens(d)) for d in docs]
    lens = np.array([sum(c.values()) for c in dtoks], dtype=float)
    avg = lens.mean() if len(lens) else 1.0
    df = collections.Counter(t for c in dtoks for t in c)
    N = len(docs)
    q = set(tokens(query))
    scores = np.zeros(N)
    for t in q:
        if t not in df:
            continue
        idf = math.log(1 + (N - df[t] + .5) / (df[t] + .5))
        tf = np.array([c.get(t, 0) for c in dtoks], dtype=float)
        scores += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lens / avg))
    return scores

def rank_of(order, gold):
    pos = [i for i, n in enumerate(order) if n in gold]
    return pos[0] + 1 if pos else math.inf

def rrf(*orders, k=60):
    s = collections.defaultdict(float)
    for order in orders:
        for i, n in enumerate(order):
            s[n] += 1 / (k + i + 1)
    return sorted(s, key=s.get, reverse=True)

res = []
for row in tasks.itertuples():
    gp, ep = graph_path(row, 'graphs'), graph_path(row, 'embeddings')
    if not gp.exists() or not row.symbols:
        continue
    g = json.load(open(gp, encoding='utf-8'))
    names = [n['id'] for n in g['nodes']]
    texts = [n['id'].replace('.', ' ') + ' ' + (n.get('text') or '') for n in g['nodes']]
    gold = gold_nodes(row, names)
    if not gold:
        continue
    query = (row.problem_statement or '') + ' ' + (row.hints_text or '')
    bm = bm25_scores(query, texts)
    bm_order = [names[i] for i in np.argsort(-bm)]
    ids = identifiers(query)
    mentioned = [n for n in names if n.rsplit('.', 1)[-1] in ids]
    emb_order, graph_order = bm_order, bm_order
    if mentioned:
        if ep.exists():
            z = np.load(ep, allow_pickle=True)
            keys = [n for n in names if n in z.files]
            if keys:
                M = np.stack([z[n] for n in keys]).astype(np.float32)
                M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
                qv = np.mean([z[n] for n in mentioned if n in z.files] or [M.mean(0)], axis=0)
                qv = qv / (np.linalg.norm(qv) + 1e-9)
                emb_order = [keys[i] for i in np.argsort(-(M @ qv))]
        G = nx.Graph(); G.add_nodes_from(names)
        G.add_edges_from((e['source'], e['target']) for e in g['edges'])
        hop = nx.multi_source_dijkstra_path_length(G, mentioned[:200], cutoff=4)
        bm_rank = {n: i for i, n in enumerate(bm_order)}
        graph_order = sorted(names, key=lambda n: (hop.get(n, 99), bm_rank[n]))
    res.append({'instance_id': row.instance_id, 'repo': row.repo, 'nodes': len(names), 'has_mention': bool(mentioned),
                'bm25': rank_of(bm_order, gold), 'embedding': rank_of(emb_order, gold),
                'graph': rank_of(graph_order, gold), 'hybrid': rank_of(rrf(bm_order, emb_order, graph_order), gold)})
ret = pd.DataFrame(res)

def recall_table(df):
    out = {}
    for m in ['bm25', 'embedding', 'graph', 'hybrid']:
        out[m] = {f'R@{k}': (df[m] <= k).mean() for k in (1, 5, 10, 20, 50)}
    return pd.DataFrame(out).T.round(3)

print(len(ret), 'tasks scored |', int(ret.has_mention.sum()), 'have at least one mentioned symbol')
recall_table(ret)
""")

code("""
recall_table(ret[ret.has_mention]).add_prefix('mentioned: ')
""")

code("""
ks = [1, 2, 3, 5, 10, 20, 50, 100]
plt.figure(figsize=(7, 3.6))
for m in ['bm25', 'embedding', 'graph', 'hybrid']:
    plt.plot(ks, [(ret[m] <= k).mean() for k in ks], marker='o', label=m)
plt.xscale('log'); plt.xlabel('k (nodes shown to the agent)'); plt.ylabel('recall of an edited symbol')
plt.title('Localization before the first tool call'); plt.legend(); plt.grid(alpha=.3); plt.tight_layout(); plt.show()
""")

md("""
**How to read this.** If the hybrid ranking puts an edited symbol in the top 10 for a large share of tasks, then
handing the agent that shortlist up front (for example through a skill script) can replace much of its search phase.
That phase is where our runs spent their budget and where context compaction hit them.
""")

md("## 5. Budget arithmetic for the 12-hour limit")

code("""
SEC_PER_CALL, OVERHEAD_MIN, TASKS, LIMIT_H, SAFE_H = 8.7, 0.5, 120, 12.0, 11.0
calls = np.arange(10, 81)
worst = TASKS * (OVERHEAD_MIN + calls * SEC_PER_CALL / 60) / 60
plt.figure(figsize=(7, 3.4))
plt.plot(calls, worst, label='every task uses the full call cap')
for frac in (0.6, 0.8):
    plt.plot(calls, TASKS * (OVERHEAD_MIN + frac * calls * SEC_PER_CALL / 60) / 60, '--',
             label=f'tasks use {int(frac * 100)}% of the cap on average')
plt.axhline(LIMIT_H, color='r', lw=1); plt.text(12, LIMIT_H + .2, '12 h limit', color='r')
plt.xlabel('max_tool_calls'); plt.ylabel('total hours (120 tasks)'); plt.legend(); plt.grid(alpha=.3)
plt.tight_layout(); plt.show()
print('Largest cap that keeps a 1 h margin even if every task uses it fully:',
      int(calls[worst <= SAFE_H].max()), 'calls (8.7 s/call, 0.5 min overhead per task)')
""")

md("""
The ~8.7 s per model call (with thinking) and ~0.5 min per-task overhead come from public calibration posts on 4×L4.
Measure your own: per-call latency depends on thinking length and output size.
""")

md("## 6. Which public tasks can be graded locally?")

code("""
# Reference (gold) patches that pass the subprocess grader used by the official starter notebook,
# measured with swegemma 0.2.11 on Kaggle CPU (2026-10-17).
GRADABLE = __GRADABLE__
tasks['gold_gradable_locally'] = tasks.instance_id.isin(GRADABLE)
tasks.groupby('repo').gold_gradable_locally.agg(['sum', 'count'])
""")

md("""
Tasks whose reference solution fails locally (mostly httpx/requests) fail for environment reasons, such as tests
importing the system copy of the package or missing fixtures. A local resolution rate that counts them is
biased downwards. Evaluate on the gradable subset.

## Takeaways
- The median task is small, but a heavy tail of large patches is hard to finish within ~28 tool calls.
- The issue text names the edited file or symbol in only part of the tasks. The remainder needs real search.
- The released code graph contains most edited symbols. The retrieval baselines above show how much a deterministic
  shortlist recovers before the agent spends any tool call.
- The 12-hour limit, not the per-task cap, is the binding constraint. Calls are cheap, and running over the limit fails the whole submission.
""")


def main():
    load_dotenv(ROOT / '.env')
    username = os.environ.get('KAGGLE_USERNAME') or 'YOUR_KAGGLE_USERNAME'
    ids_file = ROOT / 'dev' / 'validated_tasks.txt'
    gradable = ids_file.read_text().split() if ids_file.exists() else []
    cells = []
    for i, (kind, src) in enumerate(CELLS):
        src = src.replace('__GRADABLE__', repr(gradable))
        cell = {'cell_type': kind, 'id': f'eda-{i:02d}', 'metadata': {}, 'source': src.splitlines(keepends=True)}
        if kind == 'code':
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    nb = {'cells': cells, 'nbformat': 4, 'nbformat_minor': 5,
          'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                       'language_info': {'name': 'python'}}}
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f'{SLUG}.ipynb').write_text(json.dumps(nb, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    meta = {'id': f'{username}/{SLUG}', 'title': TITLE, 'code_file': f'{SLUG}.ipynb', 'language': 'python',
            'kernel_type': 'notebook', 'is_private': '--public' not in sys.argv, 'enable_gpu': False,
            'enable_tpu': False, 'enable_internet': False, 'keywords': [], 'dataset_sources': [],
            'kernel_sources': [], 'competition_sources': ['gemma-4-developer-agent'], 'model_sources': []}
    (OUT_DIR / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {OUT_DIR / (SLUG + ".ipynb")} (public={not meta["is_private"]})')


if __name__ == '__main__':
    main()
