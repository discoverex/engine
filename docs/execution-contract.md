# 외부 스케줄러/워커 실행 계약

이 저장소는 실행 엔진 패키지입니다. 스케줄러/큐/워커 오케스트레이션은 외부 저장소에서 담당합니다.

## 계약 범위
- 스케줄러는 직렬화 가능한 Hydra override 문자열 목록을 전달합니다.
- 워커는 작업 1건당 CLI 프로세스 1개를 실행합니다.
- 워커는 내부 설정 스키마를 알 필요가 없습니다.
- 워커 환경에는 MLflow tracker 의존성(`--extra tracking`)이 포함되어야 합니다.

## 안정 인터페이스
- 엔트리포인트: `discoverex`
- 명령: `gen-verify`, `verify-only`, `replay-eval`

## 워커 초기화 요구사항
```bash
mkdir -p .cache/uv
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking
```

## 작업 페이로드 예시
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
  ]
}
```

## 워커 실행 규칙
- 워커는 무상태(stateless) 실행만 담당합니다.
- 작업 1건은 프로세스 1회 실행에 매핑합니다.
- override는 전달 순서를 유지해 `-o` 인자로 전달합니다.
- 엔진 실행 후 delivery 후처리 단계를 별도로 호출합니다.

예시:
```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex gen-verify \
  --background-asset-ref bg://dummy \
  -o runtime/model_runtime=gpu \
  -o models/perception=hf \
  -o runtime.model_runtime.device=cuda:0
```

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
