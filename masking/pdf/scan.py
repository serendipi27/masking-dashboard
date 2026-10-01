"""PDF 유출 스캔과 구조 검증. 결과에는 위치와 종류만 담고 실제값은 절대 출력하지 않는다."""
import re

import pymupdf

from .mask_pdf import cell_text, find_summary, norm, read_page
from .rules import KEEP_COLS, RULES


def _page_text(page):
    return norm(page.get_text()).lower()


def scan_pdf(path, tokens):
    """모든 쪽의 추출 텍스트(공백 무시)와 파일 속성, 원시 바이트에 실제값 토큰이 남았는지 검사."""
    hits = []
    doc = pymupdf.open(str(path))
    toks = [(k, t, norm(t).lower()) for k, t in tokens if len(norm(t)) >= 2]
    for i, page in enumerate(doc):
        text = _page_text(page)
        hits += [(f'p{i + 1}', k) for k, t, tn in toks if tn in text]
    meta = norm(' '.join(str(v) for v in doc.metadata.values() if v)).lower()
    hits += [('metadata', k) for k, t, tn in toks if tn in meta]
    raw = open(path, 'rb').read()
    hits += [('raw-bytes', k) for k, t, tn in toks if t.isascii() and len(t) >= 4 and t.encode() in raw]
    return sorted(set(hits))


_DASH_EQUIV = str.maketrans('‐‑‒–—−', '------')  # 하이픈류(U+2010~U+2014, 마이너스 U+2212)를
                                                                              # 일반 하이픈(-)으로 통일. 카드번호처럼 셀 안에서
                                                                              # 여러 줄로 나눠 그려진 텍스트를 PDF에서 다시 읽으면
                                                                              # 원본과 시각적으로 구분 안 되는 다른 하이픈 문자로
                                                                              # 추출되는 경우가 있어(육안 렌더링은 원본과 동일함을
                                                                              # 확인함), 형식 비교에서 오탐이 나지 않게 함.


def _shape(v):
    v = v.translate(_DASH_EQUIV)
    return re.sub(r'[가-힣]', '가', re.sub(r'[A-Za-z]', 'a', re.sub(r'\d', '9', v)))


def verify_structure(orig_path, new_path):
    """쪽 수·표 행열·유지 열 값·열별 형식·금액 범위·합계/건수·셀 넘침·변경 영역 밖 렌더링 동일 여부를 검증."""
    problems = []
    o, n = pymupdf.open(str(orig_path)), pymupdf.open(str(new_path))
    if len(o) != len(n):
        return [f'쪽 수 변경 {len(o)} -> {len(n)}']
    total_new, rows_new = 0, 0
    for pi, (po, pn) in enumerate(zip(o, n)):
        tag = f'p{pi + 1}'
        try:
            ro, rn = read_page(po), read_page(pn)
        except ValueError as e:
            problems.append(f'{tag} 표 읽기 실패: {e}')
            continue
        if len(ro) != len(rn):
            problems.append(f'{tag} 행 수 변경 {len(ro)} -> {len(rn)}')
            continue
        rows_new += len(rn)
        for ri, (a, b) in enumerate(zip(ro, rn), 1):
            for ci in KEEP_COLS:
                if cell_text(a.get(ci)) != cell_text(b.get(ci)):
                    problems.append(f'{tag} 행{ri} 열{ci} 유지 열 값이 바뀜')
            for ci, rule in RULES.items():
                ta, tb = cell_text(a.get(ci)), cell_text(b.get(ci))
                if bool(ta) != bool(tb):
                    problems.append(f'{tag} 행{ri} 열{ci} 값 유무 변경')
                    continue
                if not tb:
                    continue
                if _shape(ta) != _shape(tb) and rule in ('card', 'holder', 'approval'):
                    problems.append(f'{tag} 행{ri} 열{ci} {rule} 형식 변경')
                if rule == 'amount':
                    va, vb = int(ta.replace(',', '')), int(tb.replace(',', ''))
                    total_new += vb
                    if va and not 0.55 <= vb / va <= 1.45:
                        problems.append(f'{tag} 행{ri} 금액 배율 범위 밖')
                cell = b[ci]
                for ln in cell['lines']:          # 셀을 넘치지 않는지
                    r = cell['rect']
                    if ln['x0'] < r.x0 + 0.5 or ln['x1'] > r.x1 - 0.5 or ln['origin'][1] - 0.9 * ln['size'] < r.y0 \
                            or ln['origin'][1] + 0.3 * ln['size'] > r.y1:
                        problems.append(f'{tag} 행{ri} 열{ci} 셀 넘침')
                        break
        # 변경 영역 밖 렌더링이 원본과 같은지
        po_pix, pn_pix = po.get_pixmap(dpi=72), pn.get_pixmap(dpi=72)
        rects = [c['rect'] for row in ro for ci, c in row.items() if ci in RULES]
        so = find_summary(po)
        if so:
            rects.append(pymupdf.Rect(so['num']['bbox']))
        for r in rects:
            ir = (r + (-2, -2, 2, 2)).irect
            po_pix.set_rect(ir, (255, 255, 255))
            pn_pix.set_rect(ir, (255, 255, 255))
        if po_pix.samples != pn_pix.samples:
            problems.append(f'{tag} 변경 영역 밖 렌더링 차이')
    so, sn = find_summary(o[-1]), find_summary(n[-1])
    if bool(so) != bool(sn):
        problems.append('요약 박스 유무 변경')
    elif sn:
        if int(sn['num']['text'].replace(',', '')) != total_new:
            problems.append('요약 합계 != 금액 합')
        if sn['count'] and (sn['count']['text'] != so['count']['text'] or int(sn['count']['text'][:-1]) != rows_new):
            problems.append('요약 건수 불일치')
    return problems
