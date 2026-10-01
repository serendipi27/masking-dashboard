import platform
from pathlib import Path

import streamlit as st


def render():
    gen = st.session_state.get("reset_gen", 0)   # 초기화 버튼을 누르면 바뀜 — 아래 입력창을 새 위젯으로 만들어
                                                  # 브라우저에 남아 있던 이전 입력값이 되살아나지 않게 함

    st.title("프로젝트 선택")
    st.caption("마스킹 작업을 진행할 프로젝트 폴더를 지정함. 그 폴더 안의 `orig_data`(원본)·"
               "`masking_secrets`(비밀 폴더)를 자동으로 찾음.")

    with st.expander("\"원본 폴더\"·\"비밀 폴더\"란?"):
        st.markdown(
            "**원본 폴더(`orig_data`)**\n"
            "- 마스킹할 실제 원본 파일(PDF·Excel(xls/xlsx)·이미지(jpg))을 넣어두는 폴더.\n"
            "- 상호명·대표자·사업자번호·계좌번호·카드번호·금액 등 진짜 정보가 그대로 들어 있는 "
            "파일들이라, 마스킹하기 전에는 AI나 외부에 공유하면 안 됨.\n"
            "- 준비 방법: 프로젝트 폴더 바로 아래에 `orig_data`라는 이름으로 폴더를 만들고, "
            "그 안에 원본 파일을 넣으면 됨.\n"
            "- 지원 형식: 홈택스 전자세금계산서 목록(xls/xlsx), 법인카드 전체 이용내역 PDF"
            "(텍스트가 있는 PDF만 — 스캔한 이미지 PDF는 처리 못함), 4대보험 고지서 등 JPG 이미지. "
            "처리기가 기대하는 열 이름·표 양식과 다르면 처리가 중단될 수 있음.\n\n"
            "**비밀 폴더(`masking_secrets`)**\n"
            "- 마스킹 과정에서만 쓰는 이 프로젝트 전용 비밀 정보(가짜값을 만드는 데 쓰는 키, "
            "실제값 ↔ 가짜값 매핑표 등)를 저장하는 폴더.\n"
            "- **미리 만들 필요 없음** — 실제 마스킹을 처음 실행하면 자동으로 만들어짐. "
            "지금 단계(원본 인식·메타데이터 확인)에서는 아예 없어도 됨.\n"
            "- 안에 생기는 `key.txt`(비밀 키)·`mapping.json`(원본 실명·실제값이 그대로 담긴 매핑표) 등은 "
            "매우 민감한 정보라, 커밋하거나 외부에 공유하면 안 되고, 다른 프로젝트와 절대 같은 폴더를 "
            "공유하면 안 됨(서로 다른 회사·개인의 실제값이 한 매핑표에 섞이게 됨). `key.txt`를 잃어버리면 "
            "이전과 다른 가짜값이 생성되니 별도로 안전하게 백업해둘 것."
        )

    example_path = r"C:\Users\xxx\Lectures\(00_working_20260921)Masking_pdf_jpg_excel" \
        if platform.system() == "Windows" else "/Users/xxx/Lectures/(00_working_20260921)Masking_pdf_jpg_excel"
    project_input = st.text_input(
        "프로젝트 폴더 경로",
        placeholder=f"예: {example_path}",
        key=f"project_root_text_{gen}",
    )

    st.session_state.orig_data_dir = None
    st.session_state.project_root = None

    if not project_input:
        st.info("프로젝트 폴더 경로를 입력해줘.")
        return

    project_root = Path(project_input).expanduser()
    if not project_root.is_dir():
        st.error("이 경로에서 폴더를 찾지 못함. 경로를 다시 확인해줘.")
        return

    orig = project_root / "orig_data"
    secrets = project_root / "masking_secrets"

    if not orig.is_dir():
        st.error(
            f"`orig_data` 폴더가 없음. `{project_root}/orig_data` 폴더를 만들고 "
            "그 안에 원본 PDF·Excel(xls/xlsx)·이미지(jpg) 파일을 넣어줘."
        )
        return

    st.session_state.orig_data_dir = orig
    st.session_state.project_root = project_root
    st.success(f"프로젝트: `{project_root.name}`")
    st.caption(f"원본 폴더: `{orig}`")

    if secrets.is_dir():
        st.caption(f"비밀 폴더: `{secrets}` (있음)")
    else:
        st.caption(
            "`masking_secrets` 폴더가 아직 없음(정상). 이 폴더는 실제 마스킹을 처음 실행할 때 "
            "자동으로 만들어지며, 지금 단계(원본 인식·메타데이터 확인)에서는 필요 없음."
        )

    st.info("왼쪽 사이드바의 \"작업 선택\"에서 Excel/PDF/Image 중 하나를 골라 계속 진행할 수 있음.")
