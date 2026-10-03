import pandas as pd
import pymupdf
import streamlit as st

from masking.pdf.rules import EXPECTED_HEADER, RULES

from . import _common

FIELD_LABELS = {idx: EXPECTED_HEADER[idx] for idx in RULES}   # 열 index -> 원본 표 열 이름(엔진의 실제 이름을 그대로 씀)


def _describe(path):
    size_bytes = path.stat().st_size
    try:
        with pymupdf.open(str(path)) as doc:
            meta = doc.metadata or {}
            return {
                "파일명": path.name,
                "크기(KB)": round(size_bytes / 1024, 1),
                "페이지 수": doc.page_count,
                "암호화": "예" if doc.is_encrypted else "아니오",
                "생성 프로그램": meta.get("producer") or "-",
            }
    except Exception as e:
        return {
            "파일명": path.name,
            "크기(KB)": round(size_bytes / 1024, 1),
            "페이지 수": "읽기 실패",
            "암호화": "-",
            "생성 프로그램": str(e),
        }


def render():
    st.title("PDF Masking")
    st.caption("법인카드 이용내역 PDF 마스킹")

    st.subheader("1. 파일 업로드")
    dirs = _common.upload_section("pdf", {".pdf"}, "원본 PDF 파일 업로드 (여러 개 가능)")
    if dirs is None:
        return
    orig_data_dir, masked_data_dir, secrets_dir = dirs

    st.subheader("2. 업로드된 PDF 인식")
    pdfs = sorted(orig_data_dir.glob("*.pdf"))

    st.subheader("3. 인식된 PDF 메타데이터")
    if not pdfs:
        st.info("업로드된 파일 중 PDF 파일이 없음.")
        return
    st.dataframe(pd.DataFrame(_describe(p) for p in pdfs), use_container_width=True)

    st.subheader("4. 원본 PDF 미리보기")
    st.caption("마스킹 전 원본 내용을 페이지 단위로 직접 확인함(아직 마스킹 전이라 실제 값 그대로 보임).")

    file_names = [p.name for p in pdfs]
    sel_name = st.selectbox("미리볼 파일", file_names, key="pdf_preview_file")
    sel_path = next(p for p in pdfs if p.name == sel_name)

    with pymupdf.open(str(sel_path)) as doc:
        n_pages = doc.page_count
        page_key = f"pdf_preview_page_{sel_name}"
        cur = max(0, min(st.session_state.get(page_key, 0), n_pages - 1))

        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 이전 페이지", disabled=cur == 0, use_container_width=True):
                st.session_state[page_key] = cur - 1
                st.rerun()
        with col_info:
            st.markdown(f"<div style='text-align:center'>페이지 {cur + 1} / {n_pages}</div>",
                       unsafe_allow_html=True)
        with col_next:
            if st.button("다음 페이지 ▶", disabled=cur == n_pages - 1, use_container_width=True):
                st.session_state[page_key] = cur + 1
                st.rerun()

        pix = doc[cur].get_pixmap(dpi=150)
        st.image(pix.tobytes("png"), use_container_width=True)

    _common.preview_expander(
        "pdf_preview", orig_data_dir, masked_data_dir, secrets_dir, {".pdf"},
        caption=(
            "실제로 파일을 만들지 않고, 엔진이 이 PDF들을 어떻게 인식했는지만 확인함(법인카드 전체 이용내역 "
            "표 형식을 전제로 하며, 다른 양식이면 여기서 이상하게 보이거나 나중에 \"검토 필요\"로 걸릴 수 있음). "
            "이 단계에서 `masking_secrets` 폴더가 만들어질 수 있음(비밀 키 생성은 최초 1회만 일어남)."
        ),
    )

    st.subheader("5. 마스킹 실행")
    st.caption(
        f"실제로 마스킹해 `{masked_data_dir / 'pdf'}`에 저장함(폴더가 없으면 새로 만들고, 이미 있으면 "
        "그대로 사용함). 유출 스캔·구조 검증을 통과한 파일만 저장되고, 걸린 파일은 저장하지 않고 "
        "아래 \"검토 필요\"에만 표시됨."
    )
    _common.run_button("pdf_run_result", orig_data_dir, masked_data_dir, secrets_dir, {".pdf"})

    result = _common.render_results(
        "pdf_run_result", masked_data_dir, secrets_dir,
        saved_where=f"`{masked_data_dir / 'pdf'}`", key_prefix="pdf",
    )
    _common.render_detail_section(result, FIELD_LABELS)

    if result is not None:
        st.subheader("8. 결과 다운로드")
        _common.download_buttons(masked_data_dir, secrets_dir, key_prefix="pdf")
