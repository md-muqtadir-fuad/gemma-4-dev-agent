"""Rank the functions/classes of the repository most likely to need a change for an issue.

Usage:  python3 .git/swe/locate.py "<issue keywords, identifiers, error message>"
        python3 .git/swe/locate.py --file issue.txt          (offline evaluation)
Prints the top candidates as `path:line  qualified.name` with their signature, plus the top files.
Scoring: BM25 over (path, name, body) of every AST chunk, fused (RRF) with exact identifier and
quoted-string matches. Standard library only.
"""
import ast
import collections
import math
import os
import re
import sys

SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'build', 'dist', '.tox',
             'site-packages', '.mypy_cache', '.pytest_cache', '.eggs'}
TEST_RE = re.compile(r'(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$')
MAX_FILE_BYTES = 300_000
WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
PART = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+')
STOP = set('the and for that this with from into when then than have has not are was were will would '
           'should could can may use used using get set def class self none true false return import '
           'issue fix bug error test tests example add new support value values'.split())


def repo_root():
    for cand in (os.environ.get('SWE_REPO'), os.environ.get('PWD'), '/workspace', os.getcwd()):
        if cand and os.path.isdir(os.path.join(cand, '.git')):
            return cand
    return os.getcwd()


def tokens(text):
    out = []
    for w in WORD.findall(text):
        lw = w.lower()
        if len(lw) > 2 and lw not in STOP:
            out.append(lw)
        parts = [p.lower() for p in PART.findall(w.replace('_', ' ')) if len(p) > 2]
        if len(parts) > 1:
            out.extend(p for p in parts if p not in STOP)
    return out


def chunks_of(path, rel):
    try:
        src = open(path, encoding='utf-8', errors='replace').read()
        tree = ast.parse(src)
    except (SyntaxError, ValueError, OSError):
        return []
    lines = src.splitlines()
    module = rel[:-3].replace('/', '.')
    out = [{'rel': rel, 'line': 1, 'name': module, 'kind': 'module',
            'sig': (lines[0] if lines else ''), 'text': ' '.join(lines[:40])}]

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f'{prefix}{child.name}'
                start, end = child.lineno, getattr(child, 'end_lineno', child.lineno)
                if isinstance(child, ast.ClassDef):
                    body_end = min(end, start + 25)  # class header + docstring; methods are own chunks
                else:
                    body_end = end
                text = '\n'.join(lines[start - 1:body_end])
                out.append({'rel': rel, 'line': start, 'name': qual, 'kind': type(child).__name__,
                            'sig': lines[start - 1].strip() if start - 1 < len(lines) else qual,
                            'text': text})
                if isinstance(child, ast.ClassDef):
                    visit(child, qual + '.')
    visit(tree, '')
    return out


def collect(root):
    chunks = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, '/')
            if TEST_RE.search(rel):
                continue
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            chunks.extend(chunks_of(path, rel))
    return chunks


def bm25_rank(query_toks, docs, k1=1.2, b=0.75):
    tfs = [collections.Counter(d) for d in docs]
    lens = [len(d) for d in docs]
    avg = (sum(lens) / len(lens)) if lens else 1.0
    df = collections.Counter(t for tf in tfs for t in tf)
    n = len(docs)
    q = collections.Counter(query_toks)
    scores = []
    for tf, ln in zip(tfs, lens):
        s = 0.0
        for t, qn in q.items():
            f = tf.get(t)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + .5) / (df[t] + .5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * ln / avg)) * (1 + 0.2 * (qn - 1))
        scores.append(s)
    return scores


def main():
    args = sys.argv[1:]
    if args[:1] == ['--file']:
        query = open(args[1], encoding='utf-8', errors='replace').read()
        args = args[2:]
    else:
        query = ' '.join(a for a in args if a != '--')
    top_n = 10
    root = repo_root()
    chunks = collect(root)
    if not chunks or not query.strip():
        print('No Python sources found or empty query. Usage: locate.py "<keywords>"')
        return
    q_toks = tokens(query)
    idents = {w for w in WORD.findall(query) if len(w) > 3}
    quoted = [s.strip() for s in re.findall(r'[\'"`]([^\'"`\n]{6,80})[\'"`]', query)]
    docs = [tokens(c['rel'].replace('/', ' ')) + tokens(c['name']) * 3 + tokens(c['text']) for c in chunks]
    bm = bm25_rank(q_toks, docs)
    exact = []
    for c in chunks:
        last = c['name'].rsplit('.', 1)[-1]
        s = 0.0
        if last in idents:
            s += 3.0
        if any(part in idents for part in c['name'].split('.')[:-1]):
            s += 0.3
        stem = c['rel'].rsplit('/', 1)[-1][:-3]
        if stem in idents or c['rel'] in query:
            s += 1.0
        s += sum(1.5 for qs in quoted if qs in c['text'])
        exact.append(s)
    rrf = collections.defaultdict(float)
    for scores in (bm, exact):
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])
        for rank, i in enumerate(order[:300]):
            if scores[i] > 0:
                rrf[i] += 1.0 / (30 + rank)
    for i, s in enumerate(exact):  # strong exact evidence should lead
        rrf[i] += 0.02 * s
    ranked = sorted(rrf, key=rrf.get, reverse=True)
    funcs, per_file = [], collections.Counter()
    for i in ranked:  # at most 3 candidates per file keeps the shortlist diverse
        c = chunks[i]
        if c['kind'] != 'module' and per_file[c['rel']] < 3:
            funcs.append(i)
            per_file[c['rel']] += 1
        if len(funcs) >= top_n:
            break
    print(f'Top {len(funcs)} candidate locations (most likely first):')
    for i in funcs:
        c = chunks[i]
        print(f"  {c['rel']}:{c['line']}  {c['name']}\n      {c['sig'][:110]}")
    files = collections.OrderedDict()
    for i in ranked:
        files.setdefault(chunks[i]['rel'], 0)
        if len(files) >= 6:
            break
    print('Top files: ' + ', '.join(files))
    print('Next: python3 .git/swe/view.py <path> <name or start-end> to read one candidate.')


if __name__ == '__main__':
    main()
