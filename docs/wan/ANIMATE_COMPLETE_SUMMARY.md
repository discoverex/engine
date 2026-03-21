# Animate Pipeline Integration — 전체 진행 완료 요약

> sprite_gen → engine 헥사고널 아키텍처 이식 프로젝트
> 작업 기간: 2026-03-18
> 브랜치: wan/test
> 커밋 수: 20개 (6d6db6d 이후)

---

## 1. 프로젝트 개요

`/home/snake2/anim_pipeline/image_pipeline/sprite_gen/` (6,745줄, 12개 파일)의
AI 기반 스프라이트 애니메이션 생성 파이프라인을
`/home/snake2/engine/` 의 헥사고널 아키텍처(Ports & Adapters)에 적합하도록 재구조화하여 이식.

**원본 파이프라인 흐름**:
```
입력 이미지
  → Stage 1: Mode 분류 (KEYFRAME_ONLY / MOTION_NEEDED)
  → Vision 분석 (Gemini → 모션 파라미터)
  → WAN I2V 생성 (ComfyUI, 최대 7회 재시도)
  → 수치 검증 (9개 품질 지표)
  → AI 검증 (Gemini Vision 주관 평가 + 파라미터 보정)
  → Stage 2: 후처리 분류 (키프레임 트래블)
  → 배경 제거 → 포맷 변환 (APNG / WebM / Lottie)
```

---

## 2. Phase별 진행 내역

### Phase 1 — 도메인 & 포트 (`4bf038f`)
- Enum 4개 + Pydantic BaseModel 엔티티 14개 정의
- Protocol 포트 인터페이스 10개 정의
- AnimatePipelineConfig 설정 스키마

### Phase 2 — 순수 로직 이식 (`d73e6d3`)
- preprocessing.py: white_anchor + 캔버스 패딩
- mask_generator.py: 바이너리 마스크 (PIL)
- keyframe_generator.py: CSS 키프레임 10종 (물리 수식 기반)
- numerical_validator.py: 9개 품질 지표 검증 (PIL/numpy/ffmpeg)

### Phase 3 — 외부 서비스 어댑터 (`89a77d3`)
- Gemini Vision 어댑터 4개 (Mode/Vision/AI/PostMotion)
- GeminiClientMixin 공유 인프라 (load/unload 라이프사이클)
- bg_remover.py: 배경 제거 → 투명 PNG 시퀀스
- format_converter.py: APNG + WebM + Lottie 통합 변환

### Phase 4 — Dummy 어댑터 & 테스트 (`010e570`)
- 모델 포트 Dummy 5개 + 처리 어댑터 Dummy 5개
- 도메인 엔티티 단위 테스트 19건
- 포트 계약 테스트 11건

### Phase 5 — 오케스트레이션 & 부트스트랩 (`e850059`)
- AnimateOrchestrator: 전체 파이프라인 조율
- RetryLoop: 생성+검증 재시도 (원본 3회 중복 로직 → 헬퍼로 통합)
- build_animate_context(): Hydra instantiate 팩토리
- Hydra dummy YAML 10개 + pipeline 설정

### Phase 6 — Flow 연결 & 통합 테스트 (`46439f7`)
- animate_pipeline() subflow 함수 추가
- Hydra animate_pipeline.yaml 설정
- Flow 레벨 통합 테스트 2건

### 추가 반영
- 프롬프트 원본 복원 4개 (`40ec18c`) — HIGH 해소
- mode_classifier 3단계 JSON 복구 강화 (`46b77da`)
- bg_type 중국어 배경 프롬프트 원본 복원 (`46b77da`)
- Lottie Baker 유틸리티 (`40ec18c`)
- 검증 지표 수 표기 정정 8→9 (`cd3d6df`)

---

## 3. 전체 수치

| 항목 | 수치 |
|------|------|
| 커밋 | 20개 |
| 코드 파일 (신규/수정) | 53개, +4,108줄 |
| 문서 파일 | 20개, +3,762줄 |
| 총 변경 | 73개 파일, +7,870줄 |
| 테스트 | **234 passed, 8 skipped, 0 failed** |
| 신규 테스트 | 33건 (4개 파일) |
| 200L 제약 위반 | 0건 |
| mypy strict 에러 | 0건 |
| ruff 에러 | 0건 |

---

## 4. 원본 파일 이식 매핑

| sprite_gen 원본 (줄) | engine 이식 위치 | 상태 |
|---------------------|-----------------|------|
| wan_mode_classifier.py (386) | gemini_mode_classifier.py + prompt | ✅ |
| wan_vision_analyzer.py (491) | gemini_vision_analyzer.py + prompt | ✅ |
| wan_ai_validator.py (541) | gemini_ai_validator.py + prompt | ✅ |
| wan_post_motion_classifier.py (406) | gemini_post_motion.py + prompt | ✅ |
| wan_validator.py (708) | numerical_validator.py + metrics + extraction | ✅ |
| wan_keyframe_generator.py (512) | keyframe_generator.py + travel + physics | ✅ |
| wan_mask_generator.py (104) | mask_generator.py | ✅ |
| wan_bg_remover.py (254) | bg_remover.py + format_converter.py | ✅ |
| wan_lottie_converter.py (247) | format_converter.py (통합) | ✅ |
| wan_lottie_baker.py (208) | lottie_baker.py + transform | ✅ |
| wan_backend.py 전처리 (164) | preprocessing.py | ✅ |
| wan_backend.py 오케스트레이션 (576) | orchestrator.py + retry_loop.py + retry_state.py | ✅ |
| wan_backend.py ComfyUI (843) | — | ⬜ 미구현 |
| wan_server.py (581) | — | ❌ 제외 |
| wan_dashboard.html | — | ❌ 제외 |

**이식률**: 12/15 모듈 완료 (ComfyUI 미구현, REST API/대시보드 제외)

---

## 5. 아키텍처 구조

```
src/discoverex/
├── domain/
│   ├── animate.py                    # Enum 4 + BaseModel 10
│   └── animate_keyframe.py           # 키프레임 3 + 결과 3
├── application/
│   ├── ports/animate.py              # Protocol 10개
│   └── use_cases/animate/
│       ├── orchestrator.py           # 전체 파이프라인 조율
│       ├── retry_loop.py             # 재시도 전략
│       ├── retry_state.py            # 루프 상태 + 상수
│       └── preprocessing.py          # 이미지 전처리
├── adapters/outbound/
│   ├── models/
│   │   ├── gemini_common.py          # 공유 Mixin
│   │   ├── gemini_mode_classifier.py # Stage 1
│   │   ├── gemini_vision_analyzer.py # Vision 분석
│   │   ├── gemini_ai_validator.py    # AI 검증
│   │   ├── gemini_post_motion.py     # Stage 2
│   │   ├── gemini_*_prompt.py × 4    # 프롬프트 (원본 전문)
│   │   └── dummy_animate.py          # 모델 Dummy 5개
│   └── animate/
│       ├── numerical_validator.py    # 9개 수치 검증
│       ├── validator_metrics.py      # 지표 계산 함수
│       ├── frame_extraction.py       # ffmpeg 프레임 추출
│       ├── bg_remover.py             # 배경 제거
│       ├── format_converter.py       # APNG/WebM/Lottie
│       ├── lottie_baker.py           # 키프레임 베이크
│       ├── lottie_baker_transform.py # precomp 변환
│       ├── mask_generator.py         # 바이너리 마스크
│       ├── keyframe_generator.py     # CSS 키프레임
│       ├── keyframe_travel.py        # launch/float/hop
│       ├── keyframe_physics.py       # damped sin/cos
│       └── dummy_animate.py          # 처리 Dummy 5개
├── config/animate_schema.py          # 설정 스키마
├── bootstrap/factory.py              # build_animate_context()
└── flows/subflows.py                 # animate_pipeline()

conf/
├── models/*/dummy.yaml × 5
├── animate_adapters/*/dummy.yaml × 5
└── flows/animate/
    ├── stub.yaml
    ├── replay_eval.yaml
    └── animate_pipeline.yaml

tests/
├── test_animate_domain.py            # 19건
├── test_animate_ports_contract.py    # 11건
├── test_animate_orchestrator.py      # 1건
└── test_animate_flow.py              # 2건
```

---

## 6. 미해결 항목

| # | 항목 | 심각도 | 비고 |
|---|------|--------|------|
| 1 | ComfyUI 어댑터 (~843줄) | LOW | GPU + ComfyUI 서버 환경에서 구현 |
| 2 | 전처리 단위 테스트 | LOW | PIL+scipy 합성 이미지 테스트 |
| 3 | E2E 스모크 (ComfyUI + Gemini) | LOW | ComfyUI 어댑터 + GPU + API 키 필요 |
| 4 | Prefect 배포 검증 | LOW | animate job_spec YAML + worker 환경 필요 |
| 5 | CLI animate 커맨드 인자 | LOW | `--image-path` 인자 추가 필요 (현재 `--scene-jsons`만) |

**HIGH 0건, MEDIUM 0건** — 차단 이슈 없음.

---

## 7. 커밋 이력 (시간순)

| # | 커밋 | 유형 | 내용 |
|---|------|------|------|
| 1 | `4bf038f` | feat | Phase 1: 도메인 + 포트 + 설정 |
| 2 | `d73e6d3` | feat | Phase 2: 순수 로직 이식 10파일 |
| 3 | `a61ea21` | docs | Phase 2 보고서 |
| 4 | `cd3d6df` | docs | 검증 지표 8→9 정정 + 체크리스트 |
| 5 | `89a77d3` | feat | Phase 3: Gemini 4 + bg/format 어댑터 |
| 6 | `af45636` | docs | Phase 3 보고서 |
| 7 | `364b7dd` | docs | Phase 3 리뷰 |
| 8 | `010e570` | feat | Phase 4: Dummy 10개 + 테스트 30건 |
| 9 | `48f518a` | docs | Phase 4 보고서 |
| 10 | `15ae983` | docs | Phase 4 체크리스트 |
| 11 | `e850059` | feat | Phase 5: 오케스트레이터 + 부트스트랩 |
| 12 | `d00a34d` | docs | Phase 5 보고서 |
| 13 | `46b77da` | fix | mode_classifier 복구 + bg 프롬프트 복원 |
| 14 | `94e7f80` | docs | 체크리스트 결과 + 미해결 종합 |
| 15 | `40ec18c` | feat | 프롬프트 원본 복원 4개 + Lottie Baker |
| 16 | `299111d` | docs | 최종 진행 현황 |
| 17 | `b31ae34` | docs | sprite_gen 수정 이력 보완 |
| 18 | `68fcb69` | docs | 보완 적용 결과 |
| 19 | `46439f7` | feat | Phase 6: Flow 연결 + 통합 테스트 |
| 20 | `a3a6082` | docs | Phase 6 보고서 |

---

## 8. 문서 목록

| 파일 | 내용 |
|------|------|
| `ANIMATE_INTEGRATION_PLAN.md` | 통합 계획서 (10개 섹션, 리뷰/검증 반영 완료) |
| `ANIMATE_INTEGRATION_PLAN_REVIEW.md` | 계획서 리뷰 7건 수정 지시 |
| `ANIMATE_COMPATIBILITY_VERIFICATION.md` | 코드 레벨 호환성 검증 (7건 불일치 → 반영) |
| `ANIMATE_PHASE1_REPORT.md` | Phase 1 완료 보고서 |
| `ANIMATE_PHASE2_REPORT.md` | Phase 2 완료 보고서 |
| `ANIMATE_PHASE3_REPORT.md` | Phase 3 완료 보고서 |
| `ANIMATE_PHASE3_REVIEW.md` | Phase 3 리뷰 9건 |
| `ANIMATE_PHASE4_REPORT.md` | Phase 4 완료 보고서 |
| `ANIMATE_PHASE5_REPORT.md` | Phase 5 완료 보고서 |
| `ANIMATE_PHASE6_REPORT.md` | Phase 6 완료 보고서 |
| `ANIMATE_PHASE1_2_CHECKLIST.md` | Phase 1-2 체크리스트 |
| `ANIMATE_PHASE4_CHECKLIST.md` | Phase 4 체크리스트 |
| `ANIMATE_PHASE5_CHECKLIST.md` | Phase 5 체크리스트 |
| `ANIMATE_PHASE5_CHECKLIST_RESULT.md` | Phase 5 체크리스트 반영 결과 |
| `ANIMATE_REMAINING_ISSUES.md` | 미해결 항목 종합 |
| `ANIMATE_LOTTIE_BAKER_AND_REMAINING.md` | Lottie Baker + 조치 시점 |
| `ANIMATE_FINAL_STATUS.md` | 최종 현황 (파일 전수 목록) |
| `ANIMATE_FINAL_STATUS_SUPPLEMENT.md` | 현황 보완 지시 |
| `ANIMATE_SUPPLEMENT_APPLIED.md` | 보완 적용 결과 |
| `ANIMATE_COMPLETE_SUMMARY.md` | 전체 진행 완료 요약 (본 문서) |
