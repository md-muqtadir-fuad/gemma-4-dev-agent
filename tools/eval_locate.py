"""Offline accuracy of the swe-tools localizer against the gold patches.

Usage: python tools/eval_locate.py <data_dir> <work_dir> [locate.py] [--query full|title]
For every task whose snapshot exists: extract it, run locate.py on the issue text, and record whether a
gold-patch file is among the reported top files and whether a gold-edited symbol is among the candidates.
Writes <work_dir>/locate_eval.csv and prints hit rates.
"""
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

data_dir, work_dir = Path(sys.argv[1]), Path(sys.argv[2])
locate = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].endswith('.py') else \
    Path(__file__).resolve().parent.parent / 'agents/scs/skills/swe-tools/scripts/locate.py'
mode = sys.argv[sys.argv.index('--query') + 1] if '--query' in sys.argv else 'full'
work_dir.mkdir(parents=True, exist_ok=True)


def gold_targets(patch):
    files, symbols = set(), set()
    for line in patch.splitlines():
        if line.startswith('+++ b/'):
            files.add(line[6:].strip())
        m = re.match(r'@@.*@@\s*(?:async\s+)?(?:def|class)\s+(\w+)', line) or \
            re.match(r'[+-]\s*(?:async\s+)?(?:def|class)\s+(\w+)', line)
        if m:
            symbols.add(m.group(1))
    return files, symbols


rows = []
for line in open(data_dir / 'tasks.jsonl', encoding='utf-8'):
    t = json.loads(line)
    snap = data_dir / 'snapshots' / f"{t['instance_id']}.tgz"
    if not snap.exists():
        continue
    repo = work_dir / 'repos' / t['instance_id']
    if not (repo / '.git').exists():
        repo.mkdir(parents=True, exist_ok=True)
        with tarfile.open(snap) as tf:
            tf.extractall(repo, filter='data') if sys.version_info >= (3, 12) else tf.extractall(repo)
        inner = [p for p in repo.iterdir() if p.is_dir()]
        if not (repo / '.git').exists() and len(inner) == 1 and (inner[0] / '.git').exists():
            repo = inner[0]
    if not (repo / '.git').exists():
        found = next((p.parent for p in repo.rglob('.git') if p.is_dir()), None)
        if found is None:
            continue
        repo = found
    text = t['problem_statement'] if mode == 'full' else t['problem_statement'].splitlines()[0]
    qfile = work_dir / 'query.txt'
    qfile.write_text(text + '\n' + (t.get('hints_text') or ''), encoding='utf-8')
    out = subprocess.run([sys.executable, str(locate), '--file', str(qfile)], capture_output=True, text=True,
                         env={'SWE_REPO': str(repo), 'PATH': ''}, timeout=300).stdout
    cands = re.findall(r'^\s{2}(\S+?):(\d+)\s+(\S+)$', out, flags=re.M)
    top_files = (re.search(r'^Top files: (.*)$', out, flags=re.M) or [None, ''])[1].split(', ')
    files, symbols = gold_targets(t['patch'])
    cand_files = [c[0] for c in cands]
    cand_syms = [c[2].rsplit('.', 1)[-1] for c in cands]
    sym_rank = next((i + 1 for i, s in enumerate(cand_syms) if s in symbols), None)
    rows.append({
        'instance_id': t['instance_id'], 'repo': t['repo'],
        'file_hit@1': bool(top_files[:1] and top_files[0] in files),
        'file_hit@6': bool(set(top_files) & files),
        'cand_file_hit@10': bool(set(cand_files) & files),
        'symbol_rank': sym_rank, 'symbol_hit@10': sym_rank is not None,
        'gold_symbols': len(symbols), 'gold_files': len(files)})
    print(f"{t['instance_id']:<18} file@1={rows[-1]['file_hit@1']!s:<5} file@6={rows[-1]['file_hit@6']!s:<5} "
          f"sym_rank={sym_rank}", flush=True)

import csv
if rows:
    with open(work_dir / 'locate_eval.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    for k in ('file_hit@1', 'file_hit@6', 'cand_file_hit@10', 'symbol_hit@10'):
        print(f'{k}: {sum(r[k] for r in rows)}/{n} = {sum(r[k] for r in rows) / n:.2f}')
