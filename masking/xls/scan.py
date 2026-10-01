"""XLS 유출 스캔과 구조 검증. 결과에는 위치와 종류만 담고 실제값은 절대 출력하지 않는다."""
import re

import xlrd

from ..core.leak_common import digits as _digits


def scan_xls(path, tokens):
    hits = []
    book = xlrd.open_workbook(str(path))
    numeric_tokens = [(k, t) for k, t in tokens if len(_digits(t)) >= 6 and _digits(t) == re.sub(r'[\s-]', '', t)]
    for sh in book.sheets():
        for r in range(sh.nrows):
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype != 1 or not cell.value.strip():
                    continue
                low, dg = cell.value.lower(), _digits(cell.value)
                for kind, t in tokens:
                    if t.lower() in low:
                        hits.append((f'R{r + 1}C{c + 1}', kind))
                for kind, t in numeric_tokens:
                    if _digits(t) in dg and t.lower() not in low:
                        hits.append((f'R{r + 1}C{c + 1}', kind + '-digits'))
    raw = open(path, 'rb').read()      # 삭제된 문자열이 파일 안에 남아 있는지 원시 바이트도 검사
    for kind, t in tokens:
        variants = [t.encode('utf-16le')]
        if t.isascii():
            variants.append(t.encode('latin-1'))
        if any(v in raw for v in variants):
            hits.append(('raw-bytes', kind))
    return sorted(set(hits))


def _shape(v):
    return re.sub(r'[가-힣]', '가', re.sub(r'[A-Za-z]', 'a', re.sub(r'\d', '9', str(v))))


def verify_structure(orig_path, new_path):
    """열 형식·데이터 형 유지 여부 검증(마스킹의 핵심 목적). 문제 목록을 반환."""
    problems = []
    ob, nb = xlrd.open_workbook(str(orig_path), formatting_info=True), xlrd.open_workbook(str(new_path), formatting_info=True)
    if ob.user_name and ob.user_name == nb.user_name:
        problems.append('파일 속성(마지막 저장자)이 원본과 동일')
    o, n = ob.sheet_by_index(0), nb.sheet_by_index(0)
    if (o.nrows, o.ncols) != (n.nrows, n.ncols):
        return [f'시트 크기 변경 {o.nrows}x{o.ncols} -> {n.nrows}x{n.ncols}']
    shape_cols = {1: '승인번호', 4: '사업자번호', 9: '사업자번호'}
    same_cols = {0: '작성일자', 2: '발급일자', 3: '전송일자', 25: '품목일자', 17: '분류', 18: '종류', 19: '발급유형', 21: '영수/청구', 28: '품목수량'}
    for r in range(o.nrows):
        for c in range(o.ncols):
            a, b = o.cell(r, c), n.cell(r, c)
            if a.ctype != b.ctype:
                problems.append(f'R{r + 1}C{c + 1} 데이터 형 변경 {a.ctype}->{b.ctype}')
            elif ob.xf_list[o.cell_xf_index(r, c)].format_key != nb.xf_list[n.cell_xf_index(r, c)].format_key:
                problems.append(f'R{r + 1}C{c + 1} 서식 변경')
            if r >= 6 and a.ctype == 1 and a.value.strip():
                if c in shape_cols and _shape(a.value) != _shape(b.value):
                    problems.append(f'R{r + 1}C{c + 1} {shape_cols[c]} 형식 변경')
                if c in same_cols and a.value != b.value:
                    problems.append(f'R{r + 1}C{c + 1} {same_cols[c]} 값이 바뀜')
        if r >= 6 and o.cell(r, 15).ctype == 2:
            h, s, t = (n.cell_value(r, c) for c in (14, 15, 16))
            if o.cell_value(r, 14) == o.cell_value(r, 15) + o.cell_value(r, 16) and h != s + t:
                problems.append(f'R{r + 1} 합계 != 공급가액+세액')
    return problems
