"""JPG 유출 스캔과 구조 검증. 결과에는 위치와 종류만 담고 실제값은 절대 출력하지 않는다.

유출 스캔은 마스킹에 쓴 엔진과 무관하게 항상 로컬 OCR로 한다. 이미 더미 값으로 바뀐 이미지를
다시 검사하는 단계라 외부로 보낼 이유가 없고, 검증 비용(속도·API 비용)도 아낄 수 있다.
"""
import re

from PIL import Image, ImageChops

from . import ocr_local
from .mask_jpg import check_template, locate_fields
from .rules import FIELDS


def _norm(s):
    return re.sub(r'[\s ]+', '', s)


def scan_jpg(path, tokens):
    lines = ocr_local.get_lines(str(path))
    blob = _norm(' '.join(l.text for l in lines)).lower()
    hits = [('ocr-text', kind) for kind, t in tokens if len(_norm(t)) >= 2 and _norm(t).lower() in blob]
    im = Image.open(path)
    if im.getexif():
        hits.append(('exif', 'metadata'))
    return sorted(set(hits))


def verify_structure(orig_path, new_path):
    """양식 확인, 필드별 값 변화, 금액 관계, 변경 영역 밖 픽셀 차이를 검사."""
    problems = []
    im_o, im_n = Image.open(orig_path).convert('RGB'), Image.open(new_path).convert('RGB')
    if im_o.size != im_n.size:
        return [f'이미지 크기 변경 {im_o.size} -> {im_n.size}']
    W, H = im_n.size
    try:
        lines = ocr_local.get_lines(str(new_path))
        check_template(lines, W, H)
    except ValueError as e:
        return [f'마스킹 결과 양식 확인 실패: {e}']
    # loose=True: 마스킹 후 재-OCR 단계라, 렌더링 폰트 차이로 값 줄이 인접 줄과 붙어도(중심이 박스
    # 밖으로 나가도) 값 자체는 찾은 것으로 인정함(mask_jpg.locate_fields 참고).
    fields = locate_fields(lines, W, H, loose=True)
    boxes = []
    for fid in FIELDS:
        f = fields.get(fid)
        if f is None:
            problems.append(f'{fid} 값을 찾지 못함(마스킹 후)')
            continue
        boxes.append(f['box'])
    amt = {}
    for fid in ('amt_health', 'amt_ltc', 'amt_sub', 'amt_pension', 'amt_employ', 'amt_accident', 'amt_total', 'amt_due'):
        f = fields.get(fid)
        if f:
            amt[fid] = int(re.sub(r'[^\d]', '', f['text']) or 0)
    if len(amt) == 8:
        if amt['amt_health'] + amt['amt_ltc'] != amt['amt_sub']:
            problems.append('건강+장기요양 != 소계')
        if amt['amt_sub'] + amt['amt_pension'] + amt['amt_employ'] + amt['amt_accident'] != amt['amt_total']:
            problems.append('소계+연금+고용+산재 != 보험료합계')
        if amt['amt_total'] != amt['amt_due']:
            problems.append('보험료합계 != 납부할금액')
    # 변경 영역(+여백) 밖 픽셀이 원본과 거의 같은지(JPEG 재압축 오차는 허용)
    diff = ImageChops.difference(im_o, im_n)
    mask = Image.new('L', (W, H), 255)
    from PIL import ImageDraw
    d = ImageDraw.Draw(mask)
    for x0, y0, x1, y1 in boxes:
        d.rectangle((x0 - 3, y0 - 3, x1 + 3, y1 + 3), fill=0)
    diff_out = list(ImageChops.multiply(diff.convert('L'), mask).getdata())
    bad = sum(1 for v in diff_out if v > 30)
    if bad > W * H * 0.001:
        problems.append(f'변경 영역 밖 픽셀 차이 {bad}개(허용 {int(W * H * 0.001)}개)')
    return problems
