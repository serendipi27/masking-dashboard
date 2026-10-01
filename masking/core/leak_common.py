"""유출 검사 공통 부분: 매핑표에서 검사할 토큰을 만든다. (형식별 스캔은 각 형식 폴더에 있다)
결과에는 위치와 종류만 담고 실제값은 절대 출력하지 않는다."""
import re


def collect_tokens(store, extra=()):
    """매핑표의 실제값에서 검사할 토큰 목록 [(kind, token)]을 만든다."""
    toks = set()
    for kind, m in store.maps.items():
        if kind in ('region', 'item'):
            pass
        for real in m:
            if kind == 'biz':
                toks |= {(kind, real), (kind, f'{real[:3]}-{real[3:5]}-{real[5:]}')}
            elif kind == 'email':
                toks.add((kind, real))
                if len(real.split('@')[0]) >= 4:
                    toks.add((kind, real.split('@')[0]))
            elif kind == 'card':
                toks |= {(kind, real), (kind, real[:9]), (kind, '****-' + real[-4:])}
            elif kind == 'holder':
                toks |= {(kind, real), (kind, real[real.find(')') + 1:])}
            elif kind == 'merchant':
                if len(real) >= 4 and m[real] != real:
                    toks.add((kind, real))
            elif kind == 'approval':
                toks |= {(kind, p) for p in real.split('-')[1:] if len(p) >= 6}
            elif kind == 'person' and len(real) >= 2:
                # 사람 이름은 한글 특성상 원래 짧아(2~3자) 여기만 예외로 낮은 기준을 유지함(올리면
                # 실제 이름 유출을 못 잡게 됨).
                toks.add((kind, real))
            elif kind in ('company', 'address', 'regiontok', 'digits', 'token', 'region') and len(real) >= 4:
                # 짧은(2~3자) 한글 단어·숫자는 무관한 문서에 우연히 겹치는 오탐이 매우 잦아(예:
                # merchant/company 이름의 일부가 다른 파일의 고정 문구와 겹친 사례를 실제로 겪음),
                # 이 종류들은 최소 길이를 4자로 올려 우연한 겹침 자체를 줄인다.
                toks.add((kind, real))
    for t in extra:
        if '#' not in t and len(t) >= 2:
            toks.add(('item', t))
    return toks


def digits(s):
    return re.sub(r'\D', '', s)
