"""Upstage Document Digitization(OCR) API 엔진. 호출하면 이미지 파일이 Upstage 서버로 전송된다.

API 키는 `.env`의 `UPSTAGE_API_KEY`에서 실행 시점에만 읽으며, 이 모듈은 키 값을 로그나 예외 메시지에
절대 포함하지 않는다. 이 모듈은 아직 실제 호출로 응답 스키마를 확인하지 못했다(개발 환경의 외부 전송
차단 정책 때문). 처음 실행할 때 `--debug-dump`로 원본 응답을 `masking/secrets/`에 저장해 두면,
스키마가 다를 경우 `_extract_words`만 고치면 된다.
"""
import os
from pathlib import Path

from .ocr_common import Line

ENDPOINT = 'https://api.upstage.ai/v1/document-digitization'
_DOTENV_LOADED = False


def _load_key():
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / '.env')
        except ImportError:
            pass
        _DOTENV_LOADED = True
    key = os.environ.get('UPSTAGE_API_KEY')
    if not key:
        raise RuntimeError('.env에 UPSTAGE_API_KEY가 없음(값이 비어 있거나 로드되지 않음)')
    return key


def _extract_words(payload):
    """응답 JSON에서 (text, vertices[4 x (x,y)]) 목록을 뽑는다. 스키마가 다르면 여기만 고치면 된다."""
    pages = payload.get('pages') or [payload]
    out = []
    for page in pages:
        for w in page.get('words') or page.get('items') or []:
            text = w.get('text', '')
            box = w.get('boundingBox') or w.get('bounding_box') or {}
            verts = box.get('vertices') or box.get('normalizedVertices') or []
            if text.strip() and verts:
                out.append((text, [(v.get('x', 0), v.get('y', 0)) for v in verts], w.get('confidence', 1.0)))
    return out


def get_lines(path, debug_dump_path=None):
    """이미지 경로 -> Line 목록. 이 함수를 호출하면 해당 이미지가 Upstage 서버로 전송된다."""
    import requests
    key = _load_key()
    with open(path, 'rb') as f:
        resp = requests.post(ENDPOINT, headers={'Authorization': f'Bearer {key}'},
                             files={'document': f}, data={'model': 'ocr'}, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if debug_dump_path:                                     # 원본 응답 구조 확인용(개인정보 포함 가능하니 secrets/ 등 보호된 경로에만 저장)
        import json
        Path(debug_dump_path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    words = _extract_words(payload)
    if not words:
        raise RuntimeError('Upstage 응답에서 단어를 찾지 못함: 응답 스키마가 예상과 다를 수 있음 '
                            '(get_lines에 debug_dump_path를 넘겨 원본 응답을 확인할 것)')
    out = []
    for text, verts, conf in words:
        xs, ys = [v[0] for v in verts], [v[1] for v in verts]
        out.append(Line(text, float(conf), float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))))
    return out
