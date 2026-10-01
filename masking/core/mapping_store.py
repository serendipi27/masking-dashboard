"""실제값 → 가짜값 매핑 저장소. 비밀 키(HMAC)로 결정적 생성하므로 재실행·다른 파일 형식에서도 같은 값이 같은 가짜값이 된다.

사용 순서: collecting=True로 전체 파일을 훑어 실제값을 수집(note) → materialize()로 가짜값 일괄 생성 → 마스킹 단계에서 get()으로 조회.
"""
import hashlib
import hmac
import json
import os
import random
from pathlib import Path

KIND_ORDER = ['region', 'regiontok', 'company', 'person', 'holder', 'card', 'biz', 'email', 'address',
              'approval', 'digits', 'token', 'item', 'merchant']


class MappingStore:
    def __init__(self, secrets_dir, amount_range=(0.6, 1.4)):
        self.dir = Path(secrets_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        key_path = self.dir / 'key.txt'
        if not key_path.exists():
            key_path.write_text(os.urandom(32).hex())
            os.chmod(key_path, 0o600)
        self.key = bytes.fromhex(key_path.read_text().strip())
        self.path = self.dir / 'mapping.json'
        self.maps = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.noted = {}          # kind -> {real: gen}
        self.collecting = False
        self.amount_range = amount_range
        self._avoid = set()      # 가짜값에 포함되면 안 되는 실제 토큰(소문자)

    def _rng(self, kind, real, attempt):
        d = hmac.new(self.key, f'{kind}|{real}|{attempt}'.encode(), hashlib.sha256).digest()
        return random.Random(int.from_bytes(d[:8], 'big'))

    def note(self, kind, real, gen):
        self.noted.setdefault(kind, {})[real] = gen
        if len(real) >= 2:
            self._avoid.add(real.lower())

    def _make(self, kind, real, gen):
        used = set(self.maps.get(kind, {}).values())
        fake = real
        for attempt in range(300):
            fake = gen(self._rng(kind, real, attempt), real)
            low = str(fake).lower()
            if fake != real and fake not in used and not any(t in low for t in self._avoid):
                break
        return fake

    def get(self, kind, real, gen):
        if self.collecting:
            self.note(kind, real, gen)
            return real
        m = self.maps.setdefault(kind, {})
        if real not in m:
            m[real] = self._make(kind, real, gen)
        return m[real]

    def materialize(self):
        """수집된 모든 실제값에 대해 (종류 순서대로, 정렬해서) 가짜값을 생성."""
        self.collecting = False
        for kind in KIND_ORDER:
            for real, gen in sorted(self.noted.get(kind, {}).items()):
                self.get(kind, real, gen)

    def amount_factor(self):
        lo, hi = self.amount_range
        d = hmac.new(self.key, b'amount-factor', hashlib.sha256).digest()
        return lo + (hi - lo) * int.from_bytes(d[:8], 'big') / 2 ** 64

    def save(self):
        self.path.write_text(json.dumps(self.maps, ensure_ascii=False, indent=1), encoding='utf-8')
        os.chmod(self.path, 0o600)
