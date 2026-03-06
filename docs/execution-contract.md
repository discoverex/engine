# 외부 스케줄러/워커 실행 계약

이 저장소는 실행 엔진 패키지입니다. 스케줄러/큐/워커 오케스트레이션은 외부 저장소에서 담당합니다.

## 계약 범위
- 스케줄러는 오케스트레이터 JobSpec의 `inputs`로 실행 payload를 전달합니다.
- 워커는 작업 1건당 CLI 프로세스 1개를 실행합니다.
- 워커는 내부 설정 스키마를 알 필요가 없습니다.
- 워커는 엔진 런처(`discoverex-orch-launcher`)를 통해 payload를 검증한 뒤 실행합니다.

## 안정 인터페이스
- 엔트리포인트: `discoverex`
- 명령: `gen-verify`, `verify-only`, `replay-eval`

## 워커 초기화 요구사항
```bash
mkdir -p .cache/uv
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking --extra storage
```

`uv`가 없으면 런처가 `python -m venv` + `pip install -e .[tracking,storage]`로 자동 폴백합니다.

## 오케스트레이터 JobSpec 매핑
오케스트레이터가 전달하는 `job_spec_json`에서 엔진 실행에 사용하는 필드는 `inputs`입니다.

- `job_spec.engine`: 오케스트레이터 라우팅용 식별자(엔진 내부 실행 파라미터로는 사용하지 않음)
- `job_spec.entrypoint`: 워커가 실행할 런처 엔트리포인트
- `job_spec.inputs`: 엔진 실행 payload SSOT (`OrchestratorInputsV1`)

권장 `entrypoint`:

```json
["/bin/sh", "-lc", "python -m discoverex.orchestrator_contract.launcher"]
```

실제 잡 등록 스크립트(엔진 레포):

```bash
python scripts/register_orchestrator_job.py \
  --prefect-api-url https://prefect-api.example.com/api \
  --deployment engine-run \
  --command gen-verify \
  --repo-url https://github.com/<org>/discoverex-engine.git \
  --ref main \
  --background-asset-ref bg://dummy \
  -o adapters/artifact_store=minio \
  -o adapters/tracker=mlflow_server \
  --runtime-env MLFLOW_TRACKING_URI=https://mlflow.example.com
```

## inputs(OrchestratorInputsV1) 페이로드 예시
```json
{
  "contract_version": "v1",
  "command": "gen-verify",
  "args": {
    "background_asset_ref": "bg://dummy"
  },
  "overrides": [
    "runtime/model_runtime=gpu",
    "models/perception=hf",
    "runtime.model_runtime.device=cuda:0"
  ],
  "runtime": {
    "mode": "worker",
    "bootstrap_mode": "auto",
    "extras": ["tracking", "storage"],
    "extra_env": {
      "MLFLOW_TRACKING_URI": "https://mlflow.example.com"
    }
  }
}
```

## 워커 실행 규칙
- 워커는 무상태(stateless) 실행만 담당합니다.
- 작업 1건은 프로세스 1회 실행에 매핑합니다.
- override는 전달 순서를 유지해 `-o` 인자로 전달합니다.
- `ORCH_JOB_INPUTS_JSON`은 Pydantic(`OrchestratorInputsV1`)으로 강검증합니다.
- 엔진 실행 후 delivery 후처리 단계를 별도로 호출합니다.
- 워커에서는 로컬 저장소 사용을 피하고 adapter override를 명시적으로 강제합니다.

예시:
```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex gen-verify \
  --background-asset-ref bg://dummy \
  -o runtime/model_runtime=gpu \
  -o models/perception=hf \
  -o runtime.model_runtime.device=cuda:0
```

권장 워커 override 최소 세트:
- `adapters/artifact_store=minio`
- `adapters/tracker=mlflow_server`
- 필요 시 `adapters/metadata_store=postgres`

세부 운영 방식은 `docs/runtime-mode-guide.md`를 기준으로 합니다.

## 워커 출력 계약
- `exit_code`: 프로세스 종료 코드
- `stdout` / `stderr`: 원본 출력
- `artifacts`: 명령 출력으로부터 파싱한 산출물 경로

CLI 출력 키:
- `gen-verify`, `verify-only`: `scene_json` 포함 JSON
- `replay-eval`: `report` 포함 JSON

## delivery 후처리 계약 (숨은그림찾기)
엔진 산출 `scene.json`을 delivery 변환기로 변환해 번들을 만듭니다.

```bash
python -m delivery.spot_the_hidden.cli --scene-json <scene_json_path>
```

출력 파일:
- `<scene_dir>/delivery/spot_hidden_bundle.json`

번들 정책:
- 단일 JSON 안에 `playable` + `answer_key`를 함께 포함
- 프런트 응답에서는 `answer_key`를 제거한 payload만 노출
- 이미지 데이터는 인라인이 아니라 `playable.image_ref` 참조로 전달

## 호환성 정책
- 명령 이름은 안정적으로 유지합니다.
- 기존 override 키는 하위 호환을 유지합니다.
- 파괴적 설정 키 변경 시 `contract_version`을 올립니다.
