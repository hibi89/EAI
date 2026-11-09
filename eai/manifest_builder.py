"""P15 safe stdout-only builder for pinned batch and dependency pipeline manifests.

Only explicitly named local goal JSON files are read. It does not create output
files, execute tasks, invoke models, contact APIs or alter source data.
"""
from pathlib import Path

from .decision_engine import ID_RE
from .goal_batch import _validate, _hash_file, MAX_ITEMS
from .goal_dispatch import _read_spec, ROUTED_KINDS
from .goal_pipeline import _prepare

MANIFEST_BUILDER_VERSION = 'eai.manifest.builder.v1'


def _pair(spec: str, label: str) -> tuple[str, str]:
    if type(spec) is not str or spec.count('=') != 1:
        raise ValueError(label + ' must be ID=relative.json')
    name, value = spec.split('=', 1)
    if not ID_RE.fullmatch(name) or not value:
        raise ValueError(label + ': invalid ID or empty value')
    return name, value


def build_goal_manifest(
    mode: str, root: str | Path, goals: list[str],
    requires: list[str] | tuple[str, ...] = (),
    continue_on_error: bool = True,
) -> dict:
    """Construct only well-scoped, SHA256-pinned manifest data; never write or solve."""
    if mode not in ('batch','pipeline') or type(mode) is not str:
        raise ValueError('mode must be batch or pipeline')
    if type(continue_on_error) is not bool:
        raise ValueError('continue_on_error must be boolean')
    if type(goals) is not list or not 1 <= len(goals) <= MAX_ITEMS:
        raise ValueError('1-6 goals required')
    if type(requires) not in (list,tuple):
        raise ValueError('requires must be a list')
    base = Path(root).expanduser().resolve(strict=True)
    if not base.is_dir():
        raise ValueError('root must be an existing directory')
    entries, seen, sources = [], set(), set()
    for goal_spec in goals:
        name, rel = _pair(goal_spec,'goal')
        if name in seen:
            raise ValueError('duplicate goal ID')
        if len(rel)>512 or any(ord(ch)<32 or ch in '\\:' for ch in rel):
            raise ValueError('goal path must be a short local POSIX-relative path')
        candidate = Path(rel)
        if candidate.is_absolute() or '..' in candidate.parts:
            raise ValueError('absolute or parent goal paths are not allowed')
        selected = (base/candidate).resolve(strict=True)
        if not selected.is_relative_to(base) or selected in sources:
            raise ValueError('goal path escapes root or duplicates a source')
        parsed, digest = _read_spec(selected)
        if type(parsed.get('kind')) is not str or parsed['kind'] not in ROUTED_KINDS:
            raise ValueError('unknown typed goal kind')
        if _hash_file(selected) != digest:
            raise ValueError('goal changed while computing SHA256')
        entries.append({'id':name,'goal':rel,'sha256':digest})
        seen.add(name)
        sources.add(selected)
    # No dependency parameter can affect a plain batch.
    if mode=='batch':
        if requires:
            raise ValueError('--requires is only valid for a pipeline')
        manifest={'version':1,'kind':'goal_batch',
                  'continue_on_error':continue_on_error,'items':entries}
        _validate(base/'.eai_generated_batch_manifest.json',manifest)
    else:
        deps={entry['id']:[] for entry in entries}
        used=set()
        for dependency_spec in requires:
            child, encoded = _pair(dependency_spec,'requires')
            if child not in deps or child in used:
                raise ValueError('unknown or duplicate --requires child')
            required=encoded.split(',')
            if len(required)>MAX_ITEMS-1 or any(not ID_RE.fullmatch(x) for x in required):
                raise ValueError('invalid --requires IDs')
            if len(set(required))!=len(required):
                raise ValueError('duplicate --requires prerequisite')
            deps[child]=required
            used.add(child)
        rows=[{**entry,'requires':deps[entry['id']]} for entry in entries]
        manifest={'version':1,'kind':'goal_pipeline',
                  'continue_on_error':continue_on_error,'items':rows}
        _prepare(base/'.eai_generated_pipeline_manifest.json',manifest)
    # Fail closed if any source changed while other files were processed.
    for entry in entries:
        selected=(base/entry['goal']).resolve(strict=True)
        if _hash_file(selected) != entry['sha256']:
            raise ValueError('goal changed during manifest construction')
    return manifest
