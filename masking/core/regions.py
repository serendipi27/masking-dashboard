"""지역명 치환 공통 함수. 같은 실제 지역은 XLS·PDF 어디서나 같은 다른 실제 지역으로 바뀐다."""
from . import generators as G


def entry(store, key):
    """실제 지역 키(예: 시·군 이름)에 대응하는 치환 지역 정보(REGION_POOL 항목)."""
    return G.REGION_BY_CITY[store.get('region', key, G.pick_region)]


def register(store, key, cands, sido=''):
    """지역 키와 그 안의 시·군·구/시도 토큰의 치환값을 매핑 저장소에 등록."""
    store.get('region', key, G.pick_region)
    for t in list(cands) + ([sido] if sido else []):
        store.get('regiontok', t, lambda rng, real, key=key: G.region_token_fake(real, entry(store, key)))


def fake_token(store, token, base=False):
    """`XX시` -> 치환된 지역 토큰. base=True면 `시`·`군`을 뗀 이름(구는 그대로)."""
    if token not in store.maps.get('regiontok', {}):
        register(store, token, [token])
    fake = store.maps['regiontok'][token]
    return fake[:-1] if base and fake[-1] in '시군' else fake
