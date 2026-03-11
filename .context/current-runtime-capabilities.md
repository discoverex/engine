# Discoverex Current Runtime Capabilities

이 문서는 현재 코드와 최근 검증 기준으로 `무엇이 실제로 동작하는지`를 기록합니다.
제품 기대치나 이상적 아키텍처가 아니라, 지금 워커와 인프라에 올렸을 때 확인된 사실만 남깁니다.

## 1) 현재 실제로 검증된 실행 체인

현재 확인된 경로:

`engine job spec wrapper -> Prefect deployment/run -> fixed worker pickup -> engine repo-mode execute -> MinIO artifact 저장 -> MLflow run 기록`

최근 원격 검증에서 확인된 사실:

* Prefect flow run 생성 및 `COMPLETED` 종료
* fixed worker가 `gpu-pool / gpu-fixed` 큐에서 잡을 pickup
* worker subprocess가 engine launcher를 통해 `discoverex generate` 실행
* MinIO에 flow-level artifact 저장
  * `stdout.log`
  * `stderr.log`
  * `result.json`
  * `artifacts.json`
* MinIO에 scene-level artifact 저장
  * `scene.json`
  * `verification.json`
  * `composite.png`
* MLflow에 engine run 생성 및 params/metrics/tags 기록

## 2) "엔진이 정상 동작한다"의 현재 의미

현재 문맥에서 "정상 동작"은 아래를 뜻합니다.

* worker가 job spec을 받아 launcher를 실행한다
* launcher가 runtime env / overrides를 주입해 `discoverex generate|verify|animate`를 실행한다
* engine이 scene bundle을 저장한다
* tracker가 MLflow run을 남긴다
* worker가 flow-level stdout/stderr/result/manifest를 업로드한다

중요:

* `scene.meta.status=failed`는 곧바로 시스템 실패를 뜻하지 않습니다
* 최근 검증 run들은 `flow state=COMPLETED`, `worker result.exit_code=0` 이었지만
  scene verification quality gate에서 탈락해 `scene status=failed`로 끝났습니다

즉 현재 실패는 두 층으로 구분해야 합니다.

* orchestration failure: Prefect / worker / launcher / subprocess 실패
* quality failure: scene 생성은 되었지만 verification threshold 미통과

## 3) 최근 검증에서 확인된 실행 프로필

### 로컬 E2E

로컬 E2E는 빠른 재현을 위해 `local-tiny-cpu`를 사용합니다.

주요 특징:

* `runtime/model_runtime=cpu`
* `models/*=tiny_torch`
* local/docker 테스트 스택 중심

### 원격 / 운영 검증

원격 검증과 실제 job submission은 `remote-gpu-hf`를 사용했습니다.

주요 특징:

* `runtime/model_runtime=gpu`
* `models/hidden_region=hf`
* `models/inpaint=hf`
* `models/perception=hf`
* `models/fx=hf`
* `adapters/artifact_store=minio`
* `adapters/tracker=mlflow_server`

## 4) worker mode의 현재 운영 경로

현재 worker mode에서는 아래 구성이 표준입니다.

* artifact store: `minio`
* tracker: `mlflow_server`
* metadata store: 필요 시 `postgres`
* MLflow 인증: engine 내부 직접 인증이 아니라 worker-side proxy가 대리

정리:

* engine은 MLflow SDK를 사용한다
* worker는 upstream `MLFLOW_TRACKING_URI`를 로컬 프록시 URL로 바꿔 child process에 주입한다
* worker만 Cloudflare Access credential을 가진다

## 5) 최근 실 run에서 확인된 산출물 형태

최근 production-profile run 기준:

* flow run id: `27ffdca8-077b-441d-99a9-19304b221041`
* scene id: `scene-e2f9bc6fd4b7`
* version id: `v-20260309034157`
* MLflow run id: `8047c792eb7d44fdbe2d98c49de034b8`

해당 run에서 확인된 사실:

* worker result `exit_code=0`
* engine stdout 최종 JSON에 `scene_id`, `version_id`, `status`, `scene_json` 포함
* `verification.json`에 `logical/perception/final` score 구조가 채워짐
* `composite.png` 객체도 존재함

다만 현재 `composite.png` 존재만으로 "실제 product-grade 렌더 완성"을 의미하지는 않습니다.
그 부분은 별도 문서(`generation-gaps-and-placeholders.md`)에서 설명합니다.

## 6) 참고 파일

실행/계약 관련 핵심 파일:

* `infra/register/register_prefect_job.py`
* `infra/register/register_orchestrator_job.py`
* `src/discoverex/orchestrator_contract/launcher.py`
* `src/discoverex/flows/engine.py`
* `src/discoverex/flows/generate.py`

최근 실 run artifact 기준 경로:

* `artifacts/prod_prefect_runs/27ffdca8-077b-441d-99a9-19304b221041/summary.json`
* `artifacts/prod_prefect_runs/27ffdca8-077b-441d-99a9-19304b221041/result.json`
* `artifacts/prod_prefect_runs/27ffdca8-077b-441d-99a9-19304b221041/engine_output.json`
