import shutil

import streamlit as st

from sections import excel, image, pdf

st.set_page_config(page_title="마스킹 대시보드", layout="wide")

TASK_PAGES = {
    "Excel Masking": excel.render,
    "PDF Masking": pdf.render,
    "Image Masking": image.render,
}

st.session_state.setdefault("active_page", next(iter(TASK_PAGES)))
gen = st.session_state.get("reset_gen", 0)   # 초기화 버튼을 누르면 바뀜 — 아래 라디오·업로더를 새 위젯으로 만들어
                                              # 브라우저 쪽에 남아 있던 이전 선택/업로드가 다음 rerun에 다시
                                              # 반영되는 것(st.file_uploader에서 겪은 것과 같은 문제)을 막는다.


def _go_to_task():
    st.session_state.active_page = st.session_state[f"task_choice_widget_{gen}"]


st.sidebar.title("마스킹 대시보드")

st.sidebar.subheader("작업 선택")
st.sidebar.radio("작업 선택", list(TASK_PAGES.keys()), label_visibility="collapsed",
                 key=f"task_choice_widget_{gen}", on_change=_go_to_task)

st.sidebar.divider()
if st.sidebar.button("🔄 초기화", use_container_width=True):
    # 무조건 맨 처음 상태로 되돌림 — Excel/PDF/Image 각 형식의 업로드 임시 폴더를 모두 지움
    # (더 이상 하나의 "프로젝트 폴더"를 공유하지 않고 형식별로 독립된 tmp_dir_<형식>을 쓰기 때문)
    for format_key in ("excel", "pdf", "image"):
        tmp_dir = st.session_state.get(f"tmp_dir_{format_key}")
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    st.session_state.clear()
    st.session_state.reset_gen = gen + 1
    st.session_state.active_page = next(iter(TASK_PAGES))
    st.rerun()

TASK_PAGES[st.session_state.active_page]()
