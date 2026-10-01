"""JPG(4대보험 고지서) 마스킹. rules.py의 상대 좌표로 값 칸을 찾아 배경색으로 지우고 더미 텍스트를 그린다."""
import io
import re
from collections import Counter

from PIL import Image, ImageDraw, ImageFont

from ..core import generators as G
from ..core.amounts import scale_amount
from ..core.fonts import load_font_bytes
from .rules import FIELDS, SANITY_LABELS, SANITY_MIN_HITS, SANITY_TOL

DIGITS_RE = re.compile(r'\d')
BANK_ACCOUNT_RE = re.compile(r'^(?P<bank>\D*)(?P<acct>[\d\-]*\d)(?P<suf>\*+)?$')


def _norm(s):
    return re.sub(r'[\s ]+', '', s)


def check_template(lines, W, H):
    """문서가 예상 양식과 맞는지 확인. 부족하면 무엇이 안 맞는지 담아 실패를 알린다."""
    diag = (W ** 2 + H ** 2) ** 0.5
    hits = 0
    for text, (rx, ry) in SANITY_LABELS:
        cx, cy = rx / 755 * W, ry / 1074 * H
        if any(text in l.text.replace(' ', '') and ((l.cx - cx) ** 2 + (l.cy - cy) ** 2) ** 0.5 < SANITY_TOL * diag
               for l in lines):
            hits += 1
    if hits < SANITY_MIN_HITS:
        raise ValueError(f'양식이 예상과 다름(표지 라벨 {hits}/{len(SANITY_LABELS)}개만 확인됨, {SANITY_MIN_HITS}개 이상 필요)')


def locate_fields(lines, W, H, loose=False):
    """각 필드의 상대 좌표 박스 안에 있는 OCR 줄을 모아 (실제 텍스트, 합친 박스)를 만든다.

    loose=True면 회사명·이름·번호류(kind가 'amount'로 시작하지 않는 필드)에 한해, 줄의 중심이 박스
    안에 있는지가 아니라 "박스와 조금이라도 겹치는지"로 판정한다. 렌더링에 쓰는 폰트가 바뀌면(예: 이
    프로젝트가 macOS 시스템 폰트 대신 다른 폰트를 번들해 쓰게 된 경우, Windows 등 다른 환경에서 또
    다른 폰트로 바뀌는 경우도 포함) 같은 글자 크기라도 실제 글자 높이가 미세하게 달라져, 마스킹 후
    재-OCR 시에만 바로 아래·위 줄과 시각적으로 붙어 하나의 OCR 줄로 합쳐지는 경우가 있다. 이때 중심
    좌표 기준으로는 "못 찾음"으로 오판할 수 있어, 검증(재확인) 단계에서만 이 완화된 판정을 쓴다.
    금액 필드는 제외하는데, 금액칸은 서로 촘촘히 붙어 있어 완화하면 오히려 옆 줄의 숫자까지 함께
    읽혀 합계 검증이 깨질 수 있기 때문이다(실제로 겪어서 확인함). 원본에서 실제 값을 추출할 때
    (collect/mask)는 정밀도가 더 중요해 기존의 엄격한(중심 기준) 판정을 그대로 쓴다."""
    out = {}
    for fid, (rel, kind) in FIELDS.items():
        rx0, ry0, rx1, ry1 = rel
        box = (rx0 * W, ry0 * H, rx1 * W, ry1 * H)
        if loose and not kind.startswith('amount'):
            hit = [l for l in lines if l.x0 < box[2] and l.x1 > box[0] and l.y0 < box[3] and l.y1 > box[1]]
        else:
            hit = [l for l in lines if box[0] <= l.cx <= box[2] and box[1] <= l.cy <= box[3]]
        if not hit:
            out[fid] = None
            continue
        hit.sort(key=lambda l: l.x0)
        text = ' '.join(l.text for l in hit).strip()
        ux0, uy0 = min(l.x0 for l in hit), min(l.y0 for l in hit)
        ux1, uy1 = max(l.x1 for l in hit), max(l.y1 for l in hit)
        out[fid] = dict(text=text, kind=kind, box=(ux0, uy0, ux1, uy1))
    return out


class JpgMasker:
    def __init__(self, store, get_lines):
        self.s = store
        self.get_lines = get_lines           # OCR 엔진 함수(로컬 또는 Upstage)
        self.missing = set()
        self.stats = {'images': 0, 'fields_found': 0}

    # ---------- 값 변환기 ----------
    def _company(self, v):
        v = v.strip()
        m = re.match(r'^(\(주\)|（주）|\(유\)|（유）)?\s*(.*?)\s*(대표)?$', v)
        pre, core, suf = m.group(1) or '', m.group(2), m.group(3) or ''
        if not core:
            return v
        fake = self.s.get('company', core, lambda rng, real: G.company_core(rng))
        return f'{pre}{fake}' + (f' {suf}' if suf else '')

    def _digits_id(self, v):
        # OCR이 숫자 사이 공백을 문서마다 다르게 읽을 수 있어(예: "68135209417 01" vs "68135209417  01"),
        # 숫자만 뽑아 키로 써야 같은 실제 번호가 항상 같은 가짜값이 됨. 11자리+2자리 형식(관리·납부자번호)은
        # 표시할 때 공백 한 칸으로 통일해서 문서마다 같은 모양으로 나오게 함.
        digits = DIGITS_RE.findall(v)
        digits = ''.join(digits)
        fake = self.s.get('digits', digits, lambda rng, real: G.digits_like(rng, real))
        return f'{fake[:-2]} {fake[-2:]}' if len(fake) == 13 else fake

    def _bank_account(self, v):
        m = BANK_ACCOUNT_RE.match(v)
        if not m or not m.group('acct'):
            return v
        acct = self.s.get('digits', m.group('acct'), lambda rng, real: G.digits_like(rng, real))
        return f"{m.group('bank')}{acct}{m.group('suf') or ''}"

    def fake_text(self, field):
        kind = field['kind']
        if kind in ('company',):
            return self._company(field['text'])
        if kind == 'person_title':
            return self._company(field['text'])
        if kind == 'digits_id':
            return self._digits_id(field['text'])
        if kind == 'bank_account':
            return self._bank_account(field['text'])
        return None  # amount:* 는 compute_amounts에서 관계식으로 한 번에 계산

    @staticmethod
    def _amount_value(field):
        return int(re.sub(r'[^\d]', '', field['text']) or 0)

    def compute_amounts(self, fields, k):
        """건강+장기요양=소계, 소계+연금+고용+산재=보험료합계=납부할금액 관계를 유지하며 재계산.
        관계가 없는 금액(납기후청구금액, 납부(이체)금액)은 배율만 독립 적용."""
        out = {}
        for fid, f in fields.items():
            if f and f['kind'] == 'amount':
                out[fid] = f'{scale_amount(self._amount_value(f), k):,}'
        health = fields.get('amt_health')
        ltc = fields.get('amt_ltc')
        if health and ltc:
            nh, nl = scale_amount(self._amount_value(health), k), scale_amount(self._amount_value(ltc), k)
            out['amt_health'], out['amt_ltc'] = f'{nh:,}', f'{nl:,}'
            nsub = nh + nl
            out['amt_sub'] = f'{nsub:,}'
            rest = [fields.get(x) for x in ('amt_pension', 'amt_employ', 'amt_accident')]
            if all(rest):
                np_, ne, na = (scale_amount(self._amount_value(x), k) for x in rest)
                out['amt_pension'], out['amt_employ'], out['amt_accident'] = f'{np_:,}', f'{ne:,}', f'{na:,}'
                ntotal = nsub + np_ + ne + na
                out['amt_total'] = out['amt_due'] = f'{ntotal:,}'
        return out

    # ---------- 수집 ----------
    def collect(self, path):
        from PIL import Image as _I
        W, H = _I.open(path).size
        lines = self.get_lines(str(path))
        check_template(lines, W, H)
        fields = locate_fields(lines, W, H)
        missing = [fid for fid, f in fields.items() if f is None]
        if missing:
            raise ValueError(f'값을 찾지 못한 필드 {len(missing)}개: {missing}')
        self.stats['images'] += 1
        self.stats['fields_found'] += len(fields)
        for fid, f in fields.items():
            if f['kind'] != 'amount' and not f['kind'].startswith('amount'):
                self.fake_text(f)   # 매핑 저장소에 실제값을 등록(수집 단계에서는 반환값을 쓰지 않음)
        return fields

    # ---------- 마스킹 ----------
    @staticmethod
    def _bg_color(im, box, pad=2):
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        W, H = im.size
        strip = []
        top = im.crop((max(0, x0), max(0, y0 - pad), min(W, x1), max(0, y0)))
        bot = im.crop((max(0, x0), min(H, y1), min(W, x1), min(H, y1 + pad)))
        for crop in (top, bot):
            if crop.size[0] > 0 and crop.size[1] > 0:
                strip += list(crop.getdata())
        if not strip:
            return (255, 255, 255)
        n = len(strip)
        return tuple(sorted(c[ch] for c in strip)[n // 2] for ch in range(3))

    def mask(self, src, dst):
        im = Image.open(src).convert('RGB')
        W, H = im.size
        lines = self.get_lines(str(src))
        check_template(lines, W, H)
        fields = locate_fields(lines, W, H)
        k = self.s.amount_factor()
        amounts = self.compute_amounts(fields, k)
        draw = ImageDraw.Draw(im)
        reg = ImageFont.truetype(io.BytesIO(load_font_bytes(False)), size=1)   # 크기는 필드마다 다시 지정
        changed = Counter()
        for fid, f in fields.items():
            if f is None:
                continue
            new = amounts.get(fid) if fid in amounts or f['kind'].startswith('amount') else self.fake_text(f)
            if new is None or new == f['text']:
                continue
            box = f['box']
            im.paste(Image.new('RGB', (int(box[2] - box[0]) + 2, int(box[3] - box[1]) + 2), self._bg_color(im, box)),
                     (int(box[0]) - 1, int(box[1]) - 1))
            size = max(9, int((box[3] - box[1]) * 0.78))
            font = reg.font_variant(size=size)
            draw.text((box[0], box[1] - 1), new, font=font, fill=(51, 51, 51))
            changed[fid] += 1
        im.save(str(dst), format='JPEG', quality=92)
        return changed
