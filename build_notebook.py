"""Generate the Kaggle notebook (kaggle/gemma4-agent.ipynb) from the local submission/ folder.

Each submission file becomes an editable %%writefile cell, so submission/ stays the
single source of truth. Run validate_submission.py first, then this script.

Usage:  .venv\\Scripts\\python.exe build_notebook.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
SUBMISSION_DIR = ROOT / 'submission'
OUT_DIR = ROOT / 'kaggle'
NOTEBOOK_SLUG = 'gemma-4-developer-agent-submission'
NOTEBOOK_TITLE = 'Gemma 4 Developer Agent Submission'
KAGGLE_SUBMISSION_DIR = '/kaggle/working/submission'

# Order the files so the important ones appear first in the notebook
FILE_ORDER = ['agent.yaml', 'eval_config.yaml', 'configs/sampling.yaml', 'prompts/system.md']

INTRO = f"""# {NOTEBOOK_TITLE}

Single-agent Gemma 4 SWE agent for the *Gemma 4 Developer Agent* competition.

**What this notebook does**
1. Writes the agent (`agent.yaml`, prompt, sampling and budget configs) to `{KAGGLE_SUBMISSION_DIR}` and packages `/kaggle/working/submission.zip`.
2. *Interactive runs only:* installs the official harness, validates and compiles the submission, starts vLLM and runs the agent on a few public tasks to estimate the resolution rate.

When Kaggle re-runs this notebook for scoring, step 2 is skipped automatically, so only the submission files are produced.

**Setup:** accelerator **GPU L4 x4**, internet **off**. Inputs: the competition data, the `metric/gemma-4-developer-agent-wheelhouse` dataset and the `google/gemma-4` model matching `model:` in `agent.yaml`.

**Submit:** after a run, use *Submit to Competition* on the notebook (1 submission per day)."""

SETTINGS = """import json
import os
from pathlib import Path

# Run the agent on a few public tasks to estimate the resolution rate (interactive runs only)
RUN_DEV_EVAL = True
# Before the agent runs, grade each dev task's reference solution to confirm local grading works (CPU only)
RUN_HARNESS_CHECK = False  # dev tasks are already gold-validated (dev/validated_tasks.txt)
# Only grade the reference solutions of ALL public tasks (CPU only, no model, no agent)
GOLD_CHECK_ONLY = False
# Record the working-tree diff after every tool call (for the anytime curve; dev runs only)
RECORD_ANYTIME = True
# Tasks evaluated in parallel during dev runs (the scorer runs them one at a time)
DEV_CONCURRENCY = __DEV_CONCURRENCY__
# Tasks per repo for the dev run; set DEV_TASK_IDS to a list of instance_ids to pick them yourself
DEV_TASKS_PER_REPO = {'fastapi/fastapi': 2, 'Textualize/rich': 2, 'psf/requests': 1, 'encode/httpx': 1}
DEV_TASK_IDS = __DEV_TASK_IDS__

DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WHEELHOUSE_DIR = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
WORKING_DIR = Path('/kaggle/working')
AGENT_DIR = WORKING_DIR / 'submission'


def is_scoring_rerun() -> bool:
    \"\"\"True when Kaggle re-runs the notebook for scoring (hidden tasks carry no test_patch).\"\"\"
    if os.environ.get('KAGGLE_IS_COMPETITION_RERUN'):
        return True
    try:
        with open(DATA_DIR / 'tasks.jsonl', encoding='utf-8') as f:
            return 'test_patch' not in json.loads(f.readline())
    except (OSError, ValueError):
        return False


IS_RERUN = is_scoring_rerun()
DEV = RUN_DEV_EVAL and not IS_RERUN
print(f'Scoring re-run: {IS_RERUN} | dev evaluation: {DEV}')

for sub in __SUBDIRS__:
    (AGENT_DIR / sub).mkdir(parents=True, exist_ok=True)"""

PACKAGE = """import zipfile

ALLOWED_EXTENSIONS = {'.yaml', '.yml', '.md', '.txt', '.py', '.json', '.safetensors'}

# Files only (no directory entries), agent.yaml at the archive root
files = sorted(p for p in AGENT_DIR.rglob('*') if p.is_file())
for p in files:
    assert not p.is_symlink(), f'Symlinks are not permitted: {p}'
    assert p.suffix.lower() in ALLOWED_EXTENSIONS, f'Disallowed file extension: {p}'
zip_path = WORKING_DIR / 'submission.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in files:
        zf.write(p, p.relative_to(AGENT_DIR).as_posix())
print(f'Wrote {zip_path} ({zip_path.stat().st_size / 1024:.1f} KiB):')
for p in files:
    print('  ', p.relative_to(AGENT_DIR).as_posix())"""

GPU_CHECK = """import subprocess


def list_gpus():
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()] if out.returncode == 0 else []


if DEV and not GOLD_CHECK_ONLY:
    gpus = list_gpus()
    print(f'{len(gpus)} GPU(s): ' + '; '.join(gpus) if gpus else 'No GPU found.')
    assert gpus, (
        'No GPU attached. In the notebook editor open Settings > Accelerator, choose "GPU L4 x4", '
        'then Save Version > Save & Run All (runs started with `kaggle kernels push` cannot get L4 GPUs). '
        'To only build submission.zip, set RUN_DEV_EVAL = False.'
    )"""

INSTALL = """import glob
import importlib
import logging
import shutil
import subprocess
import sys

# Offline vLLM serving and LiteLLM routing (from the official starter notebook)
os.environ.update({
    'TRANSFORMERS_NO_TF': '1',
    'TRANSFORMERS_NO_FLAX': '1',
    'TRANSFORMERS_OFFLINE': '1',
    'VLLM_NO_USAGE_STATS': '1',
    'VLLM_WORKER_MULTIPROC_METHOD': 'spawn',
    'VLLM_ENGINE_READY_TIMEOUT_S': '1200',
    'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1',
    'NCCL_DEBUG': 'WARN',
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
    'LITELLM_TELEMETRY': 'False',
    'LITELLM_LOG': 'WARNING',
    'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
    'OTEL_SDK_DISABLED': 'true',
    'OTEL_PYTHON_DISABLED': 'true',
})
os.environ.setdefault('OPENAI_API_KEY', 'EMPTY')
os.environ.setdefault('LOCAL_API_KEY', 'EMPTY')


def configure_logging() -> None:
    \"\"\"Silence verbose third-party loggers.\"\"\"
    for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx', 'httpcore',
                 'openai', 'urllib3', 'opentelemetry', 'opentelemetry.context'):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        if 'litellm' in name.lower():
            lg.propagate = False
            lg.handlers.clear()


def install_wheelhouse() -> None:
    # Remove broken cutlass .pth hooks if present
    for pattern in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth',
                    '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
        for pth in glob.glob(pattern):
            try:
                os.unlink(pth)
            except OSError:
                pass
    # Restore PEP 440 '+cu128' wheel filenames stripped by Kaggle dataset uploads
    tmp_whl = Path('/tmp/wheelhouse')
    tmp_whl.mkdir(parents=True, exist_ok=True)
    for w in WHEELHOUSE_DIR.glob('*.whl'):
        if 'cutlass' in w.name.lower():
            continue
        name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
        target = tmp_whl / name
        if not target.exists():
            try:
                os.symlink(w, target)
            except OSError:
                shutil.copyfile(w, target)
    wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
    print(f'Installing {len(wheels)} wheels from {WHEELHOUSE_DIR}...')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels],
                   check=True)
    importlib.invalidate_caches()
    configure_logging()
    print('Wheelhouse installation complete.')


configure_logging()
if not IS_RERUN:
    install_wheelhouse()"""

VALIDATE = """ALLOWED_MODEL_NAMES = {
    'gemma-4-31b-it-qat-w4a16-ct',
    'gemma-4-12b-it-qat-w4a16-ct',
    'gemma-4-e4b-it-qat-w4a16-ct',
    'gemma-4-e2b-it-qat-w4a16-ct',
}


def validate_submission():
    \"\"\"Run the scorer's structure checks and compile the YAML with placeholder tools.\"\"\"
    from adk_submission import ModelRegistry, compile_submission, validate_directory
    from adk_submission.discovery import discover_declared_models
    from swegemma.config import build_submission_limits

    limits, gen_constraints = build_submission_limits()
    validate_directory(AGENT_DIR, limits=limits)
    models = discover_declared_models(AGENT_DIR)
    assert len(models) == 1, f'Expected exactly 1 declared model, got {sorted(models)}'
    model = next(iter(models))
    assert model in ALLOWED_MODEL_NAMES, f'Model {model!r} is not allowed'

    tool_names = ['run_command', 'read_file', 'edit_file', 'write_file', 'get_status', 'submit_patch',
                  'get_code_neighbors', 'search_similar_code', 'get_code_subgraph']

    def placeholder(name):
        def tool() -> str:
            return ''
        tool.__name__ = name
        tool.__doc__ = f'Placeholder for {name}.'
        return tool

    registry = ModelRegistry()
    registry.register(model, f'openai/{model}')
    agent = compile_submission(
        submission_dir=AGENT_DIR,
        tool_registry={n: placeholder(n) for n in tool_names},
        model_registry=registry,
        limits=limits,
        generation_constraints=gen_constraints,
    )
    print(f'Submission OK: {type(agent).__name__} {agent.name!r}, model={model}')
    return model


if not IS_RERUN:
    DECLARED_MODEL = validate_submission()"""

PICK_TASKS = """import random
from collections import defaultdict


def pick_dev_tasks():
    from swegemma.models import load_tasks

    tasks = load_tasks(DATA_DIR / 'tasks.jsonl')
    if GOLD_CHECK_ONLY:
        return tasks
    if DEV_TASK_IDS:
        wanted = set(DEV_TASK_IDS)
        return [t for t in tasks if t.instance_id in wanted]
    by_repo = defaultdict(list)
    for t in tasks:
        by_repo[t.repo].append(t)
    rng = random.Random(0)
    picked = []
    for repo, n in DEV_TASKS_PER_REPO.items():
        picked += rng.sample(by_repo[repo], min(n, len(by_repo[repo])))
    return picked


if DEV:
    dev_tasks = pick_dev_tasks()
    print(f'{len(dev_tasks)} dev tasks:')
    for t in dev_tasks:
        print(f'  - {t.instance_id:<16} {t.repo}')"""

START_VLLM = """import re


def start_vllm(model_name):
    import litellm
    import torch
    from adk_submission import VllmConfig, VllmServer, discover_adapters
    from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS

    litellm.drop_params = True
    model_path = Path(f'/kaggle/input/models/google/gemma-4/other/{model_name}/2')
    assert model_path.exists(), f'Model weights not found at {model_path}. Attach the model as an input.'

    adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
    adapter_map = getattr(adapters, 'adapters', None) or {}
    for name in adapter_map:
        assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name), f'Unsafe adapter name {name!r}'
    ranks = [r for info in adapter_map.values() if (r := getattr(info, 'rank', None))]

    gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1
    tp_size = 4 if gpu_count >= 4 else (2 if gpu_count >= 2 else 1)
    extra_args = {
        'gemma-4-12b-it-qat-w4a16-ct': (
            '--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}',
        ),
    }.get(model_name, ())

    cfg = VllmConfig(
        model=str(model_path),
        port=8000,
        host='127.0.0.1',
        tool_call_parser='gemma4',
        reasoning_parser='gemma4',
        max_model_len=32768,
        dtype='bfloat16' if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else 'auto',
        gpu_memory_utilization=0.90,
        enable_auto_tool_choice=True,
        enable_lora=bool(adapter_map),
        max_loras=max(1, len(adapter_map)),
        max_lora_rank=max(ranks) if ranks else 128,
        scheduler_reserve_full_isl=False,
        tensor_parallel_size=tp_size,
        startup_timeout=60 * 20,
        extra_args=extra_args,
    )
    server = VllmServer(cfg, adapter_manifest=adapters)
    server.start()
    print(f'vLLM server started on {server.base_url} ({gpu_count} GPUs, tp={tp_size})')
    models = server.create_model_registry(
        aliases=[model_name], model_prefix='openai/', api_key=os.environ['LOCAL_API_KEY'],
    )
    return server, models, adapters


if DEV and not GOLD_CHECK_ONLY:
    if globals().get('server_instance') is not None:
        server_instance.stop()
    server_instance, model_registry, adapter_manifest = start_vllm(DECLARED_MODEL)"""

EVAL_SETUP = """import asyncio
import concurrent.futures
import time

import pandas as pd
import yaml

RESULTS_DIR = WORKING_DIR / 'results'


def run_sync(fn, *args, **kwargs):
    \"\"\"Run an async function to completion, even inside the notebook's event loop.\"\"\"
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(fn(*args, **kwargs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(fn(*args, **kwargs))).result()


def make_evaluator(models, adapter_manifest=None):
    \"\"\"Evaluator configured like the scorer, with budgets read from eval_config.yaml.\"\"\"
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps._configs import EventsCompactionConfig
    from swegemma.config import EvalConfig, build_submission_limits
    from swegemma.evaluate import Evaluator

    raw = yaml.safe_load((AGENT_DIR / 'eval_config.yaml').read_text(encoding='utf-8')) or {}
    ev = raw.get('evaluation', raw)
    turns = ev.get('max_turns', ev.get('max_llm_calls'))
    limits, gen_constraints = build_submission_limits()
    return Evaluator(EvalConfig(
        tasks_path=DATA_DIR / 'tasks.jsonl',
        snapshots_dir=DATA_DIR / 'snapshots',
        results_dir=RESULTS_DIR,
        submission_dir=AGENT_DIR,
        models=models,
        sandbox='subprocess',
        timeout_seconds=int(ev.get('timeout_seconds', 300)),
        verification_timeout_seconds=int(ev.get('verification_timeout_seconds', 300)),
        max_time_minutes=float(ev.get('max_time_minutes', 60.0)),
        max_tool_calls=int(ev.get('max_tool_calls', 100)),
        max_turns=int(turns) if turns is not None else None,
        limits=limits,
        generation_constraints=gen_constraints,
        adapter_manifest=adapter_manifest,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5,
        ),
        graph_dir=DATA_DIR / 'graphs',
        embeddings_dir=DATA_DIR / 'embeddings',
        wheels_dir=DATA_DIR / 'wheels',
        verbose=False,
    ))


SNAPSHOT_TOOLS = ('run_command', 'edit_file', 'write_file')
# Diff of the working tree vs HEAD, built in a throwaway index so the agent's git state is untouched
SNAPSHOT_CMD = ('cd /workspace && export GIT_INDEX_FILE=/tmp/_anytime_idx && git read-tree HEAD '
                '&& git add -A && git diff --cached --binary HEAD')


def install_anytime_recorder():
    \"\"\"Dev-only instrumentation: after every state-changing tool call, store the working-tree diff in
    results/anytime/<task>.jsonl. Replaying these snapshots through the grader gives the anytime curve
    P(resolved | agent stopped after call c).\"\"\"
    import functools
    import inspect
    from swegemma.context import SwegemmaContext

    if getattr(SwegemmaContext.create_tools, '_anytime', False):
        return
    original = SwegemmaContext.create_tools
    out_dir = RESULTS_DIR / 'anytime'
    out_dir.mkdir(parents=True, exist_ok=True)

    def record(ctx, tool_name):
        try:
            res = ctx.docker.exec(ctx.container_id, SNAPSHOT_CMD, timeout=60)  # same path as the tools
            diff = getattr(res, 'stdout', '') or ''
        except Exception as e:  # never let instrumentation break the agent
            diff = f'__snapshot_error__ {type(e).__name__}: {e}'
        last = getattr(ctx, '_anytime_last', None)
        if diff == last:
            return
        ctx._anytime_last = diff
        row = {'call': ctx.tool_calls_used, 'tool': tool_name,
               'elapsed_s': round(ctx.agent_elapsed_seconds or 0.0, 1), 'diff': diff}
        with open(out_dir / f'{ctx.task_id}.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(row) + '\\n')

    def wrap(ctx, name, fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                record(ctx, name)
                return result
        else:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                record(ctx, name)
                return result
        return wrapper

    def create_tools(self):
        tools = original(self)
        return {n: wrap(self, n, f) if n in SNAPSHOT_TOOLS else f for n, f in tools.items()}

    create_tools._anytime = True
    SwegemmaContext.create_tools = create_tools


def save_artifacts(subdir, instance_id, patch, test_output):
    \"\"\"Keep the patch and the grading pytest output of a task for later diagnosis.\"\"\"
    out = RESULTS_DIR / subdir
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{instance_id}.patch').write_text(patch or '', encoding='utf-8')
    (out / f'{instance_id}.test.log').write_text(test_output or '', encoding='utf-8')"""

HARNESS_CHECK = """def check_harness(tasks):
    \"\"\"Grade each task's reference solution: every task should resolve if local grading works.\"\"\"
    from adk_submission import ModelRegistry
    from swegemma.deduplication import resolve_task_snapshot_paths
    from swegemma.harness.verification import verify_task

    evaluator = make_evaluator(ModelRegistry())
    rows = []
    for task in tasks:
        snapshot, base_snapshot, snapshot_patch = resolve_task_snapshot_paths(
            DATA_DIR / 'snapshots', task.instance_id, task.repo)
        start = time.time()
        r = run_sync(verify_task, evaluator.docker, evaluator.config, task, snapshot,
                     base_snapshot_path=base_snapshot, patch_path=snapshot_patch,
                     agent_patch=task.patch, start_time=time.perf_counter())
        save_artifacts('harness_check', task.instance_id, task.patch, r.test_output)
        rows.append({'instance_id': task.instance_id, 'gold_resolved': bool(r.resolved),
                     'test_exit_code': r.test_exit_code, 'seconds': round(time.time() - start, 1),
                     'error': r.error_message})
        print(f'  {task.instance_id:<16} gold_resolved={r.resolved} exit={r.test_exit_code} '
              f'{rows[-1]["seconds"]}s {r.error_message or ""}', flush=True)
    df = pd.DataFrame(rows)
    print(f'Reference solutions resolved: {int(df.gold_resolved.sum())}/{len(df)}')
    return df


if DEV and (RUN_HARNESS_CHECK or GOLD_CHECK_ONLY):
    harness_check = check_harness(dev_tasks)
    harness_check.to_csv(WORKING_DIR / 'gold_check.csv', index=False)"""

RUN_EVAL = """def run_dev_eval(tasks):
    if RECORD_ANYTIME:
        install_anytime_recorder()
    evaluator = make_evaluator(model_registry, adapter_manifest)
    rows_path = WORKING_DIR / 'dev_results.jsonl'  # appended per task, so partial runs keep their results

    async def one(idx, task, sem):
        async with sem:
            print(f'[{idx}/{len(tasks)}] start {task.instance_id} ({task.repo})', flush=True)
            start = time.time()
            try:
                r = await evaluator.evaluate_task(task=task, task_index=idx, total_tasks=len(tasks))
                save_artifacts('agent', task.instance_id, r.agent_patch, r.test_output)
                row = {
                    'instance_id': task.instance_id, 'repo': task.repo, 'resolved': bool(r.resolved),
                    'tool_calls': r.tool_calls, 'patch_chars': len((r.agent_patch or '').strip()),
                    'test_exit_code': r.test_exit_code, 'seconds': round(r.duration_seconds, 1),
                    'status': r.status, 'error': r.error_message,
                }
            except Exception as e:  # keep going so one broken task does not end the run
                row = {'instance_id': task.instance_id, 'repo': task.repo, 'resolved': False,
                       'seconds': round(time.time() - start, 1), 'error': f'{type(e).__name__}: {e}'}
            with open(rows_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, default=str) + '\\n')
            print(f'    {task.instance_id} -> resolved={row["resolved"]} tool_calls={row.get("tool_calls")} '
                  f'patch_chars={row.get("patch_chars")} {row["seconds"]}s', flush=True)
            return row

    async def run_all():
        sem = asyncio.Semaphore(max(1, DEV_CONCURRENCY))
        return await asyncio.gather(*(one(i, t, sem) for i, t in enumerate(tasks, start=1)))

    rows = run_sync(run_all)
    df = pd.DataFrame(rows)
    df.to_csv(WORKING_DIR / 'dev_results.csv', index=False)
    print(f'\\nResolved {int(df.resolved.sum())}/{len(df)} = {df.resolved.mean():.2%}')
    print(f'Per-task patches, test output and traces: {RESULTS_DIR}')
    return df


if DEV and not GOLD_CHECK_ONLY:
    dev_results = run_dev_eval(dev_tasks)
    display(dev_results)"""

SHUTDOWN = """if globals().get('server_instance') is not None:
    server_instance.stop()
    server_instance = None
    print('vLLM server stopped.')"""


def md(text):
    return {'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(keepends=True)}


def code(text):
    return {'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [],
            'source': text.splitlines(keepends=True)}


def submission_cells():
    files = sorted(p.relative_to(SUBMISSION_DIR).as_posix()
                   for p in SUBMISSION_DIR.rglob('*') if p.is_file())
    files.sort(key=lambda f: FILE_ORDER.index(f) if f in FILE_ORDER else len(FILE_ORDER))
    for rel in files:
        content = (SUBMISSION_DIR / rel).read_text(encoding='utf-8')
        yield code(f'%%writefile {KAGGLE_SUBMISSION_DIR}/{rel}\n{content}')


def build_notebook():
    cells = [
        md(INTRO),
        code(SETTINGS),
        md('## 1. Submission files\nEdit these cells to change the agent. '
           '`model:` in `agent.yaml` must name one of the four allowed quantized models.'),
        *submission_cells(),
        md('## 2. Package `submission.zip`'),
        code(PACKAGE),
        md('## 3. Install the harness and validate\nSkipped during the scoring re-run. '
           'The dev evaluation needs the **GPU L4 x4** accelerator, which can only be chosen in the notebook editor.'),
        code(GPU_CHECK),
        code(INSTALL),
        code(VALIDATE),
        md('## 4. Dev evaluation on public tasks\n'
           'Runs only when `RUN_DEV_EVAL = True` and this is not the scoring re-run. '
           'Expect ~10-20 min for vLLM startup plus up to `max_time_minutes` per task.'),
        code(PICK_TASKS),
        code(EVAL_SETUP),
        code(HARNESS_CHECK),
        code(START_VLLM),
        code(RUN_EVAL),
        code(SHUTDOWN),
    ]
    for i, cell in enumerate(cells):
        cell['id'] = f'cell-{i:02d}'
    return {
        'cells': cells,
        'metadata': {
            'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
            'language_info': {'name': 'python'},
        },
        'nbformat': 4,
        'nbformat_minor': 5,
    }


def kernel_metadata(username):
    # Inputs and environment mirror the official starter notebook
    return {
        'id': f'{username}/{NOTEBOOK_SLUG}',
        'title': NOTEBOOK_TITLE,
        'code_file': f'{NOTEBOOK_SLUG}.ipynb',
        'language': 'python',
        'kernel_type': 'notebook',
        'is_private': True,
        'enable_gpu': True,
        'enable_tpu': False,
        'enable_internet': False,
        'keywords': ['gpu'],
        'dataset_sources': ['metric/gemma-4-developer-agent-wheelhouse'],
        'kernel_sources': [],
        'competition_sources': ['gemma-4-developer-agent'],
        'model_sources': [
            'google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2',
            'google/gemma-4/Other/gemma-4-12b-it-qat-w4a16-ct/2',
            'google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2',
            'google/gemma-4/Other/gemma-4-e2b-it-qat-w4a16-ct/2',
        ],
        'docker_image': 'gcr.io/kaggle-private-byod/python@sha256:'
                        '37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461',
        'machine_shape': 'NvidiaL4',
    }


def main():
    global NOTEBOOK_SLUG, NOTEBOOK_TITLE, SUBMISSION_DIR
    load_dotenv(ROOT / '.env')
    username = os.environ.get('KAGGLE_USERNAME') or 'YOUR_KAGGLE_USERNAME'
    gold_check = '--gold-check' in sys.argv
    # --submit-only: no dev evaluation, so the notebook runs on CPU and can be pushed and submitted directly
    submit_only = '--submit-only' in sys.argv
    if '--agent' in sys.argv:  # build from another agent folder, e.g. agents/public_baseline
        SUBMISSION_DIR = ROOT / sys.argv[sys.argv.index('--agent') + 1]
    out_dir = OUT_DIR
    if gold_check:  # separate CPU-only notebook that grades every reference solution
        NOTEBOOK_SLUG, NOTEBOOK_TITLE = 'gemma-4-agent-gold-check', 'Gemma 4 Agent Gold Check'
        out_dir = ROOT / 'kaggle_gold'
    out_dir.mkdir(exist_ok=True)
    nb = build_notebook()
    # Dev set: tasks whose reference solution passes the local grader (dev/validated_tasks.txt)
    ids_file = ROOT / 'dev' / 'validated_tasks.txt'
    dev_ids = ids_file.read_text().split() if ids_file.exists() else []
    if '--dev-sample' in sys.argv:  # evenly spaced over the sorted list = stratified by repo
        n = int(sys.argv[sys.argv.index('--dev-sample') + 1])
        dev_ids = dev_ids[::max(1, len(dev_ids) // n)][:n]
    concurrency = sys.argv[sys.argv.index('--concurrency') + 1] if '--concurrency' in sys.argv else '1'
    subdirs = sorted({p.parent.relative_to(SUBMISSION_DIR).as_posix() for p in SUBMISSION_DIR.rglob('*')
                      if p.is_file() and p.parent != SUBMISSION_DIR})
    for cell in nb['cells']:
        cell['source'] = [line.replace('__SUBDIRS__', repr(tuple(subdirs))).replace('__DEV_TASK_IDS__', repr(dev_ids)).replace('__DEV_CONCURRENCY__', concurrency)
                          for line in cell['source']]
    meta = kernel_metadata(username)
    if gold_check:
        for cell in nb['cells']:
            cell['source'] = [line.replace('GOLD_CHECK_ONLY = False', 'GOLD_CHECK_ONLY = True')
                              for line in cell['source']]
        meta.update(enable_gpu=False, keywords=[], model_sources=[])
        meta.pop('machine_shape')
    if submit_only:
        meta.update(enable_gpu=False)
        meta.pop('machine_shape', None)
        for cell in nb['cells']:
            cell['source'] = [line.replace('RUN_DEV_EVAL = True', 'RUN_DEV_EVAL = False')
                              for line in cell['source']]
    nb_path = out_dir / f'{NOTEBOOK_SLUG}.ipynb'
    nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    (out_dir / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {nb_path} and {out_dir / "kernel-metadata.json"}')


if __name__ == '__main__':
    main()
