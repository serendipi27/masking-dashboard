"""이 패키지의 어느 모듈을 import하든 한 번만 실행됨(Python의 패키지 import 규칙).

masking/은 프로젝트 루트 아래 dashboard/의 형제 폴더라, 상대 import를 쓰는 masking 패키지를
불러오려면 프로젝트 루트가 sys.path에 있어야 한다. 여기서 한 번만 등록해두면 project.py를 뺀
나머지 페이지(excel/pdf/image.py)와 _common.py가 각자 따로 등록할 필요가 없다.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
