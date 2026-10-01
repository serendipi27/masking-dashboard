"""XLS 처리기: run_masking.py가 확장자(.xls)로 선택해 쓰는 공통 인터페이스 구현.

인터페이스: collect(path) → prepare() → mask(src, dst) → scan(path, tokens) / verify(src, dst), describe(), summary(), extra_tokens()
"""
from ..core import config
from . import rules
from .mask_xls import XlsMasker, load_item_dict, mask_file, open_for_edit
from .scan import scan_xls, verify_structure


class Handler:
    extension = '.xls'
    category = 'xls'

    def __init__(self, store, secrets_dir=None):
        self.item_dict = load_item_dict(secrets_dir or config.SECRETS_DIR)
        self.masker = XlsMasker(store, self.item_dict)
        self.stats = {}

    def collect(self, path):
        """수집 단계: 값은 바꾸지 않고 실제값만 매핑 저장소에 모은다."""
        _, sheet = open_for_edit(path)
        self.masker.run(sheet, None, self.stats)

    def prepare(self):
        """가짜값 생성(materialize) 이후, 자유 서술 치환표를 만든다."""
        self.masker.build_registry()

    def mask(self, src, dst):
        return mask_file(self.masker, src, dst)

    def scan(self, path, tokens):
        return scan_xls(path, tokens)

    def verify(self, src, dst):
        return verify_structure(src, dst)

    def extra_tokens(self):
        return [k for k, v in self.item_dict.items() if k != v]     # 그대로 두는 일반 용어는 유출 검사에서 제외

    def describe(self):
        return [f'  열{k:>2} {name:<14} 규칙={rule:<8} 고유값 {len(self.stats.get(k, ()))}개'
                for k, (name, rule) in rules.TEXT_RULES.items()]

    def summary(self):
        return f'XLS: 품목명 대체 생성 {self.masker.unseen_items}건 / 상단 합계와 행 합계 불일치 {self.masker.top_mismatch}건'
