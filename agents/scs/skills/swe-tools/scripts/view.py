"""Print one function/class (or a line range) of a file with line numbers.

Usage:  python3 .git/swe/view.py <path> <Name|Class.method|START-END> [max_lines]
At most 80 lines are printed; the header says which lines were shown and how many exist.
"""
import ast
import os
import sys

MAX_LINES = 80


def repo_root():
    for cand in (os.environ.get('SWE_REPO'), os.environ.get('PWD'), '/workspace', os.getcwd()):
        if cand and os.path.isdir(os.path.join(cand, '.git')):
            return cand
    return os.getcwd()


def find_symbol(tree, target):
    parts = target.split('.')
    best = None

    def visit(node, prefix):
        nonlocal best
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = prefix + [child.name]
                if qual[-len(parts):] == parts and best is None:
                    best = child
                visit(child, qual)
    visit(tree, [])
    return best


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    path = sys.argv[1].lstrip('/')
    if path.startswith('workspace/'):
        path = path[len('workspace/'):]
    full = os.path.join(repo_root(), path)
    if not os.path.isfile(full):
        print(f'No such file: {path}. Find it with: git ls-files | grep <name>')
        return
    lines = open(full, encoding='utf-8', errors='replace').read().splitlines()
    limit = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else MAX_LINES
    target = sys.argv[2] if len(sys.argv) > 2 else '1-80'
    start, end = 1, min(len(lines), limit)
    if '-' in target and target.replace('-', '').isdigit():
        a, b = target.split('-', 1)
        start, end = max(1, int(a)), min(len(lines), int(b))
    elif target.isdigit():
        start = max(1, int(target) - 10)
        end = min(len(lines), start + 40)
    else:
        try:
            node = find_symbol(ast.parse('\n'.join(lines)), target)
        except SyntaxError:
            node = None
        if node is None:
            hits = [i + 1 for i, l in enumerate(lines) if target.split('.')[-1] in l][:8]
            print(f'{target} not found as a definition in {path}. Lines mentioning it: {hits}')
            return
        start = node.lineno - len(getattr(node, 'decorator_list', []) or [])
        end = getattr(node, 'end_lineno', node.lineno)
    shown_end = min(end, start + limit - 1)
    print(f'{path} lines {start}-{shown_end} of {len(lines)}' +
          (f' (truncated; definition ends at {end}, view {shown_end + 1}-{end} next)' if shown_end < end else ''))
    for i in range(start, shown_end + 1):
        print(f'{i:5d}  {lines[i - 1]}')


if __name__ == '__main__':
    main()
