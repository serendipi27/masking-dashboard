"""더미 텍스트에 쓸 전체 한글 폰트 로드. 원본 PDF의 폰트는 일부 글자만 담은 부분 폰트라 새 글자를 쓸 수 없다.

탐색 순서: masking/fonts/ 안의 ttf·otf(파일명에 Bold 포함 여부로 구분) → macOS 시스템 폰트(Apple SD Gothic Neo).
"""
import io
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / 'fonts'   # masking/fonts (core/fonts.py is one level under masking/)
SYSTEM_TTC = Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')
_cache = {}


def load_font_bytes(bold=False):
    if bold in _cache:
        return _cache[bold]
    for p in sorted(FONT_DIR.glob('*')):
        if p.suffix.lower() in ('.ttf', '.otf') and (('bold' in p.stem.lower()) == bold):
            _cache[bold] = p.read_bytes()
            return _cache[bold]
    if SYSTEM_TTC.exists():
        from fontTools.ttLib import TTCollection
        want = 'AppleSDGothicNeo-Bold' if bold else 'AppleSDGothicNeo-Regular'
        for f in TTCollection(str(SYSTEM_TTC)).fonts:
            if f['name'].getDebugName(6) == want:
                buf = io.BytesIO()
                f.save(buf)
                _cache[bold] = buf.getvalue()
                return _cache[bold]
    raise FileNotFoundError('한글 폰트를 찾을 수 없음: masking/fonts/ 에 Noto Sans KR 등 ttf(Regular, Bold)를 넣을 것')
