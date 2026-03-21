# Animate Integration — 최종 현황 보완 사항

> ANIMATE_FINAL_STATUS.md 섹션 6 보완
> 작성일: 2026-03-18

---

## 보완: 세션 중 sprite_gen 스크립트 수정 내역

ANIMATE_FINAL_STATUS.md 섹션 6 "원본 파일 이식 매핑"에서
wan_server.py와 wan_dashboard.html이 "❌ 제외 (REST API / 웹 UI)"로만 표기되어 있으나,
이번 세션에서 두 파일에 Lottie 내보내기 기능이 추가됨. engine 외부 관심사이므로 이식 대상은 아니지만, sprite_gen 스크립트 변경 이력으로서 추적 필요.

### 섹션 6 테이블 하단에 추가할 내용

```markdown
### 세션 중 sprite_gen 스크립트 수정 (engine 미반영, 스크립트 전용)

| sprite_gen 파일 | 변경 내용 | engine 반영 |
|----------------|----------|------------|
| wan_mode_classifier.py (+66줄) | 3단계 JSON 복구 + 핵심 필드 검증 + has_deformable 추론 | ✅ gemini_mode_classifier.py에 반영 (커밋 46b77da) |
| wan_lottie_baker.py (신규 208줄) | Lottie + 키프레임 precomp 래퍼 베이크 | ✅ lottie_baker.py + lottie_baker_transform.py (커밋 40ec18c) |
| wan_server.py (+51줄) | `/api/export_combined`, `/api/export_lottie` API 추가 | ❌ engine 외부 (REST API는 engine 범위 밖) |
| wan_dashboard.html (+74줄) | 📦통합Lottie / 🎬모션Lottie만 / 🔑키프레임JSON 내보내기 버튼 3종 | ❌ engine 외부 (웹 UI는 engine 범위 밖) |
```

### 관련 문서

상세 내용은 `ANIMATE_LOTTIE_BAKER_AND_REMAINING.md` 참조.
