"""Excel/PDF/Image Masking 세 페이지가 공유하는 화면 부품.

형식별로 다른 부분(원본 인식·미리보기·항목 이름)은 각 페이지에 그대로 두고, 형식과 무관하게
똑같이 반복되는 부분(진행 표시·결과 표시·"그래도 저장" 흐름)만 여기 모은다.
"""
import pandas as pd
import streamlit as st

from masking.run_masking import accept_flagged, run_pipeline


def file_result_row(fr, extra=None):
    """"5. 결과" 표의 한 행. extra를 주면 "파일명" 바로 뒤에 그 열들을 끼워 넣는다(Excel의 "형식" 등)."""
    row = {"파일명": fr.path.name}
    if extra:
        row.update(extra)
    row["변경 건수"] = sum(fr.changed.values())
    row["유출 스캔"] = len(fr.leaks)
    row["구조 검증"] = len(fr.problems)
    row["상태"] = "저장됨" if fr.ok else "검토 필요"
    return row


def detail_row(fr, field_labels, extra=None):
    """"6. 마스킹 세부내용" 표의 한 행. field_labels: {fr.changed의 키: 표시 이름}(열 index 또는 필드 id)."""
    row = {"파일명": fr.path.name}
    if extra:
        row.update(extra)
    total = 0
    for key, label in field_labels.items():
        n = fr.changed.get(key, 0)
        row[label] = n
        total += n
    row["합계"] = total
    return row


def preview_expander(session_key, orig_data_dir, masked_data_dir, secrets_dir, extensions, caption,
                     jpg_engine=None):
    """"엔진 인식 결과 요약(고급)" 펼치기: dry_run으로 describe()만 확인하고 파일은 만들지 않는다."""
    with st.expander("🔍 엔진 인식 결과 요약(고급)"):
        st.caption(caption)
        if st.button("🔍 인식 결과 요약 보기", key=f"{session_key}_btn"):
            kwargs = dict(dry_run=True, extensions=extensions)
            if jpg_engine is not None:
                kwargs["jpg_engine"] = jpg_engine
            with st.spinner("분석하는 중..."):
                try:
                    st.session_state[session_key] = run_pipeline(orig_data_dir, masked_data_dir, secrets_dir, **kwargs)
                except Exception as e:
                    st.error(f"분석 실패: {e}")

        preview = st.session_state.get(session_key)
        if preview is not None:
            if preview.files_found:
                for lines in preview.describe.values():
                    for line in lines:
                        st.text(line)
            else:
                st.warning("미리보기에서 인식된 파일이 없음.")


def run_button(session_key, orig_data_dir, masked_data_dir, secrets_dir, extensions,
               row_fn=file_result_row, jpg_engine=None, spinner_text="마스킹 실행 중..."):
    """"4. 마스킹 실행" 버튼 + 진행 표 실시간 갱신 + 실제 실행. 결과는 session_state[session_key]에 저장한다."""
    if st.button("▶ 마스킹 실행", type="primary", key=f"{session_key}_btn"):
        progress_area = st.empty()
        rows = []

        def on_progress(event, payload):
            if event == "file_done":
                rows.append(row_fn(payload))
                progress_area.dataframe(pd.DataFrame(rows), use_container_width=True)

        kwargs = dict(dry_run=False, extensions=extensions, progress=on_progress)
        if jpg_engine is not None:
            kwargs["jpg_engine"] = jpg_engine
        with st.spinner(spinner_text):
            try:
                st.session_state[session_key] = run_pipeline(orig_data_dir, masked_data_dir, secrets_dir, **kwargs)
            except Exception as e:
                st.error(f"실행 실패: {e}")


def render_results(session_key, masked_data_dir, secrets_dir, saved_where, row_fn=file_result_row,
                   key_prefix=""):
    """"5. 결과" 섹션: 저장됨/검토 필요 분리 표시 + "그래도 저장" 흐름. session_state의 PipelineResult를
    반환(없으면 None) — 호출한 페이지가 이어서 "6. 마스킹 세부내용"을 그릴 때 씀."""
    result = st.session_state.get(session_key)
    if result is None:
        return None

    st.subheader("5. 결과")

    if result.ok:
        st.success(f"저장됨: {len(result.ok)}건 → {saved_where}")
        st.dataframe(pd.DataFrame(row_fn(fr) for fr in result.ok), use_container_width=True)

    if result.flagged:
        st.warning(f"검토 필요(저장 안 됨): {len(result.flagged)}건")
        for fr in result.flagged:
            with st.expander(f"⚠️ {fr.path.name}"):
                st.write(f"유출 스캔: {len(fr.leaks)}건 — {fr.leaks[:10]}")
                st.write(f"구조 검증: {len(fr.problems)}건 — {fr.problems[:10]}")
                confirm_key = f"{key_prefix}_flag_confirm_{fr.path.name}"
                confirmed = st.checkbox("위 내용을 확인했고, 그래도 저장하겠음", key=confirm_key)
                if st.button("✅ 그래도 저장", key=f"{key_prefix}_flag_save_{fr.path.name}", disabled=not confirmed):
                    dst = accept_flagged(fr, masked_data_dir, secrets_dir)
                    result.flagged.remove(fr)
                    result.ok.append(fr)
                    st.success(f"저장함: `{dst}`")
                    st.rerun()

    if not result.ok and not result.flagged:
        st.info("처리할 파일이 없음.")

    return result


def render_detail_section(result, field_labels, extra_fn=None):
    """"6. 마스킹 세부내용" 섹션. result가 없거나 저장된 파일이 없으면 아무것도 안 그린다."""
    if not result or not result.ok:
        return
    st.subheader("6. 마스킹 세부내용")
    st.caption("저장된 파일에서 실제로 어떤 항목을 몇 건 바꿨는지 보여줌(항목 이름은 엔진의 실제 이름을 그대로 씀).")
    rows = [detail_row(fr, field_labels, extra=(extra_fn(fr) if extra_fn else None)) for fr in result.ok]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
