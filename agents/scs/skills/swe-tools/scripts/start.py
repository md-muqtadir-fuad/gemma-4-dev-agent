"""Install the helper scripts into <repo>/.git/swe/ (never part of the patch) and run the localizer.

Run once, as the first action:  run_skill_script(skill_name="swe-tools", file_path="scripts/start.py",
                                                 args=["<keywords from the issue>"])
Afterwards use run_command:  python3 .git/swe/locate.py "...", .git/swe/view.py, .git/swe/check.py
"""
import os
import runpy
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def repo_root():
    for cand in (os.environ.get('SWE_REPO'), os.environ.get('PWD'), '/workspace'):
        if cand and os.path.isdir(os.path.join(cand, '.git')):
            return cand
    return None


root = repo_root()
if root is None:
    print('Repository not found (expected /workspace).')
    sys.exit(0)
dest = os.path.join(root, '.git', 'swe')
os.makedirs(dest, exist_ok=True)
for name in ('locate.py', 'view.py', 'check.py'):
    shutil.copyfile(os.path.join(HERE, name), os.path.join(dest, name))
print('Installed: python3 .git/swe/locate.py "<keywords>" | .git/swe/view.py <path> <Name|A-B> | .git/swe/check.py')
os.environ['SWE_REPO'] = root
sys.argv = [os.path.join(dest, 'locate.py')] + [a for a in sys.argv[1:] if a != '--']
runpy.run_path(os.path.join(dest, 'locate.py'), run_name='__main__')
