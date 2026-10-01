"""JPG 처리기: run_masking.py가 확장자(.jpg/.jpeg)로 선택해 쓰는 공통 인터페이스 구현.

OCR 엔진은 환경변수 MASKING_JPG_ENGINE으로 고른다('local' 기본값, 'upstage' 선택).
'upstage'를 고르면 이미지가 Upstage 서버로 전송된다 — 로컬 우선 원칙에 따라 기본값은 아니다.
"""
import os

from . import ocr_local
from .mask_jpg import JpgMasker
from .scan import scan_jpg, verify_structure


def _engine_fn():
    engine = os.environ.get('MASKING_JPG_ENGINE', 'local')
    if engine == 'local':
        return ocr_local.get_lines, engine
    if engine == 'upstage':
        from . import ocr_upstage
        return ocr_upstage.get_lines, engine
    raise ValueError(f"알 수 없는 MASKING_JPG_ENGINE={engine!r} (local 또는 upstage)")


class Handler:
    extension = '.jpg'
    category = 'jpg'

    def __init__(self, store, secrets_dir=None):
        get_lines, self.engine = _engine_fn()
        self.masker = JpgMasker(store, get_lines)
        self.engine_fn = get_lines

    def collect(self, path):
        self.masker.collect(path)

    def prepare(self):
        pass

    def mask(self, src, dst):
        return self.masker.mask(src, dst)

    def scan(self, path, tokens):
        return scan_jpg(path, tokens)

    def verify(self, src, dst):
        return verify_structure(src, dst)

    def extra_tokens(self):
        return []

    def describe(self):
        st = self.masker.stats
        return [f'  JPG 엔진={self.engine}  이미지 {st["images"]}개, 찾은 필드 {st["fields_found"]}개']

    def summary(self):
        return f'JPG(엔진={self.engine}): 이미지 {self.masker.stats["images"]}개 처리'
