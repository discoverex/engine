# 2026-03-19 세션 최종 요약

> 브랜치: wan/test
> 총 커밋: 18개 (이번 세션)
> 총 변경: 448 files changed, 47,427 insertions

---

## 1. 세션 목표 및 달성

| 목표 | 상태 | 비고 |
|------|------|------|
| ComfyUI 어댑터 구현 | **완료** | 3파일 446줄, E2E 성공 |
| Gemini 4개 포트 연동 | **완료** | YAML 4개 + ModelHandle 전달 |
| 대시보드 서버 (방법 2) | **완료** | Flask 3파일 490줄, 15개 API |
| 프론트엔드 모델 선택 | **완료** | 설치 모델만 표시 + VRAM 정보 + 모델 전달 |
| 생성 진행률 프로그레스 바 | **완료** | ComfyUI /progress → 실시간 표시 |
| 상세 실행 로그 | **완료** | Stage1/Vision 분석 + 시도별 검증 결과 |
| validation_stats.txt | **완료** | sprite_gen 호환 형식 + 기존 이력 복사 |
| 기존 영상 덮어쓰기 방지 | **완료** | attempt offset 자동 계산 |
| WAN 모델 다운로드 | **완료** | Q4_K_S (9.8GB) + Q4_K_M (11GB) 추가 |

---

## 2. 커밋 이력

| # | 커밋 | 구분 | 설명 |
|---|------|------|------|
| 1 | `bea8dc1` | chore | uv.lock 갱신 |
| 2 | `5b61df7` | **feat** | ComfyUI 어댑터 구현 — 3파일(446줄) |
| 3 | `2a9e6f6` | fix | animate CLI 실행 경로 연결 |
| 4 | `69e5810` | **feat** | Gemini 어댑터 4개 YAML + 전체 연동 프로필 |
| 5 | `ced2c9e` | **feat** | engine 대시보드 서버 — Flask 3파일(490줄) |
| 6 | `d79ecc0` | chore | .gitignore에 .env 추가 |
| 7 | `d4aabef` | docs | 세션 작업 요약 v1 |
| 8 | `914176a` | fix | 비디오 목록/서빙 — glob 패턴 + CWD 경로 |
| 9 | `9c56329` | **feat** | 모델 선택 → ComfyUI 워크플로우 전달 |
| 10 | `0b954cc` | **feat** | 설치된 모델만 대시보드 표시 |
| 11 | `d09c8bc` | feat | 모델 VRAM 요구량 표시 |
| 12 | `1325c3f` | **feat** | ComfyUI 생성 진행률 프로그레스 바 |
| 13 | `0edbdb4` | **feat** | 상세 실행 로그 + validation_stats.txt |
| 14 | `f9e70af` | docs | 세션 작업 요약 v2 |
| 15 | `517498f` | fix | 워크플로우 로그에 모델명 표시 |
| 16 | `b3dd478` | **feat** | orchestrator 상세 로그 (Stage1 + Vision 전체) |
| 17 | `a28fe67` | fix | 기존 영상 덮어쓰기 방지 — attempt offset |
| 18 | 이 커밋 | docs | 세션 최종 요약 |

---

## 3. 최종 아키텍처

```
브라우저 (dashboard.html)
    ↓ HTTP REST (15+ API)
engine_server.py (Flask, port 5001)
    ↓
AnimateOrchestrator
    ├── GeminiModeClassifier        ← Gemini 2.5 Flash
    ├── GeminiVisionAnalyzer        ← Gemini 2.5 Flash
    ├── ComfyUIWanGenerator         ← ComfyUI (port 8188)
    │   └── 모델: Q3_K_S / Q4_K_S / Q4_K_M (프론트엔드 선택)
    ├── NumericalAnimationValidator  ← 8개 메트릭
    ├── GeminiAIValidator           ← Gemini 2.5 Flash
    ├── GeminiPostMotionClassifier  ← Gemini 2.5 Flash
    ├── FfmpegBgRemover             ← ffmpeg + flood-fill
    ├── PilMaskGenerator            ← PIL
    ├── PilKeyframeGenerator        ← 물리 기반 키프레임
    └── MultiFormatConverter        ← APNG/WebM/Lottie

RetryLogger → validation_stats.txt (sprite_gen 호환)
```

---

## 4. 프론트엔드 기능 현황

| 기능 | 상태 | 구현 |
|------|------|------|
| 이미지 파일 브라우저 | ✅ | `/api/browse` |
| Stage 1 분류 (Gemini) | ✅ | `/api/classify` |
| KEYFRAME_ONLY 키프레임 생성 | ✅ | `PilKeyframeGenerator` |
| 모델 선택 (설치된 것만) | ✅ | `/api/available_models` + 동적 select |
| VRAM 요구량 표시 | ✅ | 양자화별 VRAM 테이블 |
| 비동기 모션 생성 | ✅ | `threading.Thread` + job_id 폴링 |
| 생성 진행률 프로그레스 바 | ✅ | ComfyUI `/progress` |
| 비디오 그리드 표시 | ✅ | `/api/videos/<stem>` |
| 비디오 BG 제거 + Lottie | ✅ | `FfmpegBgRemover` + `MultiFormatConverter` |
| Stage 2 포스트모션 분류 | ✅ | `GeminiPostMotionClassifier` |
| 키프레임 에디터 | ✅ | 7개 슬라이더 (dashboard.html 내장) |
| Lottie/Combined 내보내기 | ✅ | `/api/export_combined`, `/api/export_lottie` |
| 통계 차트 | ✅ | `/api/stats/<stem>` + Chart.js |

---

## 5. 터미널 로그 출력 (예시)

```
[Animate] start: butterfly_01
[Stage1] mode=motion_needed facing=left scene=False deformable=True action=
  → 대상: A realistic butterfly... | 근거: The butterfly's wings are flexible...
  → 액션: Forewings gently raising and lowering.
  → 오브젝트: A realistic butterfly with yellow, black, and white patterns...
  → 움직임: The forewings (upper wings). | 고정: The body (head, thorax, abdomen)...
  → fps=14 motion=0.04~0.18 pingpong=True
  → positive: 纯白色背景，整个动画过程中背景始终保持白色...
  → negative: 身体旋转，身体漂移，全身运动...
  → 근거: The most natural motion for a butterfly...
  [이력] 기존 영상 3개 발견 → attempt 4부터 시작
  [시도 4] seed=1415630199 fps=14
  ❌ 수치 검증 실패: ['too_fast', 'ghosting']
  ❌ AI 검증 실패: ['unnatural_movement'] | Character becomes blurry...
  [AI조정] fps→10, neg:模糊，画面模糊...
  [시도 5] seed=3107579379 fps=10
  ✅ 성공 (attempt 5, seed=3107579379)
────── [통계] butterfly_01 — 총 2회 시도 ──────
  수치실패: {'ghosting': 1, 'too_fast': 1}
  보완조치: {'ai_adjust': 1}
```

---

## 6. 설치된 WAN 모델

| 모델 | 크기 | VRAM | 비고 |
|------|------|------|------|
| wan2.1-i2v-14b-480p-Q3_K_S.gguf | 7.4GB | 6.5GB | 기존 설치 |
| wan2.1-i2v-14b-480p-Q4_K_S.gguf | 9.8GB | 8.75GB | 이번 세션 |
| wan2.1-i2v-14b-480p-Q4_K_M.gguf | 11GB | 9.65GB | 이번 세션 |

WAN 2.2 모델은 HF 로그인 후 다운로드 가능 (보류 중).

---

## 7. 실행 방법

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine 대시보드
cd ~/engine
export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui

# 브라우저
# http://localhost:5001/
```

---

## 8. 신규 파일 전체 (이번 세션)

```
# ComfyUI 어댑터
src/discoverex/adapters/outbound/models/comfyui_client.py         (180줄)
src/discoverex/adapters/outbound/models/comfyui_workflow.py        (143줄)
src/discoverex/adapters/outbound/models/comfyui_wan_generator.py   (127줄)
conf/models/animation_generation/comfyui.yaml
conf/workflows/wan21_i2v.json

# Gemini YAML
conf/models/mode_classifier/gemini.yaml
conf/models/vision_analyzer/gemini.yaml
conf/models/ai_validator/gemini.yaml
conf/models/post_motion_classifier/gemini.yaml

# 대시보드 서버
src/discoverex/adapters/inbound/web/__init__.py
src/discoverex/adapters/inbound/web/engine_server.py               (194줄)
src/discoverex/adapters/inbound/web/engine_server_extra.py         (171줄)
src/discoverex/adapters/inbound/web/engine_server_helpers.py       (173줄)
src/discoverex/adapters/inbound/web/dashboard.html                 (1458줄)

# animate_adapters YAML
conf/animate_adapters/bg_remover/real.yaml
conf/animate_adapters/format_converter/real.yaml
conf/animate_adapters/keyframe_generator/real.yaml
conf/animate_adapters/numerical_validator/real.yaml
conf/animate_adapters/mask_generator/real.yaml

# Hydra 설정
conf/animate_comfyui.yaml
conf/flows/animate/comfyui_pipeline.yaml

# 로그/통계
src/discoverex/application/use_cases/animate/retry_logger.py       (131줄)

# 보고서
COMFYUI_ADAPTER_REPORT.md
COMFYUI_E2E_REPORT.md
ENGINE_DASHBOARD_REPORT.md
SESSION_SUMMARY_20260319.md
SESSION_SUMMARY_20260319_v2.md
```

---

## 9. 수정된 기존 파일

| 파일 | 변경 |
|------|------|
| `src/discoverex/config/schema.py` | PipelineConfig extra="ignore" |
| `src/discoverex/config/animate_schema.py` | AnimatePipelineConfig extra="ignore" |
| `src/discoverex/config_loader.py` | `load_raw_animate_config()` 추가 |
| `src/discoverex/flows/subflows.py` | raw config 재compose |
| `src/discoverex/bootstrap/factory.py` | load() + GEMINI_API_KEY + os import |
| `src/discoverex/adapters/inbound/cli/main.py` | `serve` 커맨드 추가 |
| `src/discoverex/application/use_cases/animate/retry_loop.py` | RetryLogger + attempt offset |
| `src/discoverex/application/use_cases/animate/orchestrator.py` | 상세 로그 (Stage1 + Vision) |
| `.gitignore` | .env 추가 |

---

## 10. 검증

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | 0건 위반 |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
| ComfyUI E2E (Dummy) | 성공 — 449KB MP4, 284초 |
| Gemini + ComfyUI E2E | 동작 — 7 attempt, 33.5분 |
| 대시보드 E2E | 동작 — 모델 선택, 진행률 표시, 비디오 서빙 |
