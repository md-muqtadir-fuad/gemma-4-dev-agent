"""Pre-submit check: what changed, does it compile, anything that will be discarded, which tests to run.

Usage:  python3 .git/swe/check.py
"""
import os
import py_compile
import re
import subprocess

PROTECTED = re.compile(r'(^|/)(tests?|testing)/.*\.py$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|'
                       r'(^|/)(pytest\.ini|pyproject\.toml|setup\.cfg|tox\.ini|\.pytest\.ini)$')


def repo_root():
    for cand in (os.environ.get('SWE_REPO'), os.environ.get('PWD'), '/workspace', os.getcwd()):
        if cand and os.path.isdir(os.path.join(cand, '.git')):
            return cand
    return os.getcwd()


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True).stdout


def main():
    root = repo_root()
    status = [l for l in git(root, 'status', '--porcelain').splitlines() if l.strip()]
    if not status:
        print('NO CHANGES. Nothing will be graded: edit a source file now.')
        return
    changed, problems = [], []
    for line in status:
        code, path = line[:2], line[3:].strip().strip('"')
        if path.endswith('/'):
            problems.append(f'untracked directory {path} will be part of the patch; remove it if it is scratch')
            continue
        changed.append(path)
        if PROTECTED.search(path):
            problems.append(f'{path}: test/config file, discarded before grading (revert: git checkout -- {path})')
        elif code == '??' and not path.endswith('.py'):
            problems.append(f'{path}: untracked non-Python file, will be part of the patch; delete if scratch')
    for path in changed:
        if path.endswith('.py') and os.path.exists(os.path.join(root, path)):
            try:
                py_compile.compile(os.path.join(root, path), doraise=True)
            except py_compile.PyCompileError as e:
                problems.append(f'{path}: SYNTAX ERROR {str(e.msg).strip()[:300]}')
    print('Changed: ' + ', '.join(changed))
    print(git(root, 'diff', '--stat').strip()[-800:])
    src = [p for p in changed if p.endswith('.py') and not PROTECTED.search(p)]
    if not src:
        problems.append('no source (.py outside tests) file changed: the graded patch would be empty')
    tests = []
    for p in src:
        stem = os.path.basename(p)[:-3].lstrip('_')
        for t in git(root, 'ls-files').splitlines():
            base = os.path.basename(t)
            if base.startswith('test_') and stem and stem in base and t.endswith('.py'):
                tests.append(t)
    if tests:
        print('Related tests: ' + ' '.join(sorted(set(tests))[:4]))
        print('Run one: timeout 120 python3 -m pytest <file> -x -q 2>&1 | tail -15')
    print('PROBLEMS:\n- ' + '\n- '.join(problems) if problems else 'OK: source changed and compiles.')


if __name__ == '__main__':
    main()
