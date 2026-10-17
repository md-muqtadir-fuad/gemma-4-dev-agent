"""Execute the Kaggle notebook's CPU-safe cells locally with /kaggle paths remapped.

Usage: python tools/run_notebook_local.py <notebook> <data_dir> <work_dir>
The wheelhouse install is skipped; vLLM and agent cells only run if DEV is True (they will fail
locally, so use a data dir whose tasks.jsonl simulates the scoring re-run, or RUN_DEV_EVAL = False).
"""
import json
import sys
from pathlib import Path

nb_path, data_dir, work_dir = map(Path, sys.argv[1:4])
work_dir.mkdir(parents=True, exist_ok=True)


def remap(src):
    return (src.replace('/kaggle/input/competitions/gemma-4-developer-agent', data_dir.as_posix())
               .replace('/kaggle/working', work_dir.as_posix()))


ns = {'display': print}
cells = [c for c in json.load(open(nb_path, encoding='utf-8'))['cells'] if c['cell_type'] == 'code']
for i, cell in enumerate(cells):
    src = remap(''.join(cell['source']))
    if src.startswith('%%writefile '):
        header, body = src.split('\n', 1)
        target = Path(header.split(' ', 1)[1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding='utf-8')
        continue
    src = src.replace('if not IS_RERUN:\n    install_wheelhouse()', 'pass  # install skipped locally')
    exec(compile(src, f'cell{i}', 'exec'), ns)
print(f"OK: {len(cells)} code cells | IS_RERUN={ns.get('IS_RERUN')} DEV={ns.get('DEV')} | "
      f"zip={(work_dir / 'submission.zip').exists()}")
