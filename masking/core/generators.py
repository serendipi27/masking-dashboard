"""더미 데이터 생성기. 모든 함수는 (rng, real) 형태로 호출되며 rng는 매핑 저장소가 시드를 고정해 넘겨준다."""
import re

CO_A = ['가온', '한빛', '새솔', '다온', '누리', '미래', '이룸', '하늘', '푸른', '세광',
        '대성', '동원', '태평', '아름', '우리', '청운', '서린', '도담', '해든', '온새미']
CO_B = ['테크', '시스템', '산업', '건설', '상사', '솔루션', '물산', '엔지니어링', '개발', '기술', '전자', '서비스']

SURNAMES = list('김이박최정강조윤장임한오서신권황안송전홍')
GIVEN_1 = list('민서지현도준예하수시유재태승은')
GIVEN_2 = list('준우윤아진영호원린빈성희현민서')

MAIL_WORDS = ['mail', 'info', 'biz', 'tax', 'office', 'contact', 'sales', 'admin']

# 실제 지역으로 치환하기 위한 풀 (도로명·번지는 임의 값)
REGION_POOL = [
    dict(sido='충청북도', abbr='충북', city='청주시', gu='흥덕구', dongs=['복대동', '가경동', '봉명동'], roads=['직지대로', '가경로', '풍산로']),
    dict(sido='전북특별자치도', abbr='전북', city='전주시', gu='덕진구', dongs=['금암동', '송천동', '진북동'], roads=['백제대로', '기린대로', '천마산로']),
    dict(sido='강원특별자치도', abbr='강원', city='원주시', gu='', dongs=['단계동', '무실동', '반곡동'], roads=['원주천로', '치악로', '서원대로']),
    dict(sido='경상북도', abbr='경북', city='구미시', gu='', dongs=['원평동', '송정동', '형곡동'], roads=['금오대로', '구미대로', '송정로']),
    dict(sido='충청남도', abbr='충남', city='천안시', gu='서북구', dongs=['불당동', '쌍용동', '성정동'], roads=['불당대로', '서부대로', '쌍용대로']),
    dict(sido='광주광역시', abbr='광주', city='북구', gu='', dongs=['운암동', '용봉동', '두암동'], roads=['무등로', '설죽로', '하서로']),
    dict(sido='대전광역시', abbr='대전', city='유성구', gu='', dongs=['봉명동', '도룡동', '전민동'], roads=['대학로', '유성대로', '엑스포로']),
    dict(sido='울산광역시', abbr='울산', city='남구', gu='', dongs=['삼산동', '달동', '옥동'], roads=['삼산로', '문수로', '왕생로']),
    dict(sido='제주특별자치도', abbr='제주', city='제주시', gu='', dongs=['노형동', '연동', '아라동'], roads=['노형로', '연삼로', '중앙로']),
    dict(sido='강원특별자치도', abbr='강원', city='춘천시', gu='', dongs=['석사동', '효자동', '퇴계동'], roads=['남춘로', '공지로', '방동길']),
    dict(sido='경상북도', abbr='경북', city='안동시', gu='', dongs=['옥동', '정하동', '태화동'], roads=['퇴계로', '강남로', '경동로']),
    dict(sido='충청북도', abbr='충북', city='충주시', gu='', dongs=['연수동', '칠금동', '금릉동'], roads=['충원대로', '국원대로', '탑평로']),
    dict(sido='전북특별자치도', abbr='전북', city='군산시', gu='', dongs=['수송동', '나운동', '조촌동'], roads=['수송로', '나운로', '조촌로']),
    dict(sido='충청남도', abbr='충남', city='아산시', gu='', dongs=['배방읍', '탕정면', '모종동'], roads=['배방로', '탕정로', '모산로']),
    dict(sido='강원특별자치도', abbr='강원', city='강릉시', gu='', dongs=['교동', '포남동', '옥천동'], roads=['경강로', '율곡로', '강릉대로']),
    dict(sido='경상북도', abbr='경북', city='포항시', gu='북구', dongs=['장량동', '두호동', '우창동'], roads=['새천년대로', '장량로', '삼호로']),
]
REGION_BY_CITY = {e['city']: e for e in REGION_POOL}
_SIDO_SUFFIX = re.compile(r'(도|광역시|특별시|특별자치시)$')


def company_core(rng, real=None):
    return rng.choice(CO_A) + rng.choice(CO_B)


def person(rng, real=None):
    return rng.choice(SURNAMES) + rng.choice(GIVEN_1) + rng.choice(GIVEN_2)


def email(rng, real=None):
    return f'{rng.choice(MAIL_WORDS)}{rng.randint(10, 99)}{rng.choice(MAIL_WORDS)}@example.com'


def digits_like(rng, real):
    """자릿수·구분자 형식을 보존한 숫자열 (첫 자리가 0이면 0 유지, 예: 전화번호)."""
    out, first = [], True
    for ch in real:
        if ch.isdigit():
            out.append('0' if first and ch == '0' else str(rng.randint(1 if first else 0, 9)))
            first = False
        else:
            out.append(ch)
    return ''.join(out)


def token_like(rng, real):
    """숫자→숫자, 대문자→대문자, 소문자→소문자로 문자 종류를 보존."""
    out = []
    for ch in real:
        if ch.isdigit():
            out.append(str(rng.randint(0, 9)))
        elif 'a' <= ch <= 'z':
            out.append(rng.choice('abcdefghijklmnopqrstuvwxyz'))
        elif 'A' <= ch <= 'Z':
            out.append(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        else:
            out.append(ch)
    return ''.join(out)


def biz_digits(rng, real=None):
    """검증 숫자가 맞는 가짜 사업자등록번호(10자리, 법인 중간번호 81~88)."""
    d = [rng.randint(1, 8), rng.randint(0, 9), rng.randint(0, 9), rng.randint(8, 8), rng.randint(1, 8)]
    d += [rng.randint(0, 9) for _ in range(4)]
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    s = sum(a * b for a, b in zip(d, w)) + (d[8] * 5) // 10
    d.append((10 - s % 10) % 10)
    return ''.join(map(str, d))


def is_valid_biz(digits):
    if len(digits) != 10 or not digits.isdigit():
        return False
    d = list(map(int, digits))
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    s = sum(a * b for a, b in zip(d[:9], w)) + (d[8] * 5) // 10
    return (10 - s % 10) % 10 == d[9]


def pick_region(rng, real=None):
    return rng.choice(REGION_POOL)['city']


def region_info(addr):
    """주소에서 (지역 키, 시·군·구 후보 토큰들, 시도 토큰)을 추출."""
    tokens = [t for t in re.split(r'[\s,()]+', addr.strip()) if t]
    head = tokens[:5]
    sido = head[0] if head and (len(head[0]) == 2 or _SIDO_SUFFIX.search(head[0])) else ''
    cands = [t for t in head if re.fullmatch(r'[가-힣]{2,}(?:시|군|구)', t)
             and not re.search(r'(광역시|특별시|특별자치시)$', t)]
    key = next((t for t in cands if t[-1] in '시군'), None) or next((t for t in cands if t.endswith('구')), None) \
        or sido or addr.strip()
    return key, cands, sido


def region_token_fake(token, entry):
    if token.endswith('구'):
        return entry['gu'] or entry['city']
    if token.endswith(('시', '군')) and not re.search(r'(광역시|특별시|특별자치시)$', token):
        return entry['city']
    return entry['abbr'] if len(token) == 2 else entry['sido']


def address(rng, real, entry):
    """실제 지역(entry)으로 바꾼 주소. 도로명/지번 형태, 괄호(동), 층, 번지 표기를 원본과 맞춘다."""
    if not real.strip():
        return real
    first = real.split()[0]
    sido = entry['abbr'] if len(first) == 2 else entry['sido']
    place = entry['city'] + (' ' + entry['gu'] if entry['gu'] else '')
    dong = rng.choice(entry['dongs'])
    floor = re.search(r'(\d+)층', real)
    if re.search(r'(로|길)\s?\d+', real):
        out = f"{sido} {place} {rng.choice(entry['roads'])} {rng.randint(1, 199)}"
        if re.search(r'\([^)]*\)', real):
            out += f'({dong})'
        if floor:
            out += f', {floor.group(1)}층'
        return out
    out = f'{sido} {place} {dong} {rng.randint(1, 999)}'
    return out + ('번지' if '번지' in real else '')
