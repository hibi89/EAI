"""P17 offline source-schema drift between two bounded local CSV files."""
from dataclasses import dataclass
import csv
import io
from pathlib import Path

from .analysis import _NUMBER
from .csv_analysis import MAX_ROWS, MAX_COLUMNS, MAX_FIELD_CHARS, ALLOWED_ENCODINGS
from .csv_quality import source_snapshot

VERSION='eai.goal.csv_schema_drift.v1'
SCOPE=('두 사용자가 지정한 로컬 CSV의 열 추가·삭제·순서·추정 값 종류만 비교했습니다. '
       '행 단위 실제 데이터·고유 식별자는 출력하지 않습니다. 타입은 값 기반 추정일 뿐 '
       '정식 스키마 계약, 원본 진실성, 시간적 인과관계를 보장하지 않습니다. '
       '원본 수정·온라인 접속·모델 호출을 수행하지 않습니다.')


@dataclass(frozen=True)
class DriftGoal:
    goal: str
    baseline: Path
    current: Path
    encoding: str


def _inside(root: Path, value: object) -> Path:
    if type(value) is not str or not 1 <= len(value) <= 512 or any(
        ord(x)<32 or x in '\\:' for x in value
    ):
        raise ValueError('schema drift source must be a relative local filename')
    path=Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('schema drift source escapes the selected directory')
    selected=(root/path).resolve(strict=True)
    if not selected.is_relative_to(root):
        raise ValueError('schema drift source symlink escapes the directory')
    return selected


def validate_drift_goal(raw: object, goal_path: Path) -> DriftGoal:
    if type(raw) is not dict or set(raw) != {
        'version','kind','goal','baseline','current','encoding'
    } or type(raw['version']) is not int or raw['version']!=1 or (
        raw['kind']!='csv_schema_drift'
    ):
        raise ValueError('invalid versioned CSV schema drift contract')
    title=raw['goal']
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(x)<32 for x in title
    ):
        raise ValueError('invalid schema drift goal')
    encoding=raw['encoding']
    if type(encoding) is not str or encoding not in ALLOWED_ENCODINGS:
        raise ValueError('invalid schema drift encoding')
    root=goal_path.parent.resolve(strict=True)
    left,right=_inside(root,raw['baseline']),_inside(root,raw['current'])
    if left==right:
        raise ValueError('schema drift requires two distinct CSV inputs')
    return DriftGoal(title.strip(),left,right,encoding)


def _classify(counter: dict) -> str:
    number,text=counter['numeric_count'],counter['text_count']
    return 'mixed' if number and text else 'numeric' if number else (
        'text' if text else 'empty')


def _profile(path: Path, encoding: str) -> dict:
    """First scanner: ordered csv.reader with per-column index counters."""
    content,digest=source_snapshot(path)
    previous=csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader=csv.reader(io.StringIO(content.decode(encoding),newline=''),strict=True)
        try:
            headers=next(reader)
        except StopIteration as exc:
            raise ValueError('schema drift CSV is missing a header') from exc
        if not 1 <= len(headers) <= MAX_COLUMNS or any(
            x!=x.strip() or not 1<=len(x)<=60 or any(ord(c)<32 for c in x)
            for x in headers
        ) or len({x.casefold() for x in headers})!=len(headers):
            raise ValueError('schema drift CSV headers are invalid')
        bins=[{'numeric_count':0,'text_count':0,'missing_count':0} for _ in headers]
        records=0
        for row in reader:
            records+=1
            if records > MAX_ROWS or len(row)!=len(headers) or any(
                len(cell)>MAX_FIELD_CHARS for cell in row
            ):
                raise ValueError('schema drift row/field bound exceeded')
            for i,cell in enumerate(row):
                item=cell.strip()
                if not item:bins[i]['missing_count']+=1
                elif _NUMBER.fullmatch(item):bins[i]['numeric_count']+=1
                else:bins[i]['text_count']+=1
    finally:
        csv.field_size_limit(previous)
    if source_snapshot(path)[1]!=digest:
        raise ValueError('schema drift input changed during scan')
    profiles=[{'column':head,'type':_classify(bin),
               'numeric_count':bin['numeric_count'],'text_count':bin['text_count'],
               'missing_count':bin['missing_count']}
              for head,bin in zip(headers,bins)]
    return {'filename':path.name,'sha256':digest,'rows':records,
            'columns':headers,'profiles':profiles}


def drift_summary(left: dict,right: dict) -> tuple[str,dict]:
    first,second=left['columns'],right['columns']
    older,newer=set(first),set(second)
    old_types={row['column']:row['type'] for row in left['profiles']}
    new_types={row['column']:row['type'] for row in right['profiles']}
    difference={'added':sorted(newer-older),'removed':sorted(older-newer),
                'reordered':older==newer and first!=second,
                'type_changes':[{'column':name,'before':old_types[name],'after':new_types[name]}
                                for name in sorted(older & newer)
                                if old_types[name]!=new_types[name]]}
    has_change=bool(difference['added'] or difference['removed'] or
                    difference['reordered'] or difference['type_changes'])
    incomplete=(left['rows']==0 or right['rows']==0 or
                any(row['type']=='empty' for row in left['profiles']+right['profiles']))
    return 'CONFLICT' if has_change else 'UNAVAILABLE' if incomplete else 'AGREE',difference


def execute_drift_goal(goal: DriftGoal) -> dict:
    if type(goal) is not DriftGoal:
        raise ValueError('unvalidated schema drift goal')
    left,right=_profile(goal.baseline,goal.encoding),_profile(goal.current,goal.encoding)
    if source_snapshot(goal.baseline)[1]!=left['sha256'] or (
        source_snapshot(goal.current)[1]!=right['sha256']
    ):
        raise ValueError('schema drift source changed between scans')
    status,diff=drift_summary(left,right)
    return {'version':VERSION,'kind':'csv_schema_drift','goal':goal.goal,
            'status':status,'encoding':goal.encoding,
            'baseline':left,'current':right,'changes':diff,'scope':SCOPE}


def render_drift(report: dict) -> str:
    d=report['changes']
    lines=[f"EAI CSV 스키마 변경: {report['status']}",
           f"기준: {report['baseline']['filename']} ({report['baseline']['sha256']})",
           f"비교: {report['current']['filename']} ({report['current']['sha256']})",
           '추가: '+', '.join(d['added']),
           '삭제: '+', '.join(d['removed']),
           f"순서 변경: {d['reordered']}",
           f"유형 변경: {len(d['type_changes'])}"]
    for item in d['type_changes']:
        lines.append(f"{item['column']}: {item['before']} -> {item['after']}")
    lines.append(report['scope'])
    return '\n'.join(lines)
