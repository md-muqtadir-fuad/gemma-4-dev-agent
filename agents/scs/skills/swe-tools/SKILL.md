---
name: swe-tools
description: Fast repository navigation for fixing an issue. start.py installs helpers into .git/swe and prints the functions most likely to need a change.
---
# swe-tools

Run once, as your first action:
run_skill_script(skill_name="swe-tools", file_path="scripts/start.py", args=["<identifiers, quoted error text and key words from the issue>"])

It prints the ten most likely functions or classes (path:line and name) and the most likely files, and installs three helpers that you then call with run_command:
- `python3 .git/swe/locate.py "<different keywords>"` searches again with other words.
- `python3 .git/swe/view.py <path> <Name|Class.method|START-END>` prints one definition or line range (at most 80 lines) with line numbers.
- `python3 .git/swe/check.py` lists changed files, compiles them, flags discarded test/config edits and stray files, and names related test files.

The helpers live inside .git, so they are never part of your patch.
