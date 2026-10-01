import streamlit as st

from sections import excel, image, pdf, project

st.set_page_config(page_title="마스킹 대시보드", layout="wide")

TASK_PAGES = {
    "Excel Masking": excel.render,
    "PDF Masking": pdf.render,
    "Image Masking": image.render,
}

st.session_state.setdefault("active_page", "프로젝트 선택")
gen = st.session_state.get("reset_gen", 0)   # 초기화 버튼을 누르면 바뀜 — 아래 라디오를 새 위젯으로 만들어
                                              # 브라우저 쪽에 남아 있던 이전 선택 상태가 다음 rerun에 다시
                                              # 반영되는 것(요전에 st.file_uploader에서 겪은 것과 같은 문제)을 막는다.


def _go_to_task():
    st.session_state.active_page = st.session_state[f"task_choice_widget_{gen}"]


st.sidebar.title("마스킹 대시보드")

st.sidebar.subheader("프로젝트 선택")
if st.sidebar.button("📁 프로젝트 폴더 지정", use_container_width=True):
    st.session_state.active_page = "프로젝트 선택"

st.sidebar.divider()
st.sidebar.subheader("작업 선택")
st.sidebar.radio("작업 선택", list(TASK_PAGES.keys()), label_visibility="collapsed",
                 key=f"task_choice_widget_{gen}", on_change=_go_to_task)

st.sidebar.divider()
if st.sidebar.button("🔄 초기화", use_container_width=True):
    # 무조건 맨 처음(프로젝트 폴더 지정 전) 상태로 되돌림 — 프로젝트 경로도 예외 없이 지움
    st.session_state.clear()
    st.session_state.reset_gen = gen + 1
    st.session_state.active_page = "프로젝트 선택"
    st.rerun()

if st.session_state.active_page == "프로젝트 선택":
    project.render()
else:
    project_root = st.session_state.get("project_root")
    if project_root and st.session_state.get("orig_data_dir"):
        TASK_PAGES[st.session_state.active_page](project_root)
    else:
        st.info("먼저 사이드바에서 프로젝트 폴더를 선택해줘.")
