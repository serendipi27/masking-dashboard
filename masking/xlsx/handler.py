"""XLSX 처리기: run_masking.py가 확장자(.xlsx)로 선택해 쓰는 공통 인터페이스 구현.

열 구조를 xls(전자세금계산서 목록)와 동일하다고 보고 xls/rules.py의 규칙을 그대로 쓴다.
"""
from ..core import config
from ..xls import rules
from .mask_xlsx import XlsxMasker, load_item_dict, mask_file, open_for_edit
from .scan import scan_xlsx, verify_structure


class Handler:
    extension = '.xlsx'
    category = 'xlsx'

    def __init__(self, store, secrets_dir=None):
        self.item_dict = load_item_dict(secrets_dir or config.SECRETS_DIR)
        self.masker = XlsxMasker(store, self.item_dict)
        self.stats = {}

    def collect(self, path):
        _, ws = open_for_edit(path)
        self.masker.run(ws, edit=False, stats=self.stats)

    def prepare(self):
        self.masker.build_registry()

    def mask(self, src, dst):
        return mask_file(self.masker, src, dst)

    def scan(self, path, tokens):
        return scan_xlsx(path, tokens)

    def verify(self, src, dst):
        return verify_structure(src, dst)

    def extra_tokens(self):
        return [k for k, v in self.item_dict.items() if k != v]

    def describe(self):
        return [f'  열{k:>2} {name:<14} 규칙={rule:<8} 고유값 {len(self.stats.get(k, ()))}개'
                for k, (name, rule) in rules.TEXT_RULES.items()]

    def summary(self):
        return f'XLSX: 품목명 대체 생성 {self.masker.unseen_items}건 / 상단 합계와 행 합계 불일치 {self.masker.top_mismatch}건'
