"""Print a Kaggle kernel log (JSON list of {time, stream_name, data}) as plain lines.

Usage: python tools/show_kaggle_log.py <log> [regex]   (regex filters lines)
"""
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
log = json.load(open(sys.argv[1], encoding='utf-8'))
pattern = re.compile(sys.argv[2]) if len(sys.argv) > 2 else None
for e in log:
    for line in e.get('data', '').rstrip().splitlines():
        if line.strip() and (pattern is None or pattern.search(line)):
            print(f"[{e.get('time', 0):8.1f}] {line[:300]}")
