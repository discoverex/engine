# Animate Integration — Lottie Baker Engine 반영 + 미해결 항목 조치 시점

> 작성일: 2026-03-18
> 용도: Claude Code에 전달하여 engine 반영 추적 + 조치 타이밍 확정

---

## 1. Lottie Baker — Engine 반영 필요

### 1.1 배경

세션 중 현재 스크립트(sprite_gen)에 Lottie + 키프레임 통합 내보내기 기능을 추가함.
3개 파일 생성/수정:

| 파일 | 변경 | 내용 |
|------|------|------|
| `wan_lottie_baker.py` | 신규 208줄 | `bake_keyframes()` — Lottie에 CSS 키프레임을 precomp 래퍼로 베이크 |
| `wan_server.py` | +51줄 | `/api/export_combined`, `/api/export_lottie` API 2개 추가 |
| `wan_dashboard.html` | +74줄 | 📦통합Lottie / 🎬모션Lottie만 / 🔑키프레임JSON 내보내기 버튼 3종 |

### 1.2 Engine 반영 범위

| 항목 | engine 반영 위치 | 필요 여부 |
|------|-----------------|----------|
| `bake_keyframes()` 로직 | `adapters/outbound/animate/lottie_baker.py` 신규 또는 `format_converter.py` 확장 | ✅ 필요 — CLI/Prefect 배치에서 통합 Lottie 출력이 필요한 경우 |
| `FormatConversionPort` 메서드 추가 | `application/ports/animate.py` | ⬜ 검토 — `bake(lottie, keyframes, output) → Path` 메서드 추가 여부 |
| `/api/export_combined`, `/api/export_lottie` | engine 미반영 | ❌ 불필요 — REST API는 engine 외부 관심사 (wan_server.py) |
| 대시보드 3종 버튼 | engine 미반영 | ❌ 불필요 — UI는 engine 외부 관심사 (wan_dashboard.html) |

### 1.3 구현 방안

**옵션 A: FormatConversionPort 확장**
```python
class FormatConversionPort(Protocol):
    def convert(self, frames: list[Path], preset: str) -> ConvertedAsset: ...
    def bake_keyframes(self, lottie: Path, keyframes: dict, output: Path) -> Path: ...  # 추가
```
`MultiFormatConverter`에 `bake_keyframes()` 메서드 추가. wan_lottie_baker.py 로직 이식.

**옵션 B: 별도 포트 없이 유틸리티로 배치**
`adapters/outbound/animate/lottie_baker.py`를 포트 없이 orchestrator가 직접 호출.
compositing.py와 동일 패턴 (포트 없이 직접 호출, 향후 필요 시 포트 승격).

**권장**: 옵션 B — compositing.py 선례와 일관. 현재는 포트 없이 시작, 필요 시 승격.

### 1.4 심각도

**LOW** — 현재 engine 배치 파이프라인(orchestrator)은 개별 파일(Lottie + 키프레임 JSON)을 출력하며, 통합 Lottie는 대시보드 전용 기능. engine에서 통합 Lottie가 필요해지면 그때 반영.

---

## 2. 미해결 항목 전수 — 조치 시점 확정

### 지금 해결해야 하는 것 (Phase 6 착수 전 필수)

| # | 항목 | 심각도 | 이유 | 조치 |
|---|------|--------|------|------|
| 1 | 프롬프트 원본 복원 4개 파일 | **HIGH** | 축약 프롬프트로 E2E 실행 시 Gemini 응답 품질 저하 → WAN 실패율 상승, 저품질 통과 | `_prompt.py` 4개를 원본 전문으로 교체. 200L 초과 시 PART1+PART2 분할 |

### Phase 6에서 해결할 것 (E2E 진행 중 처리)

| # | 항목 | 심각도 | 이유 | 조치 시점 |
|---|------|--------|------|----------|
| 2 | ComfyUI 어댑터 구현 | LOW | 실제 ComfyUI 연동 E2E 실행 시에만 필요. Dummy로 전체 흐름은 검증 완료 | E2E 스모크 테스트 착수 시 |
| 3 | flows/subflows.py animate_stub 교체 | LOW | Prefect 배포 검증 시 필요 | Phase 6 항목 25 |
| 4 | 전처리 단위 테스트 추가 | LOW | white_anchor + preprocess 로직 테스트. PIL+scipy 필요 | Phase 6 테스트 보강 시 |
| 5 | DummyFormatConverter 빈 경로 | LOW | orchestrator가 None 허용하므로 현재 동작에 문제 없음 | 필요 시 개선 |
| 6 | Lottie Baker engine 반영 | LOW | 대시보드 전용 기능. engine 배치에서 필요해지면 반영 | 필요 시 |

### 해결 완료 확인 (이전 MEDIUM 5건)

| # | 항목 | 해결 | 확인 |
|---|------|------|------|
| ~~M1~~ | JSON 복구 로직 4개 어댑터 | ✅ | 코드 대조 완전 이식 확인 |
| ~~M2~~ | mode_classifier 3단계 복구 + 핵심 필드 검증 | ✅ | `_robust_parse()` + `_REQUIRED_KEYS` |
| ~~M3~~ | has_deformable 추론 로직 | ✅ | processing_mode에서 추론 |
| ~~M4~~ | soft_pass Pydantic immutable | ✅ | 새 인스턴스 생성 패턴 |
| ~~M5~~ | bg_type 중국어 프롬프트 | ✅ | 원본 전문 복원 (커밋 46b77da) |

---

## 3. 요약

```
지금 해결:  HIGH 1건 (프롬프트 복원) ← Phase 6 착수 전 필수
Phase 6:   LOW 5건 (ComfyUI, stub, 테스트, Dummy, Lottie Baker)
해결 완료:  MEDIUM 0건, 이전 이슈 10건+ 전부 해결
```

**Phase 6 착수 조건**: HIGH 1건(프롬프트 복원) 처리 후 진행 가능.
LOW 5건은 Phase 6 진행 중에 필요한 시점에 순차 처리.
