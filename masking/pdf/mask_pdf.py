"""PDF(비씨카드 전체 이용내역) 마스킹.

PyMuPDF로 표 셀 좌표를 얻어 바꿀 셀의 원문을 redaction으로 실제 삭제(위에 칠하는 방식이 아님)하고,
같은 위치·글자 크기·색으로 더미 텍스트를 넣는다. 가맹점명은 파란색 밑줄까지 다시 그린다.
"""
import re
from collections import Counter

import pymupdf

from ..core import generators as G
from ..core import regions as R
from ..core.amounts import scale_amount
from . import fakers as F
from ..core.fonts import load_font_bytes
from .rules import EXPECTED_HEADER, INSET, LINK_COLOR, PAD, PITCH, RULES, UL_DY, UL_H

LONGNUM = re.compile(r'\d{6,}')
PLACEHOLDER = re.compile(r'\{([Rr]):([^}]+)\}')      # 사전 값 안의 지역 자리표시자: {R:XX시}=치환된 지역 토큰, {r:XX시}=시·군을 뗀 이름


def norm(s):
    return re.sub(r'[\s ]+', '', s)


def rgb(c):
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


def read_cell_lines(page, rect):
    """셀 안의 텍스트를 줄 단위로 읽는다(글자 위치·크기·색 포함)."""
    lines = []
    for b in page.get_text('dict', clip=rect)['blocks']:
        for ln in b.get('lines', []):
            sp = [s for s in ln['spans'] if s['text'].strip()
                  and rect.contains(pymupdf.Point((s['bbox'][0] + s['bbox'][2]) / 2, (s['bbox'][1] + s['bbox'][3]) / 2))]
            if sp:
                lines.append(dict(text=''.join(s['text'] for s in sp), origin=sp[0]['origin'], size=sp[0]['size'],
                                  color=sp[0]['color'], x0=min(s['bbox'][0] for s in sp), x1=max(s['bbox'][2] for s in sp)))
    return sorted(lines, key=lambda d: d['origin'][1])


def read_page(page):
    """쪽의 표를 읽어 행별 {열 index: {rect, lines}} 목록을 반환. 표가 1개가 아니거나 헤더가 다르면 오류."""
    tabs = page.find_tables().tables
    if len(tabs) != 1:
        raise ValueError(f'표가 1개가 아님({len(tabs)}개)')
    t = tabs[0]
    header = [norm(page.get_textbox(pymupdf.Rect(c))) if c else '' for c in t.rows[0].cells]
    if header != EXPECTED_HEADER:
        raise ValueError('표 헤더 불일치')
    rows = []
    for row in t.rows[1:]:
        r = {}
        for ci, c in enumerate(row.cells):
            if c is not None:
                rect = pymupdf.Rect(c)
                r[ci] = dict(rect=rect, lines=read_cell_lines(page, rect))
        rows.append(r)
    return rows


def cell_text(cell):
    return ''.join(ln['text'] for ln in cell['lines']).replace(' ', ' ').strip() if cell else ''


def find_summary(page):
    """마지막 쪽 요약 박스의 `N건`과 합계 숫자 span. 없으면 None."""
    spans = [s for b in page.get_text('dict')['blocks'] for ln in b.get('lines', []) for s in ln['spans']]
    label = next((s for s in spans if s['text'].strip() == '합계'), None)
    if not label:
        return None
    y = label['origin'][1]
    num = next((s for s in spans if abs(s['origin'][1] - y) < 2 and s['origin'][0] > label['origin'][0]
                and re.fullmatch(r'[\d,]+', s['text'].strip())), None)
    cnt = next((s for s in spans if re.fullmatch(r'\d+건', s['text'].strip())), None)
    return dict(num=num, count=cnt) if num else None


def wrap(font, text, size, max_w):
    """브라우저의 글자 단위 줄바꿈(word-break: break-all)을 흉내 낸 그리디 줄바꿈."""
    lines, cur = [], ''
    for ch in text:
        if cur and font.text_length(cur + ch, fontsize=size) > max_w:
            lines.append(cur.strip())
            cur = ch
        else:
            cur += ch
    lines.append(cur.strip())
    return [ln for ln in lines if ln] or ['']


class PdfMasker:
    def __init__(self, store, merchant_dict):
        self.s = store
        self.dict = merchant_dict
        self.unseen = set()
        self.total_mismatch = 0
        self.count_mismatch = 0
        self.stats = {'rows': 0, 'merchants': set(), 'cards': set()}

    # ---------- 값 변환기 ----------
    def _merchant_gen(self, rng, key):
        nums = LONGNUM.findall(key)
        skel = LONGNUM.sub('#', key)
        rep = self.dict.get(skel)
        if rep is None:
            self.unseen.add(key)
            rep = self._region_sub(F.merchant_fallback(rng, skel))
        rep = PLACEHOLDER.sub(lambda m: R.fake_token(self.s, m.group(2), base=(m.group(1) == 'r')), rep)
        it = iter(nums)
        return re.sub('#', lambda m: self.s.get('digits', next(it, ''), G.digits_like), rep)

    def _region_sub(self, text):
        for tok, fake in sorted(self.s.maps.get('regiontok', {}).items(), key=lambda kv: -len(kv[0])):
            if len(tok) >= 3 and tok[-1] in '시군구' and not tok.endswith('광역시'):
                text = text.replace(tok, fake).replace(tok[:-1], fake[:-1] if fake[-1] in '시군' else fake)
        return text

    def fake(self, rule, real, k):
        if rule == 'card':
            return self.s.get('card', real, lambda rng, r: F.card_number(rng, r))
        if rule == 'holder':
            return self.s.get('holder', real, lambda rng, r: F.holder(rng, r, self.s))
        if rule == 'approval':
            return real if not real.strip('0') else self.s.get('digits', real, G.digits_like)
        if rule == 'merchant':
            return self.s.get('merchant', real, self._merchant_gen)
        if rule == 'amount':
            return f"{scale_amount(int(real.replace(',', '')), k):,}"
        raise ValueError(rule)

    @staticmethod
    def real_values(row):
        out = {}
        for ci, rule in RULES.items():
            c = row.get(ci)
            if c and c['lines']:
                out[ci] = (rule, norm(cell_text(c)) if rule == 'merchant' else cell_text(c))
        return out

    # ---------- 수집 ----------
    def collect(self, doc):
        """실제값을 매핑 저장소에 모은다(값은 바꾸지 않음). 요약 박스의 건수·합계가 행과 맞는지도 확인."""
        rows_n, total = 0, 0
        for page in doc:
            for row in read_page(page):
                rows_n += 1
                for ci, (rule, real) in self.real_values(row).items():
                    if rule == 'amount':
                        total += int(real.replace(',', ''))
                    else:
                        self.fake(rule, real, 1.0)
                    if rule == 'merchant':
                        self.stats['merchants'].add(real)
                    if rule == 'card':
                        self.stats['cards'].add(real)
        self.stats['rows'] += rows_n
        summ = find_summary(doc[-1])
        if summ:
            if int(summ['num']['text'].replace(',', '')) != total:
                self.total_mismatch += 1
            if summ['count'] and int(summ['count']['text'][:-1]) != rows_n:
                self.count_mismatch += 1

    # ---------- 마스킹 ----------
    def mask(self, src, dst):
        k = self.s.amount_factor()
        doc = pymupdf.open(str(src))
        reg_font, bold_font = pymupdf.Font(fontbuffer=load_font_bytes(False)), pymupdf.Font(fontbuffer=load_font_bytes(True))
        changed, total = Counter(), 0
        plan = []
        for page in doc:                      # 1) 새 값 계산(총합은 요약 박스용)
            items = []
            for row in read_page(page):
                for ci, (rule, real) in self.real_values(row).items():
                    new = self.fake(rule, real, k)
                    if rule == 'amount':
                        total += int(new.replace(',', ''))
                    if new != real:
                        items.append((ci, rule, row[ci], new))
                        changed[ci] += 1
            plan.append(items)
        for page, items in zip(doc, plan):    # 2) 원문 삭제(텍스트와 밑줄만, 셀 테두리·배경은 유지)
            summ = find_summary(page)
            for _, _, cell, _ in items:
                page.add_redact_annot(cell['rect'] + (INSET, INSET, -INSET, -INSET), fill=False, cross_out=False)
            if summ:
                page.add_redact_annot(pymupdf.Rect(summ['num']['bbox']) + (0.3, 0.3, -0.3, -0.3), fill=False, cross_out=False)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                  text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            page.insert_font(fontname='MKR', fontbuffer=load_font_bytes(False))
            page.insert_font(fontname='MKB', fontbuffer=load_font_bytes(True))
            for ci, rule, cell, new in items:  # 3) 더미 텍스트 삽입(원본과 같은 중심·크기·색)
                bold = rule == 'merchant'
                font, name = (bold_font, 'MKB') if bold else (reg_font, 'MKR')
                first = cell['lines'][0]
                size, rect = first['size'], cell['rect']
                parts = list(re.fullmatch(r'(.+?-)(.+?-)(.+)', new).groups()) if rule == 'card' else wrap(font, new, size, rect.width - 2 * PAD[ci])
                yc = sum(ln['origin'][1] for ln in cell['lines']) / len(cell['lines'])
                for i, part in enumerate(parts):
                    y = yc + (i - (len(parts) - 1) / 2) * PITCH
                    w = font.text_length(part, fontsize=size)
                    x = (rect.x0 + rect.x1) / 2 - w / 2
                    page.insert_text((x, y), part, fontname=name, fontsize=size, color=rgb(first['color']))
                    if bold:
                        page.draw_rect(pymupdf.Rect(x, y + UL_DY, x + w, y + UL_DY + UL_H), color=None, fill=LINK_COLOR)
            if summ:                           # 요약 박스 합계: 마스킹된 금액의 합으로 다시 계산
                num = summ['num']              # 원본 숫자 영역 안에 들어가도록(넓으면 글자 크기를 줄여) 가운데 정렬
                text = f'{total:,}'
                box_w = num['bbox'][2] - num['bbox'][0]
                size = num['size']
                w = bold_font.text_length(text, fontsize=size)
                if w > box_w:
                    size, w = size * box_w / w, box_w
                page.insert_text((num['bbox'][0] + (box_w - w) / 2, num['origin'][1]), text, fontname='MKB', fontsize=size,
                                 color=rgb(num['color']))
        title = doc.metadata.get('title') or ''
        try:
            doc.subset_fonts()                 # 쓰지 않는 글리프(원본 글자 모양) 제거
        except Exception:
            pass
        doc.set_metadata({'title': title})
        doc.del_xml_metadata()
        doc.save(str(dst), garbage=4, deflate=True, clean=True)
        doc.close()
        return changed
