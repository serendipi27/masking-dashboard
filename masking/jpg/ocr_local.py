"""로컬 OCR 엔진(RapidOCR). 이미지가 이 PC 밖으로 나가지 않는다.

원본 크기(1배)와 2배 확대본을 각각 읽어 합친다. 작은 글자(승인번호·금액)는 확대했을 때 더 잘 읽히고,
라벨처럼 큰 글자는 1배로도 충분히 읽혀서, 둘을 합치면 어느 한쪽만 쓸 때보다 값 재현율이 높다(자체 시험 기준).
"""
from .ocr_common import Line, dedup

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        import tempfile
        from pathlib import Path

        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        # 기본값은 모델을 패키지 설치 폴더(site-packages/rapidocr/models) 안에 내려받는데,
        # Streamlit Cloud는 실행 시점에 그 폴더가 쓰기 금지라 Permission denied가 남. 쓰기 가능한
        # 임시 폴더로 옮김(컨테이너가 살아있는 동안은 재사용되어 매 세션 다시 받지 않음).
        model_dir = Path(tempfile.gettempdir()) / 'rapidocr_models'
        _engine = RapidOCR(params={'Rec.lang_type': LangRec.KOREAN, 'Rec.ocr_version': OCRVersion.PPOCRV5,
                                   'Rec.model_type': ModelType.MOBILE,
                                   'Global.model_root_dir': model_dir})
    return _engine


def _read(path, scale):
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert('RGB')
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    r = _get_engine()(np.array(im)[:, :, ::-1])
    if not r.txts:
        return []
    out = []
    for t, s, b in zip(r.txts, r.scores, r.boxes):
        xs, ys = [q[0] / scale for q in b], [q[1] / scale for q in b]
        out.append(Line(t, float(s), float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))))
    return out


def get_lines(path):
    """이미지 경로 -> Line 목록(1배+2배 합침, 중복 제거)."""
    return dedup(_read(path, 1) + _read(path, 2))
