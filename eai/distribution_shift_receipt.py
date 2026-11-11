"""Independent DictReader and statistics.median proof of P29 shift receipts."""
import csv
from decimal import Decimal, localcontext
import io
from statistics import median

from .analysis import _NUMBER
from .csv_analysis import MAX_COLUMNS, MAX_FIELD_CHARS, MAX_ROWS
from .csv_quality import source_snapshot
from .csv_distribution_shift import ShiftGoal, VERSION, SCOPE


def _other_scan(path, goal):
    data, digest = source_snapshot(path)
    old=csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader=csv.DictReader(io.StringIO(data.decode(goal.encoding),newline=""),restkey="__extra")
        fields=reader.fieldnames
        if fields is None or not 1<=len(fields)<=MAX_COLUMNS or any(
            not 1<=len(name)<=60 or name != name.strip() or
            any(ord(c)<32 for c in name) for name in fields
        ) or len({name.casefold() for name in fields})!=len(fields):
            raise ValueError("invalid independent headers")
        if not set(goal.columns)<=set(fields):
            raise ValueError("independent column missing")
        arrays={name:[] for name in goal.columns}
        total,invalid=0,0
        for row in reader:
            total+=1
            if total>MAX_ROWS or "__extra" in row or None in row or any(
                value is None or len(value)>MAX_FIELD_CHARS for value in row.values()
            ):
                raise ValueError("invalid independent row")
            values=[row[name].strip() for name in goal.columns]
            if any(not v or not _NUMBER.fullmatch(v) for v in values):
                invalid+=1
                continue
            for name,value in zip(goal.columns,values):
                arrays[name].append(Decimal(value))
    finally:
        csv.field_size_limit(old)
    if source_snapshot(path)[1]!=digest:
        raise ValueError("independent source changed")
    return {"filename":path.name,"sha256":digest,"rows":total,
            "complete_rows":total-invalid,"invalid_rows":invalid},arrays


def verify_shift_receipt(goal: ShiftGoal, report: dict) -> tuple[list[str],dict]:
    if type(goal) is not ShiftGoal or type(report) is not dict or set(report)!={
        "version","kind","goal","status","threshold","sources","columns","scope"
    } or report.get("version")!=VERSION or report.get("kind")!="csv_distribution_shift" or (
        report.get("goal")!=goal.goal or report.get("scope")!=SCOPE or
        report.get("threshold")!=format(goal.threshold,"f")
    ):
        raise ValueError("independent shift receipt contract mismatch")
    baseline,old=_other_scan(goal.baseline,goal)
    current,new=_other_scan(goal.current,goal)
    if report.get("sources")!=[baseline,current]:
        raise ValueError("distribution source provenance/count mismatch")
    expected=[]
    has_shift=False
    unavailable=False
    with localcontext() as ctx:
        ctx.prec=110
        for name in goal.columns:
            if len(old[name])<goal.min_rows or len(new[name])<goal.min_rows:
                item={"column":name,"baseline_median":None,"current_median":None,
                      "baseline_mad":None,"shift_mad_units":None,
                      "state":"NOT_ESTIMABLE"}
                unavailable=True
            else:
                med_old=median(old[name])
                med_new=median(new[name])
                mad=median([abs(v-med_old) for v in old[name]])
                if mad==0:
                    score=None
                    state="NOT_ESTIMABLE"
                    unavailable=True
                else:
                    score=format((abs(med_new-med_old)/mad).quantize(
                        Decimal("0.000001")),"f")
                    state="SHIFT" if Decimal(score)>goal.threshold else "STABLE"
                    has_shift |= state=="SHIFT"
                item={"column":name,"baseline_median":format(med_old,"f"),
                      "current_median":format(med_new,"f"),
                      "baseline_mad":format(mad,"f"),
                      "shift_mad_units":score,"state":state}
            expected.append(item)
    status=("CONFLICT" if has_shift or baseline["invalid_rows"] or current["invalid_rows"]
            else "UNAVAILABLE" if unavailable else "AGREE")
    if report.get("columns")!=expected or report.get("status")!=status:
        raise ValueError("independent shift calculations/status mismatch")
    if source_snapshot(goal.baseline)[1]!=baseline["sha256"] or (
        source_snapshot(goal.current)[1]!=current["sha256"]
    ):
        raise ValueError("independent shift sources changed")
    diag=("SHIFT_REVIEW" if status=="CONFLICT"
          else "INCOMPLETE_DISTRIBUTION" if status=="UNAVAILABLE" else "NONE")
    return (
        ["source_sha256","row_counts","median_mad","shift_threshold","status"],
        {"type":diag,"action_required":status!="AGREE",
         "hint":"Review sample quality, baseline suitability and threshold."
         if status!="AGREE" else ""},
    )
