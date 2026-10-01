"""XLS(전자세금계산서 목록) 마스킹. xlrd로 읽고 xlutils로 서식을 유지한 채 저장한다."""
import json
import re
from collections import Counter

import xlrd
from xlutils.copy import copy as xl_copy

from ..core import generators as G
from ..core import regions as R
from ..core.amounts import scale_amount
from . import fakers as F
from .rules import AMOUNT_COLS, DATA_START_ROW, HEADER_ROW, KEEP_COLS, RECEIVER_IDENTITY_COLS, TEXT_RULES

LEGAL_PRE = re.compile(r'^\s*(?:\(주\)|（주）|\(유\)|（유）|주식회사|유한회사)\s*')
LEGAL_SUF = re.compile(r'\s*(?:\(주\)|（주）|\(유\)|（유）|주식회사|유한회사)\s*$')
LONGNUM = re.compile(r'\d{6,}')
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
FREE_RE = r'(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)|{reg}(?P<acct>\d{{2,6}}(?:-\d{{2,8}}){{1,3}})|(?P<id>\b[A-Za-z]{{1,3}}\d{{5,}}\b)|(?P<num>\d{{6,}})'


def set_cell(ws, r, k, value):
    """값만 바꾸고 기존 셀 서식(xf)은 유지."""
    row = ws._Worksheet__rows.get(r)
    cell = row._Row__cells.get(k) if row else None
    xf = cell.xf_idx if cell else None
    ws.write(r, k, value)
    if xf is not None:
        ws._Worksheet__rows[r]._Row__cells[k].xf_idx = xf


def tax_of(s_new, s_old, t_old):
    if t_old == 0:
        return 0
    return int(s_new * 0.1) if int(s_old * 0.1) == int(t_old) else int(round(s_new * 0.1))


class XlsMasker:
    def __init__(self, store, item_dict):
        self.s = store
        self.items = item_dict
        self.pair_lookup = {}
        self.free_re = re.compile(FREE_RE.format(reg=''))
        self.unseen_items = 0
        self.top_mismatch = 0
        self.receiver_canonical = {}   # 공급받는자(자사) 열(RECEIVER_IDENTITY_COLS) index -> 이 인스턴스에서
                                        # 처음 만난 실제값. 이후 행(과 이 인스턴스가 이어서 처리하는 다른 파일)은
                                        # 실제 표기가 달라도 이 값으로 통일해 항상 같은 가짜값이 나오게 한다.

    # ---------- 값 변환기 ----------
    def company(self, v):
        m = LEGAL_PRE.match(v)
        pre = m.group(0) if m else ''
        rest = v[len(pre):]
        m = LEGAL_SUF.search(rest)
        suf = m.group(0) if m else ''
        core = rest[:len(rest) - len(suf)]
        if not core.strip():
            return v
        lead = core[:len(core) - len(core.lstrip())]
        trail = core[len(core.rstrip()):]
        fake = self.s.get('company', core.strip(), lambda rng, real: G.company_core(rng))
        return pre + lead + fake + trail + suf

    def person(self, v):
        if '(주)' in v or '（주）' in v or '주식회사' in v:      # 대표자명 열에 회사명이 들어온 경우
            return self.company(v)
        return re.sub(r'\S+', lambda m: self.s.get('person', m.group(0), lambda rng, real: G.person(rng)), v)

    def biz(self, v):
        d = re.sub(r'\D', '', v)
        if len(d) != 10:
            return v
        fake = self.s.get('biz', d, lambda rng, real: G.biz_digits(rng))
        return f'{fake[:3]}-{fake[3:5]}-{fake[5:]}' if '-' in v else fake

    def email(self, v):
        return self.s.get('email', v.strip().lower(), lambda rng, real: G.email(rng))

    def approval(self, v):
        return self.s.get('approval', v, lambda rng, real: F.approval(rng, real))

    def address(self, v):
        key, cands, sido = G.region_info(v)
        R.register(self.s, key, cands, sido)
        return self.s.get('address', v, lambda rng, real, key=key: G.address(rng, real, R.entry(self.s, key)))

    def scrub(self, v):
        """자유 서술 텍스트: 이미 등록된 실명·회사명·지역명·번호를 치환하고 계좌·전화·ID형 숫자열을 형식 보존 치환."""
        return self.free_re.sub(self._free_cb, v)

    def _free_cb(self, m):
        t = m.group(0)
        kind = m.lastgroup
        if kind == 'reg':
            return self.pair_lookup.get(t.lower(), t)
        if kind == 'email':
            return self.email(t)
        if kind == 'acct' and DATE_RE.fullmatch(t):
            return t
        if kind == 'id':
            return self.s.get('token', t, lambda rng, real: G.token_like(rng, real))
        return self.s.get('digits', t, lambda rng, real: G.digits_like(rng, real))

    def item(self, v):
        nums = LONGNUM.findall(v)
        skel = LONGNUM.sub('#', v)
        rep = self.items.get(skel)
        if rep is None:
            if not self.s.collecting:
                self.unseen_items += 1
            rep = self.s.get('item', skel, F.item_generic)
        it = iter(nums)
        return re.sub('#', lambda m: self.s.get('digits', next(it, ''), G.digits_like), rep) if nums else rep

    def build_registry(self):
        """materialize 이후 호출: 자유 서술에서 치환할 (실제→가짜) 문자열 표를 만든다."""
        maps, pairs = self.s.maps, {}
        for kind in ('company', 'person'):
            pairs.update({r: f for r, f in maps.get(kind, {}).items() if len(r) >= 2})
        for d, f in maps.get('biz', {}).items():
            pairs[d] = f
            pairs[f'{d[:3]}-{d[3:5]}-{d[5:]}'] = f'{f[:3]}-{f[3:5]}-{f[5:]}'
        for r, f in maps.get('email', {}).items():
            pairs[r] = f
            if len(r.split('@')[0]) >= 4:
                pairs[r.split('@')[0]] = f.split('@')[0]
        for r, f in maps.get('regiontok', {}).items():
            pairs[r] = f
            if r[-1] in '시군구' and len(r) >= 3 and not r.endswith('광역시'):
                pairs[r[:-1]] = f[:-1]
        pairs.update(maps.get('address', {}))
        pairs = {k: v for k, v in pairs.items() if len(k) >= 2}
        self.pair_lookup = {k.lower(): v for k, v in pairs.items()}
        reg = '(?P<reg>' + '|'.join(re.escape(k) for k in sorted(pairs, key=len, reverse=True)) + ')|' if pairs else ''
        self.free_re = re.compile(FREE_RE.format(reg=reg), re.I)

    # ---------- 시트 처리 ----------
    @staticmethod
    def check_headers(sheet):
        for k, (name, _) in TEXT_RULES.items():
            if str(sheet.cell_value(HEADER_ROW, k)).strip() != name:
                raise ValueError(f'열 {k} 헤더 불일치: 기대 "{name}"')
        for k, name in {**AMOUNT_COLS, **KEEP_COLS}.items():
            if str(sheet.cell_value(HEADER_ROW, k)).strip() != name:
                raise ValueError(f'열 {k} 헤더 불일치: 기대 "{name}"')

    def run(self, sheet, ws=None, stats=None):
        """ws가 None이면 수집 단계(값 변환 없이 실제값만 note), 아니면 실제 마스킹."""
        collect = ws is None
        self.check_headers(sheet)
        factor = None if collect else self.s.amount_factor()
        changed = Counter()
        if not collect:      # 병합 헤더 셀은 xlutils 복사 시 비워지므로 머리글 영역을 다시 기록
            for r in range(HEADER_ROW + 1):
                for k in range(sheet.ncols):
                    c = sheet.cell(r, k)
                    if c.ctype == 1 and c.value.strip():
                        set_cell(ws, r, k, c.value)
        tot_new, tot_old = [0, 0, 0], [0, 0, 0]
        for r in range(DATA_START_ROW, sheet.nrows):
            for k, (_, rule) in TEXT_RULES.items():
                c = sheet.cell(r, k)
                if c.ctype != 1 or not c.value.strip():
                    continue
                if stats is not None:
                    stats.setdefault(k, set()).add(c.value)
                real = c.value
                if k in RECEIVER_IDENTITY_COLS:
                    real = self.receiver_canonical.setdefault(k, real)
                new = getattr(self, rule)(real)
                if not collect and new != c.value:
                    set_cell(ws, r, k, new)
                    changed[k] += 1
            if not collect:
                self._amounts(sheet, ws, r, factor, tot_new, tot_old, changed)
        self._top_block(sheet, ws, tot_new, tot_old, changed)
        return changed

    def _num(self, sheet, r, k):
        c = sheet.cell(r, k)
        return c.value if c.ctype == 2 else None

    def _amounts(self, sheet, ws, r, k, tot_new, tot_old, changed):
        h, s, t, si, ti = (self._num(sheet, r, c) for c in (14, 15, 16, 30, 31))
        new = {}
        if s is not None:
            new[15] = scale_amount(s, k)
            if t is not None:
                new[16] = tax_of(new[15], s, t)
            if h is not None:
                new[14] = new[15] + new.get(16, 0) if h == s + (t or 0) else scale_amount(h, k)
            if si is not None:
                new[30] = new[15] if si == s else scale_amount(si, k)
            if ti is not None:
                new[31] = new.get(16, 0) if ti == t else tax_of(new.get(30, new[15]), si or s, ti)
        for col, val in new.items():
            set_cell(ws, r, col, float(val))
            changed[col] += 1
        for i, (col, old) in enumerate(((14, h), (15, s), (16, t))):
            tot_old[i] += old or 0
            tot_new[i] += new.get(col, old or 0)
        c = sheet.cell(r, 29)                       # 품목단가: '108,000' 형태의 문자열
        if c.ctype == 1 and re.fullmatch(r'[\d,]+', c.value.strip() or 'x'):
            set_cell(ws, r, 29, f"{scale_amount(int(c.value.replace(',', '')), k):,}")
            changed[29] += 1

    def _top_block(self, sheet, ws, tot_new, tot_old, changed):
        labels = {'사업자등록번호': 'biz', '상호': 'company', '대표자명': 'person'}
        totals = {'총합계금액': 0, '총공급가액': 1, '총세액': 2}
        for r in range(DATA_START_ROW - 2):
            for k in range(sheet.ncols - 1):
                c = sheet.cell(r, k)
                if c.ctype != 1:
                    continue
                label = c.value.replace(' ', '')
                v = sheet.cell(r, k + 1)
                if label in labels and v.ctype == 1 and v.value.strip():
                    new = getattr(self, labels[label])(v.value)
                    if ws is not None and new != v.value:
                        set_cell(ws, r, k + 1, new)
                        changed['top'] += 1
                elif label in totals and v.ctype == 1 and ws is not None:
                    i = totals[label]
                    if int(v.value.replace(',', '') or 0) != tot_old[i]:
                        self.top_mismatch += 1
                    set_cell(ws, r, k + 1, f'{tot_new[i]:,}')
                    changed['top'] += 1


def open_for_edit(path):
    book = xlrd.open_workbook(str(path), formatting_info=True)
    return book, book.sheet_by_index(0)


def load_item_dict(secrets_dir):
    p = secrets_dir / 'item_dictionary.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def mask_file(masker, src, dst):
    book, sheet = open_for_edit(src)
    wb = xl_copy(book)
    wb.owner = ''                # 파일 속성의 마지막 저장자(PC 계정명 등)가 남지 않도록 비움 (일부 문자열은 xlrd가 읽지 못해 빈 값 사용)
    changed = masker.run(sheet, wb.get_sheet(0))
    wb.save(str(dst))
    return changed
