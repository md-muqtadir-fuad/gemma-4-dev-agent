"""Validate the submission/ folder with the official harness libraries (no GPU needed).

Runs the same structure checks and YAML compilation the scorer performs,
using placeholder tools and model endpoints.

Usage:  .venv\\Scripts\\python.exe validate_submission.py [submission_dir]
"""
import re
import sys
from pathlib import Path

from adk_submission import ModelRegistry, compile_submission, validate_directory
from adk_submission.discovery import discover_declared_models
from swegemma.config import (
    ALLOWED_SUBMISSION_EXTENSIONS,
    MAX_SUBMISSION_SIZE_BYTES,
    build_submission_limits,
)

ALLOWED_MODEL_NAMES = {
    'gemma-4-31b-it-qat-w4a16-ct',
    'gemma-4-12b-it-qat-w4a16-ct',
    'gemma-4-e4b-it-qat-w4a16-ct',
    'gemma-4-e2b-it-qat-w4a16-ct',
}
HARNESS_TOOLS = [
    'run_command', 'read_file', 'edit_file', 'write_file', 'get_status',
    'submit_patch', 'get_code_neighbors', 'search_similar_code', 'get_code_subgraph',
]
# ADK fills {name} placeholders in instructions from session state; only these exist.
STATE_KEYS = {'problem_description', 'hints'}


def placeholder_tool(name):
    def tool() -> str:
        return ''
    tool.__name__ = name
    tool.__doc__ = f'Placeholder for {name}.'
    return tool


def main(submission_dir: Path) -> None:
    limits, gen_constraints = build_submission_limits()

    files = [p for p in submission_dir.rglob('*') if p.is_file()]
    for p in files:
        assert not p.is_symlink(), f'Symlinks are not permitted: {p}'
        assert p.suffix.lower() in ALLOWED_SUBMISSION_EXTENSIONS, f'Disallowed extension: {p}'
    total = sum(p.stat().st_size for p in files)
    assert total <= MAX_SUBMISSION_SIZE_BYTES, f'Submission too large: {total} bytes'

    validate_directory(submission_dir, limits=limits)

    models = discover_declared_models(submission_dir)
    assert len(models) == 1, f'Expected exactly 1 declared model, got {sorted(models)}'
    model = next(iter(models))
    assert model in ALLOWED_MODEL_NAMES, f'Model {model!r} is not allowed'

    for md in submission_dir.rglob('*.md'):
        unknown = set(re.findall(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', md.read_text(encoding='utf-8'))) - STATE_KEYS
        assert not unknown, f'{md}: unknown {{placeholders}} would break ADK templating: {sorted(unknown)}'

    registry = ModelRegistry()
    registry.register(model, f'openai/{model}')
    agent = compile_submission(
        submission_dir=submission_dir,
        tool_registry={name: placeholder_tool(name) for name in HARNESS_TOOLS},
        model_registry=registry,
        limits=limits,
        generation_constraints=gen_constraints,
    )
    print(f'OK: {submission_dir} compiles -> {type(agent).__name__} {agent.name!r}, '
          f'model={model}, {len(files)} files, {total / 1024:.1f} KiB')


if __name__ == '__main__':
    main(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / 'submission'))
