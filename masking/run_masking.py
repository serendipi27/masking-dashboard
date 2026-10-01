"""실행 (이 파일이 있는 폴더의 부모 디렉터리에서, 즉 `python -m masking.run_masking` 형태로):

    python -m masking.run_masking --input <프로젝트>/orig_data --output <프로젝트>/masked_data \\
        --secrets-dir <프로젝트>/masking_secrets [--dry-run] [--jpg-engine local|upstage]

여러 프로젝트가 이 스크립트 하나를 공유하므로 `--input`·`--output`·`--secrets-dir`는 항상 그 프로젝트를
직접 가리켜야 한다(기본값 없음). 특히 `--secrets-dir`를 다른 프로젝트와 같은 경로로 쓰면 서로 다른
회사·개인의 실제값이 하나의 매핑표에 섞이므로 절대 공유하지 말 것.

원본 파일을 확장자별 처리기로 마스킹해 <output>/<형식>/ 에 `masked_<원본명>`으로 저장한다.
형식별 하위 폴더(xls/xlsx/pdf/jpg)는 각 처리기의 category 값을 따른다.
임시 폴더에 쓴 뒤 유출 스캔·구조 검증을 통과한 파일만 확정한다. 판정은 파일 단위로 독립적이라
한 파일에서 의심 사례가 나와도 다른 파일은 정상 저장된다. 걸린 파일은 저장하지 않고 이유만 보고한다.
출력에는 열 번호·건수·위치만 표시하고 실제값은 표시하지 않는다.

`run_pipeline()`은 이 CLI와 Streamlit 대시보드가 함께 쓰는 핵심 함수다. `progress` 콜백을 넘기면
단계마다 호출되어(파일별 진행 상황 등) UI에서 실시간으로 보여줄 수 있다. CLI는 이 함수를 감싸
텍스트로 출력만 할 뿐, 마스킹·검증·저장 로직 자체는 여기 한 곳에만 있다.
"""
import argparse
import importlib
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .core import config
from .core.leak_common import collect_tokens
from .core.mapping_store import MappingStore

# 확장자 -> 처리기 모듈. 필요한 형식의 모듈만 불러오므로 다른 형식의 라이브러리는 설치하지 않아도 된다.
HANDLER_MODULES = {'.xls': 'masking.xls', '.xlsx': 'masking.xlsx', '.pdf': 'masking.pdf',
                   '.jpg': 'masking.jpg', '.jpeg': 'masking.jpg'}


@dataclass
class FileResult:
    path: Path
    category: str
    changed: dict
    leaks: list
    problems: list

    @property
    def ok(self):
        return not (self.leaks or self.problems)


@dataclass
class PipelineResult:
    files_found: int
    describe: dict            # {category: [설명 줄, ...]}
    ok: list = field(default_factory=list)          # list[FileResult] 저장됨
    flagged: list = field(default_factory=list)      # list[FileResult] 검토 필요(저장 안 함)
    summaries: dict = field(default_factory=dict)    # {category: 요약 문자열}
    output_dir: Path = None
    counts: dict = field(default_factory=dict)       # {category: 저장된 개수}


def find_files(input_dir, extensions=None):
    """extensions(예: {'.xls', '.xlsx'})를 주면 그 확장자만 찾는다. 기본은 지원하는 모든 확장자."""
    exts = extensions or HANDLER_MODULES.keys()
    return sorted(f for f in Path(input_dir).iterdir()
                  if f.suffix.lower() in exts and not f.name.startswith(config.MASKED_PREFIX))


def run_pipeline(input_dir, output_dir, secrets_dir, jpg_engine='local', dry_run=False, progress=None,
                 extensions=None):
    """마스킹 전체 흐름. progress(event, payload)가 있으면 단계마다 호출한다(이벤트: 'collect_start',
    'described', 'file_done', 'summaries', 'done'). extensions를 주면 그 확장자만 처리한다
    (예: Excel 페이지에서 같은 폴더에 PDF가 섞여 있어도 건드리지 않음). 반환값은 PipelineResult."""
    def emit(event, payload=None):
        if progress:
            progress(event, payload)

    input_dir, output_dir, secrets_dir = Path(input_dir), Path(output_dir), Path(secrets_dir)
    os.environ['MASKING_JPG_ENGINE'] = jpg_engine
    config.SECRETS_DIR = secrets_dir

    files = find_files(input_dir, extensions)
    if not files:
        return PipelineResult(files_found=0, describe={})
    emit('collect_start', {'n': len(files)})

    store = MappingStore(config.SECRETS_DIR, config.AMOUNT_RANGE)
    handlers = {}
    for ext in sorted({f.suffix.lower() for f in files}):
        handlers[ext] = importlib.import_module(HANDLER_MODULES[ext]).Handler(store, config.SECRETS_DIR)

    store.collecting = True                         # 1) 수집: 실제값을 먼저 모아 가짜값과 겹치지 않게 함
    for f in files:
        handlers[f.suffix.lower()].collect(f)
    store.materialize()
    for h in handlers.values():
        h.prepare()

    describe = {h.category: h.describe() for h in handlers.values()}
    emit('described', describe)
    result = PipelineResult(files_found=len(files), describe=describe, output_dir=output_dir)
    if dry_run:
        return result

    tmp = Path(tempfile.mkdtemp(prefix='masking_'))     # 2) 마스킹: 임시 폴더에 저장 후 검증(파일별 독립 판정)
    tokens = collect_tokens(store, extra=[t for h in handlers.values() for t in h.extra_tokens()])
    try:
        for f in files:
            h = handlers[f.suffix.lower()]
            out_dir = tmp / h.category
            out_dir.mkdir(exist_ok=True)
            out = out_dir / config.masked_name(f.name)
            changed = h.mask(f, out)
            leaks = h.scan(out, tokens)
            problems = h.verify(f, out)
            fr = FileResult(f, h.category, dict(changed), leaks, problems)
            (result.ok if fr.ok else result.flagged).append(fr)
            emit('file_done', fr)
        result.summaries = {cat: h.summary() for cat, h in ((h.category, h) for h in handlers.values())}
        emit('summaries', result.summaries)

        output_dir.mkdir(parents=True, exist_ok=True)
        for fr in result.ok:
            dst_dir = output_dir / fr.category
            dst_dir.mkdir(parents=True, exist_ok=True)
            if dst_dir.resolve() != input_dir.resolve():   # 접두사 도입 전 결과물(원본과 같은 이름)이 남아 있으면 삭제
                (dst_dir / fr.path.name).unlink(missing_ok=True)
            shutil.move(str(tmp / fr.category / config.masked_name(fr.path.name)),
                       dst_dir / config.masked_name(fr.path.name))
            result.counts[fr.category] = result.counts.get(fr.category, 0) + 1
        if result.ok:
            store.save()       # 확정 저장한 파일이 하나라도 있을 때만 매핑표를 갱신(걸린 파일 때문에 상태가 어긋나지 않도록)
        emit('done', result)
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def accept_flagged(fr, output_dir, secrets_dir):
    """검토 필요 파일을 사람이 확인한 뒤 그래도 저장하고 싶을 때 호출(대시보드의 '그래도 저장' 버튼용).
    유출 스캔·구조 검증 결과를 다시 보여주지는 않으며, 호출자가 이미 그 내용을 검토했다고 전제한다."""
    ext = fr.path.suffix.lower()
    config.SECRETS_DIR = Path(secrets_dir)
    store = MappingStore(config.SECRETS_DIR, config.AMOUNT_RANGE)
    h = importlib.import_module(HANDLER_MODULES[ext]).Handler(store, config.SECRETS_DIR)
    dst_dir = Path(output_dir) / fr.category
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / config.masked_name(fr.path.name)
    h.mask(fr.path, dst)
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='열별 분류·건수만 출력하고 파일은 만들지 않음')
    ap.add_argument('--input', type=Path, required=True, help='원본 파일이 있는 폴더(프로젝트의 orig_data 등)')
    ap.add_argument('--output', type=Path, required=True, help='결과를 저장할 masked_data 폴더')
    ap.add_argument('--secrets-dir', type=Path, required=True,
                    help='이 프로젝트 전용 비밀 폴더(매핑표·키). 다른 프로젝트와 절대 공유하지 말 것')
    ap.add_argument('--jpg-engine', choices=['local', 'upstage'], default='local')
    a = ap.parse_args(argv)

    def progress(event, payload):
        if event == 'collect_start':
            print(f"[수집] 파일 {payload['n']}개")
        elif event == 'described':
            for lines in payload.values():
                print('\n'.join(lines))
        elif event == 'file_done':
            fr = payload
            print(f'[{fr.category}/{config.masked_name(fr.path.name)}] 변경 {sum(fr.changed.values())}개 '
                 f'(항목별 {dict(sorted(fr.changed.items(), key=str))})')
            print(f'  유출 스캔: {len(fr.leaks)}건 {fr.leaks[:10]}')
            print(f'  구조 검증: {len(fr.problems)}건 {fr.problems[:10]}')
        elif event == 'summaries':
            for s in payload.values():
                print(s)

    result = run_pipeline(a.input, a.output, a.secrets_dir, jpg_engine=a.jpg_engine, dry_run=a.dry_run,
                          progress=progress)
    if result.files_found == 0:
        print('처리할 파일이 없음')
        return 1
    if a.dry_run:
        return 0
    print(f'완료: {a.output} 에 형식별로 저장함 '
         f'({", ".join(f"{k} {v}개" for k, v in sorted(result.counts.items())) or "없음"})')
    if result.flagged:
        print(f'검토 필요(저장 안 함): {[(fr.path.name, fr.category) for fr in result.flagged]}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
