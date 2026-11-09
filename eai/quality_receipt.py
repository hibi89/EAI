"""P16 independent column-oriented audit over source bytes for quality receipts."""
from collections import Counter
from decimal import Decimal
import csv
import io

from .analysis import _NUMBER
from .csv_analysis import MAX_COLUMNS, MAX_FIELD_CHARS, MAX_ROWS
from .csv_quality import (QualityGoal, VERSION, CODES, MAX_SAMPLES, SCOPE,
                          source_snapshot, quality_contract)


def verify_quality_receipt(goal: QualityGoal, receipt: object) -> tuple[list[str],dict]:
    if type(goal) is not QualityGoal or type(receipt) is not dict:
        raise ValueError('EAI quality receipt verification failed: invalid inputs')
    data,digest = source_snapshot(goal.source)
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        parsed = csv.DictReader(io.StringIO(data.decode(goal.encoding),newline=''),strict=True)
        headers = parsed.fieldnames
        if type(headers) is not list or not 1 <= len(headers) <= MAX_COLUMNS or (
            len(set(headers)) != len(headers)
        ):
            raise ValueError('EAI quality receipt failed: malformed header')
        if not (set(goal.required)|set(goal.unique_by)|
                {rule.column for rule in goal.numeric_rules}) <= set(headers):
            raise ValueError('EAI quality receipt failed: unknown columns')
        issue_counts = Counter()
        first_samples, affected, encountered = [],set(),set()
        records = 0

        def append(record, code, column):
            issue_counts[code] += 1
            affected.add(record)
            if len(first_samples) < MAX_SAMPLES:
                first_samples.append({'record':record,'code':code,'column':column})

        for records,row in enumerate(parsed,start=1):
            if records > MAX_ROWS or None in row or any(
                type(cell) is not str or len(cell)>MAX_FIELD_CHARS for cell in row.values()
            ):
                raise ValueError('EAI quality receipt failed: malformed row')
            required_values = {name:row[name].strip() for name in goal.required}
            for name in goal.required:
                if required_values[name] == '':
                    append(records,'MISSING_REQUIRED',name)
            unique = tuple(row[name].strip() for name in goal.unique_by)
            if all(unique):
                if unique in encountered:
                    append(records,'DUPLICATE_KEY',','.join(goal.unique_by))
                else:
                    encountered.add(unique)
            for rule in goal.numeric_rules:
                entry = row[rule.column].strip()
                if entry == '':
                    continue
                if not _NUMBER.fullmatch(entry):
                    append(records,'NOT_NUMERIC',rule.column)
                else:
                    value = Decimal(entry)
                    if value < rule.minimum:
                        append(records,'BELOW_MIN',rule.column)
                    elif value > rule.maximum:
                        append(records,'ABOVE_MAX',rule.column)
    finally:
        csv.field_size_limit(old)
    if source_snapshot(goal.source)[1] != digest:
        raise ValueError('EAI quality receipt failed: source changed')
    totals = {code:issue_counts[code] for code in CODES}
    status='UNAVAILABLE' if records == 0 else ('CONFLICT' if sum(totals.values()) else 'AGREE')
    expected={'version':VERSION,'kind':'csv_quality','goal':goal.goal,
              'filename':goal.source.name,'sha256':digest,'encoding':goal.encoding,
              'status':status,'rows':records,'columns':headers,
              'rules':quality_contract(goal),'counts':totals,
              'affected_records':len(affected),'samples':first_samples,'scope':SCOPE}
    if receipt != expected:
        raise ValueError('EAI quality receipt verification failed: forged or inconsistent audit')
    diagnostic=({'type':'QUALITY_REVIEW','action_required':True,
                 'hint':'누락·중복·숫자/범위 위반이 있는 레코드와 원본 규칙을 확인하세요.'}
                if status=='CONFLICT' else
                {'type':'QUALITY_EMPTY','action_required':True,
                 'hint':'헤더 외에 데이터 레코드가 없어 품질을 판정할 수 없습니다.'}
                if status=='UNAVAILABLE' else
                {'type':'NONE','action_required':False})
    return ['source_sha256','schema','per_column_rules','event_counts',
            'affected_records','samples','status'],diagnostic
