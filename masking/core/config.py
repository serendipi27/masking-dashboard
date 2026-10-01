"""형식과 무관한 공통 설정. 다른 프로젝트로 옮길 때는 환경변수로 경로를 바꿀 수 있다."""
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]                                   # masking/
ROOT = Path(os.environ.get('MASKING_ROOT', PKG_DIR.parent))                     # 프로젝트 루트(orig_data, masked_data가 있는 곳)
ORIG_DIR = ROOT / 'orig_data'
MASKED_DIR = ROOT / 'masked_data'
SECRETS_DIR = Path(os.environ.get('MASKING_SECRETS', PKG_DIR / 'secrets'))      # key.txt, mapping.json, 치환 사전 (AI 읽기 차단)

MASKED_PREFIX = 'masked_'     # 모든 형식(xls·pdf·jpg)의 마스킹 결과 파일명 접두사
AMOUNT_RANGE = (0.6, 1.4)     # 금액 비밀 배율 범위 (실제 배율은 비밀 키에서 결정)


def masked_name(name):
    """원본 파일명 -> 마스킹 결과 파일명. 모든 마스킹 코드가 이 함수를 공통으로 사용한다."""
    return name if name.startswith(MASKED_PREFIX) else MASKED_PREFIX + name
