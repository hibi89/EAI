"""P17 independent DictReader rescan verifies schema-drift report from raw sources."""
from collections import defaultdict
import csv
import io

from .analysis import _NUMBER
from .csv_analysis import MAX_ROWS,MAX_COLUMNS,MAX_FIELD_CHARS
from .csv_quality import source_snapshot
from .csv_schema_drift import DriftGoal, VERSION, SCOPE


def _independent_profile(path,encoding):
    raw,digest=source_snapshot(path)
    old=csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        parser=csv.DictReader(io.StringIO(raw.decode(encoding),newline=''),strict=True)
        headers=parser.fieldnames
        if type(headers) is not list or not 1<=len(headers)<=MAX_COLUMNS or (
            len({x.casefold() for x in headers})!=len(headers)
        ):
            raise ValueError('schema drift receipt missing or duplicate header')
        tally=defaultdict(lambda:{'numeric_count':0,'text_count':0,'missing_count':0})
        total=0
        for row in parser:
            total+=1
            if total>MAX_ROWS or None in row or any(
                type(cell) is not str or len(cell)>MAX_FIELD_CHARS
                for cell in row.values()
            ):
                raise ValueError('schema drift receipt malformed row')
            for col in headers:
                cell=row[col].strip()
                if cell=='':tally[col]['missing_count']+=1
                elif _NUMBER.fullmatch(cell):tally[col]['numeric_count']+=1
                else:tally[col]['text_count']+=1
        profiles=[]
        for col in headers:
            info=tally[col]
            a,b=info['numeric_count'],info['text_count']
            kind='mixed' if a and b else 'numeric' if a else 'text' if b else 'empty'
            profiles.append({'column':col,'type':kind,'numeric_count':a,
                             'text_count':b,'missing_count':info['missing_count']})
    finally:
        csv.field_size_limit(old)
    if source_snapshot(path)[1]!=digest:
        raise ValueError('schema drift receipt source changed during verification')
    return {'filename':path.name,'sha256':digest,'rows':total,
            'columns':headers,'profiles':profiles}


def verify_drift_receipt(goal: DriftGoal, result: object):
    if type(goal) is not DriftGoal or type(result) is not dict:
        raise ValueError('schema drift receipt verification failed: invalid envelope')
    base=_independent_profile(goal.baseline,goal.encoding)
    current=_independent_profile(goal.current,goal.encoding)
    previous=set(base['columns'])
    new=set(current['columns'])
    left_types={item['column']:item['type'] for item in base['profiles']}
    right_types={item['column']:item['type'] for item in current['profiles']}
    delta={'added':sorted(new-previous),'removed':sorted(previous-new),
           'reordered':previous==new and base['columns']!=current['columns'],
           'type_changes':[{'column':name,'before':left_types[name],
                            'after':right_types[name]}
                           for name in sorted(previous & new)
                           if left_types[name]!=right_types[name]]}
    changed=bool(delta['added'] or delta['removed'] or delta['reordered'] or delta['type_changes'])
    unknown=base['rows']==0 or current['rows']==0 or any(
        item['type']=='empty' for item in base['profiles']+current['profiles']
    )
    state='CONFLICT' if changed else 'UNAVAILABLE' if unknown else 'AGREE'
    expected={'version':VERSION,'kind':'csv_schema_drift','goal':goal.goal,
              'status':state,'encoding':goal.encoding,'baseline':base,
              'current':current,'changes':delta,'scope':SCOPE}
    if result != expected:
        raise ValueError('schema drift receipt verification failed: inconsistent or forged')
    diag=({'type':'SCHEMA_DRIFT_REVIEW','action_required':True,
           'hint':'추가·삭제·열 순서·데이터 유형 변경의 원본 영향 범위를 확인하세요.'}
          if state=='CONFLICT' else
          {'type':'SCHEMA_EVIDENCE_INCOMPLETE','action_required':True,
           'hint':'빈 파일 또는 관측값이 없는 열이 있어 유형 판단을 보류합니다.'}
          if state=='UNAVAILABLE' else
          {'type':'NONE','action_required':False})
    return ['source_hashes','columns','per_column_types','changes','status'],diag
