"""PDF 전용 더미 생성기(카드번호, 카드소지자, 가맹점명 대체)."""
import re

from ..core import generators as G

# 가맹점 사전에 없는 이름의 업종 추정용 키워드 -> 대체 이름 끝말
CATEGORY = [
    ('주유소', '주유소'), ('마트', '마트'), ('약국', '약국'), (r'가정의학과|의원|병원|치과|한의원', '의원'),
    ('철물', '철물'), (r'리조트|호텔|펜션|모텔', '리조트'), ('택시', '택시'), ('수산', '수산'), ('횟집', '횟집'),
    (r'정육|수육', '정육식당'), (r'식당|한식|뷔페|국밥|포차|불바베큐|게장|마솥|팥죽|치킨|닭|고기|주방', '식당'),
    (r'농협|수협|축협|조합', '농협'), (r'스포|골프|헬스', '스포츠센터'), (r'카페|커피', '카페'),
]
PUBLIC_WORDS = ('요금', '세입금', '우체국', '코스콤', '교통', '스마트로')   # 공공·요금·결제망 항목은 이름을 유지하고 지역명만 치환


def card_number(rng, real=None):
    """`dddd-dddd-****-dddd` 형식 유지."""
    return f'{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-****-{rng.randint(1000, 9999)}'


def holder(rng, real, store):
    """`(지)한*주` 같은 부분 마스킹 이름. 성·끝 글자가 XLS의 실제 인물과 하나로 맞으면 그 인물의 가명을 따른다."""
    m = re.fullmatch(r'(\([^)]*\))?([가-힣])\*([가-힣])', real)
    if not m:
        n = G.person(rng)
        return n[0] + '*' + n[2]
    names = set(store.maps.get('person', {})) | set(store.noted.get('person', {}))
    cand = [n for n in names if len(n) == 3 and n[0] == m.group(2) and n[2] == m.group(3)]
    fake = store.get('person', cand[0], lambda r, real: G.person(r)) if len(cand) == 1 else G.person(rng)
    return f'{m.group(1) or ""}{fake[0]}*{fake[2]}'


def merchant_fallback(rng, skel):
    """사전에 없는 가맹점: 공공·요금 항목이면 이름 유지, 아니면 업종 키워드를 유지한 가짜 상호."""
    if any(w in skel for w in PUBLIC_WORDS):
        return skel
    for pat, end in CATEGORY:
        if re.search(pat, skel):
            return rng.choice(G.CO_A) + end
    return rng.choice(G.CO_A) + '상점'
