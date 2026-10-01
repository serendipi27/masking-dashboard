"""OCR 엔진 공통 자료형. 로컬 엔진과 Upstage 엔진이 같은 형태의 결과를 내도록 맞춘다."""
from dataclasses import dataclass


@dataclass
class Line:
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


def iou(a, b):
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area = lambda l: max(0.0, l.x1 - l.x0) * max(0.0, l.y1 - l.y0)
    denom = area(a) + area(b) - inter
    return inter / denom if denom else 0.0


def dedup(lines, thresh=0.5):
    """겹치는 중복 검출(예: 여러 배율로 읽은 결과를 합칠 때)을 신뢰도 높은 것 위주로 정리."""
    out = []
    for l in sorted(lines, key=lambda l: -l.conf):
        if not any(iou(l, k) > thresh for k in out):
            out.append(l)
    return out
