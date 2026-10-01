import pandas as pd
import streamlit as st
from PIL import Image

from masking.core.config import masked_name
from masking.jpg.rules import FIELDS

from . import _common

# 항목 이름은 새로 짓지 않고 엔진의 실제 필드 id(rules.py의 FIELDS)를 그대로 씀(밑줄만 공백으로 풀어 표시).
FIELD_LABELS = {fid: fid.replace("_", " ") for fid in FIELDS}

ENGINE_OPTIONS = {"로컬(RapidOCR)": "local", "Upstage OCR API": "upstage"}


def _describe(path):
    size_bytes = path.stat().st_size
    try:
        with Image.open(path) as img:
            width, height = img.size
            return {
                "파일명": path.name,
                "크기(KB)": round(size_bytes / 1024, 1),
                "가로x세로": f"{width}x{height}",
                "포맷": img.format or "-",
            }
    except Exception as e:
        return {
            "파일명": path.name,
            "크기(KB)": round(size_bytes / 1024, 1),
            "가로x세로": "읽기 실패",
            "포맷": str(e),
        }


def render(project_root):
    orig_data_dir = project_root / "orig_data"
    masked_data_dir = project_root / "masked_data"
    secrets_dir = project_root / "masking_secrets"

    st.title("Image Masking")
    st.caption("4대보험 고지서 등 이미지 마스킹")
    st.caption("현재 마스킹 엔진은 JPG(JPEG)만 지원함(PNG 등 다른 이미지 형식은 지원하지 않음).")

    st.subheader("OCR 엔진 선택")
    st.caption(
        "이미지는 텍스트 레이어가 없어 OCR로 글자를 읽어야 함. **로컬**은 이미지가 PC 밖으로 나가지 않지만 "
        "느림(첫 장은 모델 로딩 때문에 ~28초, 이후 장당 5~6초). **Upstage**는 빠르지만(장당 ~1.5초) 이미지가 "
        "외부 서버로 전송됨(`.env`의 `UPSTAGE_API_KEY` 필요). 정확도는 둘 다 동일하며, 매번 명시적으로 "
        "선택해야 함(기본값으로 조용히 고르지 않음)."
    )
    engine_label = st.radio("OCR 엔진", list(ENGINE_OPTIONS.keys()), index=None,
                            key="image_ocr_engine_choice", label_visibility="collapsed")
    jpg_engine = ENGINE_OPTIONS.get(engine_label)
    if jpg_engine is None:
        st.warning("OCR 엔진을 선택해야 아래 인식·마스킹 단계를 진행할 수 있음.")

    st.subheader("1. 원본 이미지 인식")
    st.caption(f"`{orig_data_dir}`에서 jpg·jpeg 파일을 찾음.")
    files = sorted(orig_data_dir.glob("*.jpg")) + sorted(orig_data_dir.glob("*.jpeg"))

    st.subheader("2. 인식된 이미지 메타데이터")
    if not files:
        st.info("이 프로젝트의 orig_data 폴더에 이미지 파일이 없음.")
        return
    st.dataframe(pd.DataFrame(_describe(p) for p in files), use_container_width=True)

    st.subheader("3. 원본 이미지 미리보기")
    st.caption("마스킹 전 원본을 그대로 확인함(아직 마스킹 전이라 실제 값 그대로 보임).")
    file_names = [p.name for p in files]
    sel_name = st.selectbox("미리볼 파일", file_names, key="image_preview_file")
    sel_path = next(p for p in files if p.name == sel_name)
    st.image(str(sel_path), use_container_width=True)

    if jpg_engine is None:
        return   # 엔진을 고르기 전에는 아래(실제 OCR이 필요한) 단계로 진행하지 않음

    _common.preview_expander(
        "image_preview", orig_data_dir, masked_data_dir, secrets_dir, {".jpg", ".jpeg"},
        caption=(
            "실제로 파일을 만들지 않고, 엔진이 이 이미지들을 어떻게 인식했는지만 확인함(국민건강보험공단 "
            "4대보험 고지서 고정 양식을 전제로 하며, 다른 양식이면 처리가 중단됨). 이 단계에서 "
            "`masking_secrets` 폴더가 만들어질 수 있음(비밀 키 생성은 최초 1회만 일어남)."
        ),
        jpg_engine=jpg_engine,
    )

    st.subheader("4. 마스킹 실행")
    st.caption(
        f"실제로 마스킹해 `{masked_data_dir / 'jpg'}`에 저장함(폴더가 없으면 새로 만들고, 이미 있으면 "
        "그대로 사용함). 유출 스캔·구조 검증을 통과한 파일만 저장되고, 걸린 파일은 저장하지 않고 "
        "아래 \"검토 필요\"에만 표시됨."
    )
    _common.run_button(
        "image_run_result", orig_data_dir, masked_data_dir, secrets_dir, {".jpg", ".jpeg"},
        jpg_engine=jpg_engine,
        spinner_text="마스킹 실행 중... (로컬 엔진은 첫 장에서 모델 로딩으로 오래 걸릴 수 있음)",
    )

    result = _common.render_results(
        "image_run_result", masked_data_dir, secrets_dir,
        saved_where=f"`{masked_data_dir / 'jpg'}`", key_prefix="image",
    )
    _common.render_detail_section(result, FIELD_LABELS)

    if result and result.ok:
        st.subheader("7. 마스킹 전후 비교")
        st.caption("저장된 이미지 중 하나를 골라 원본과 마스킹 결과를 나란히 확인함.")
        saved_names = [fr.path.name for fr in result.ok]
        cmp_name = st.selectbox("비교할 파일", saved_names, key="image_compare_file")
        cmp_fr = next(fr for fr in result.ok if fr.path.name == cmp_name)
        col_before, col_after = st.columns(2)
        with col_before:
            st.caption("원본")
            st.image(str(cmp_fr.path), use_container_width=True)
        with col_after:
            st.caption("마스킹 결과")
            masked_path = masked_data_dir / cmp_fr.category / masked_name(cmp_fr.path.name)
            st.image(str(masked_path), use_container_width=True)
