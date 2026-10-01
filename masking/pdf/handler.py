"""PDF 처리기: run_masking.py가 확장자(.pdf)로 선택해 쓰는 공통 인터페이스 구현."""
import json

import pymupdf

from ..core import config
from .mask_pdf import PdfMasker
from .rules import RULES
from .scan import scan_pdf, verify_structure


def load_merchant_dict(secrets_dir):
    p = secrets_dir / 'merchant_dictionary.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


class Handler:
    extension = '.pdf'
    category = 'pdf'

    def __init__(self, store, secrets_dir=None):
        self.merchant_dict = load_merchant_dict(secrets_dir or config.SECRETS_DIR)
        self.masker = PdfMasker(store, self.merchant_dict)

    def collect(self, path):
        with pymupdf.open(str(path)) as doc:
            self.masker.collect(doc)

    def prepare(self):
        pass

    def mask(self, src, dst):
        return self.masker.mask(src, dst)

    def scan(self, path, tokens):
        return scan_pdf(path, tokens)

    def verify(self, src, dst):
        return verify_structure(src, dst)

    def extra_tokens(self):
        return [k for k, v in self.merchant_dict.items() if k != v and '#' not in k]

    def describe(self):
        st = self.masker.stats
        return [f'  PDF 행 {st["rows"]}개, 고유 가맹점 {len(st["merchants"])}개, 고유 카드 {len(st["cards"])}개',
                f'  처리 열(index): {dict(RULES)}']

    def summary(self):
        m = self.masker
        return (f'PDF: 가맹점 사전 미등록 {len(m.unseen)}건 / 요약 합계 불일치 {m.total_mismatch}건 / 요약 건수 불일치 {m.count_mismatch}건')
