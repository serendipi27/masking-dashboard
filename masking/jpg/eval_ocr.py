"""OCR 엔진별 정확도 비교(개발용 도구, run_masking 파이프라인에는 포함되지 않음).

원본 이미지에서 18개 필드를 찾아 값을 읽고, 이 문서가 원래 만족해야 하는 산술 관계
(건강+장기요양=소계, 소계+연금+고용+산재=보험료합계=납부할금액)와 형식(자릿수 등)이
읽은 값에서도 성립하는지로 정확도를 판정한다. 실제 값을 미리 알고 있어야 하는 정답표가
필요 없고, 결과에는 통과/실패 개수만 남아 실제 데이터를 노출하지 않는다.

사용법(프로젝트 루트에서):
    python -m masking.jpg.eval_ocr local
    python -m masking.jpg.eval_ocr upstage      # 이미지가 Upstage 서버로 전송됨
    python -m masking.jpg.eval_ocr local upstage   # 두 엔진을 한 번에 비교
"""
import glob
import re
import sys
import time

from .mask_jpg import check_template, locate_fields
from .rules import FIELDS

BANK_RE = re.compile(r'^\D*[\d\-]*\d\*+$')


def _amt(field):
    return int(re.sub(r'[^\d]', '', field['text']) or -1)


def evaluate_image(fields):
    """필드별 통과 여부 {field_id: bool}. found=필드를 찾았는지, valid=값이 온전해 보이는지."""
    checks = {}
    for fid, f in fields.items():
        if f is None:
            checks[fid] = False
            continue
        kind = FIELDS[fid][1]
        t = f['text']
        if kind == 'digits_id':
            checks[fid] = len(re.sub(r'\D', '', t)) >= 11
        elif kind == 'bank_account':
            checks[fid] = bool(BANK_RE.match(t.replace(' ', '')))
        elif kind in ('company', 'person_title'):
            checks[fid] = len(t.strip()) >= 2
        else:                                    # amount, amount:*
            checks[fid] = _amt(f) > 0
    amt = {fid: _amt(fields[fid]) for fid in FIELDS if fields.get(fid) and FIELDS[fid][1].startswith('amount')}
    rel_ok = True
    if all(k in amt for k in ('amt_health', 'amt_ltc', 'amt_sub')):
        rel_ok &= amt['amt_health'] + amt['amt_ltc'] == amt['amt_sub']
    if all(k in amt for k in ('amt_sub', 'amt_pension', 'amt_employ', 'amt_accident', 'amt_total')):
        rel_ok &= amt['amt_sub'] + amt['amt_pension'] + amt['amt_employ'] + amt['amt_accident'] == amt['amt_total']
    if all(k in amt for k in ('amt_total', 'amt_due')):
        rel_ok &= amt['amt_total'] == amt['amt_due']
    checks['_relations'] = rel_ok
    return checks


def run(engine_name):
    from PIL import Image
    if engine_name == 'local':
        from . import ocr_local as eng
        get_lines = eng.get_lines
    elif engine_name == 'upstage':
        from . import ocr_upstage as eng
        get_lines = eng.get_lines
    else:
        raise ValueError(engine_name)

    files = sorted(glob.glob('orig_data/*.jpg'))
    total, passed, times, found_fields, total_fields = 0, 0, [], 0, 0
    per_image = []
    for f in files:
        t0 = time.time()
        try:
            W, H = Image.open(f).size
            lines = get_lines(f)
            check_template(lines, W, H)
            fields = locate_fields(lines, W, H)
            checks = evaluate_image(fields)
        except Exception as e:
            per_image.append((f, 'ERROR', str(e)))
            continue
        dt = time.time() - t0
        times.append(dt)
        ok = sum(1 for k, v in checks.items() if v)
        total_fields += len(FIELDS)
        found_fields += sum(1 for fid in FIELDS if fields.get(fid) is not None)
        total += len(checks)
        passed += ok
        per_image.append((f, f'{ok}/{len(checks)}', f'{dt:.1f}초'))
    return dict(engine=engine_name, files=len(files), passed=passed, total=total,
               found_fields=found_fields, total_fields=total_fields,
               avg_time=sum(times) / len(times) if times else None, per_image=per_image)


def main(argv):
    engines = argv or ['local']
    results = [run(e) for e in engines]
    print(f"{'엔진':<10}{'필드 검출':<12}{'값 통과율':<14}{'이미지당 평균 시간':<10}")
    for r in results:
        rate = f"{r['passed']}/{r['total']} ({100 * r['passed'] / r['total']:.0f}%)" if r['total'] else 'N/A'
        found = f"{r['found_fields']}/{r['total_fields']}"
        t = f"{r['avg_time']:.1f}초" if r['avg_time'] else 'N/A'
        print(f"{r['engine']:<10}{found:<12}{rate:<14}{t:<10}")
        for f, status, extra in r['per_image']:
            print(f'   {f.split("/")[-1]:<24} {status:<10} {extra}')
    return results


if __name__ == '__main__':
    main(sys.argv[1:])
