"""XLS 전용 더미 생성기(승인번호, 품목명 대체)."""
from ..core.generators import token_like

ITEM_POOL = ['소프트웨어 유지보수 용역', '사무용품 구입', '소모품비', '임대료', '통신요금', '전력요금', '수도요금',
             '시설관리비', '운반비', '자재 구입', '공사대금', '컨설팅 용역', '교육훈련비', '광고선전비', '차량유지비']


def approval(rng, real):
    """`YYYYMMDD-8자리-8자` 형식: 날짜 부분은 유지하고 나머지는 문자 종류를 보존한 무작위."""
    head, *rest = real.split('-')
    return '-'.join([head] + [token_like(rng, p) for p in rest])


def item_generic(rng, real=None):
    return rng.choice(ITEM_POOL)
