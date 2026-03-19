# Engine 대시보드 서버 구현 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 대상: 방법 2 — sprite_gen 대시보드를 engine 백엔드로 교체

---

## 1. 배경

sprite_gen의 `wan_dashboard.html`(1,438줄) + `wan_server.py`(719줄)는 5단계 파이프라인 대시보드로
이미 완전히 동작하는 프론트엔드입니다.

engine에서 동일한 대시보드를 사용하되, 백엔드를 engine의 포트/어댑터로 교체하는 **방법 2**를 구현.
대시보드 HTML 변경 없이, API 엔드포인트/요청/응답 형식을 동일하게 유지.

---

## 2. 구현 내용

### 2.1 animate_adapters YAML 전환 (Step 1)

engine에 이미 913줄의 실제 구현체가 존재했으나, Hydra YAML이 Dummy를 가리키고 있었음.
YAML 5개를 생성하여 실제 어댑터로 전환.

| 어댑터 | Dummy → 실제 클래스 | 줄수 |
|--------|---------------------|------|
| bg_remover | `DummyBgRemover` → `FfmpegBgRemover` | 97 |
| format_converter | `DummyFormatConverter` → `MultiFormatConverter` | 156 |
| keyframe_generator | `DummyKeyframeGenerator` → `PilKeyframeGenerator` | 154 |
| numerical_validator | `DummyAnimationValidator` → `NumericalAnimationValidator` | 125 |
| mask_generator | `DummyMaskGenerator` → `PilMaskGenerator` | — |

**코드 변경 없음.** YAML `_target_` 경로 변경만으로 전환 완료.

### 2.2 Flask 서버 구현 (Step 2)

sprite_gen의 `wan_server.py`를 engine의 포트/어댑터로 교체한 Flask 서버 3파일.

| 파일 | 줄수 | 책임 |
|------|------|------|
| `engine_server.py` | 189 | Flask app + 핵심 API (classify, generate, status, videos) |
| `engine_server_extra.py` | 158 | 추가 API (select_video, classify_motion, export, stats, browse, files) |
| `engine_server_helpers.py` | 143 | 유틸리티 (video_list, resolve_path, serve_media, browse_dir, parse_stats) |
| **합계** | **490** | |

### 2.3 API 엔드포인트 매핑 (15개)

| API | sprite_gen 호출 | engine 호출 |
|-----|----------------|-------------|
| `POST /api/classify` | `WanModeClassifier.classify()` | `orchestrator.mode_classifier.classify()` |
| `POST /api/generate` | `WanBackend.generate()` (thread) | `orchestrator.run()` (thread) |
| `GET /api/status/<id>` | `_jobs` dict 폴링 | 동일 패턴 |
| `GET /api/videos/<stem>` | glob MP4 | 동일 |
| `GET /api/videos_all` | glob MP4 | 동일 |
| `POST /api/select_video` | `WanBgRemover` + `WanLottieConverter` | `orchestrator.bg_remover.remove()` + `format_converter.convert()` |
| `POST /api/classify_motion` | `WanPostMotionClassifier` | `orchestrator.post_motion_classifier.classify()` |
| `POST /api/generate_keyframe` | `WanKeyframeGenerator` | `orchestrator.keyframe_generator.generate()` |
| `POST /api/export_combined` | `bake_keyframes()` | `lottie_baker.bake_keyframes()` (동일 함수) |
| `POST /api/export_lottie` | `send_file()` | 동일 |
| `GET /api/files/<path>` | MIME 서빙 | 동일 |
| `GET /api/video_thumb/<path>` | ffmpeg 첫 프레임 | 동일 |
| `GET /api/browse` | 디렉토리 탐색 | 동일 |
| `GET /api/stats/<stem>` | validation_stats.txt 파싱 | 동일 |
| `GET /api/stats_all` | 누적 통계 | 동일 |

### 2.4 CLI serve 커맨드 (Step 3)

```bash
uv run discoverex serve --port 5001 --config-name animate_comfyui
```

`main.py`에 `serve` 커맨드 추가. 내부적으로:
1. `load_raw_animate_config()` — Hydra config compose
2. `build_animate_context()` — orchestrator 생성 (Gemini + ComfyUI + 실제 어댑터)
3. `create_app(orchestrator)` — Flask app 초기화
4. `flask_app.run()` — 개발 서버 시작

---

## 3. 아키텍처

```
브라우저 (wan_dashboard.html)
    ↓ HTTP REST
engine_server.py (Flask)
    ↓
build_animate_context() → AnimateOrchestrator
    ├── mode_classifier      → GeminiModeClassifier
    ├── vision_analyzer      → GeminiVisionAnalyzer
    ├── animation_generator  → ComfyUIWanGenerator
    ├── ai_validator         → GeminiAIValidator
    ├── post_motion_classifier → GeminiPostMotionClassifier
    ├── numerical_validator  → NumericalAnimationValidator
    ├── bg_remover           → FfmpegBgRemover
    ├── mask_generator       → PilMaskGenerator
    ├── keyframe_generator   → PilKeyframeGenerator
    └── format_converter     → MultiFormatConverter
```

**sprite_gen 의존성 완전 제거.** 대시보드 HTML만 sprite_gen 경로에서 서빙.

---

## 4. 파일 변경 요약

### 신규 파일

| 파일 | 경로 |
|------|------|
| Flask 서버 메인 | `src/discoverex/adapters/inbound/web/engine_server.py` |
| 추가 라우트 | `src/discoverex/adapters/inbound/web/engine_server_extra.py` |
| 유틸리티 | `src/discoverex/adapters/inbound/web/engine_server_helpers.py` |
| 패키지 init | `src/discoverex/adapters/inbound/web/__init__.py` |
| BG 제거 YAML | `conf/animate_adapters/bg_remover/real.yaml` |
| 포맷 변환 YAML | `conf/animate_adapters/format_converter/real.yaml` |
| 키프레임 생성 YAML | `conf/animate_adapters/keyframe_generator/real.yaml` |
| 수치 검증 YAML | `conf/animate_adapters/numerical_validator/real.yaml` |
| 마스크 생성 YAML | `conf/animate_adapters/mask_generator/real.yaml` |

### 수정 파일

| 파일 | 변경 |
|------|------|
| `conf/animate_comfyui.yaml` | animate_adapters Dummy → 실제 `_target_` |
| `src/discoverex/adapters/inbound/cli/main.py` | `serve` 커맨드 추가 |

---

## 5. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success: no issues found in 4 source files |
| 200줄 제약 | 0건 위반 (189 / 158 / 143) |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |

---

## 6. 사용 방법

```bash
# 1. 환경변수 설정
export GEMINI_API_KEY=<your-key>

# 2. ComfyUI 서버 실행 (별도 터미널)
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# 3. Engine 대시보드 서버 시작
cd ~/engine && uv run discoverex serve --port 5001 --config-name animate_comfyui

# 4. 브라우저에서 접속
# http://localhost:5001/
```

### 대시보드 5단계 파이프라인

1. **Stage 1**: 이미지 선택 → Gemini 분류 (KEYFRAME_ONLY / MOTION_NEEDED)
2. **Stage 2**: WAN I2V 모션 생성 (ComfyUI, 비동기 + 실시간 폴링)
3. **Stage 3**: 생성된 비디오 선택 (MP4 그리드)
4. **Stage 4**: 배경 제거 → APNG/WebM/Lottie 변환
5. **Stage 5**: 포스트모션 분류 → 키프레임 에디터 → 내보내기

---

## 7. sprite_gen 대비 비교

| 항목 | sprite_gen | engine |
|------|-----------|--------|
| 백엔드 | 직접 호출 (단일 파일) | 헥사고널 포트/어댑터 |
| 설정 | 환경변수/글로벌 상수 | Hydra YAML 설정 |
| 어댑터 전환 | 코드 수정 필요 | YAML `_target_` 변경만 |
| 테스트 | 수동 | 234 자동화 테스트 |
| 대시보드 HTML | 동일 | 동일 (sprite_gen 경로에서 서빙) |
| API 형식 | 동일 | 동일 |
| WAN 모션 생성 | ComfyUI 직접 | ComfyUIWanGenerator 어댑터 |
| Gemini 호출 | 직접 | GeminiClientMixin 어댑터 |
| BG 제거 | `wan_bg_remover.py` | `FfmpegBgRemover` (동일 알고리즘) |
| Lottie 변환 | `wan_lottie_converter.py` | `MultiFormatConverter` (동일 알고리즘) |
