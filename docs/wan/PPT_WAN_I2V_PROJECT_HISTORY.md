# PPT 구성안: WAN I2V 도입 전후 프로젝트 진행 이력

> 작성일: 2026-03-24
> 브랜치: wan/test

---

## 1부: WAN 도입 이전 (기존 MD 내용 기반)

### 슬라이드 1 — 프로젝트 배경

- 비주얼 추론 기반 퍼즐 생성 플랫폼 (숨은그림찾기 + 벤치마크)
- 오브젝트별 자동 애니메이션이 핵심 요구사항
- 테스트 캐릭터: 360×357px 카툰 스타일 개구리 (큰 머리/작은 몸)

### 슬라이드 2 — Phase 1: SD 계열 시도와 실패

- SDXL img2img → 캐릭터 정체성 유지 실패
- FLUX Kontext Pro → 컨셉만 유지, 디테일 변형
- FLUX LoRA 학습 → 이미 변형된 이미지로 학습하여 "일반적 개구리"만 학습

### 슬라이드 3 — 패러다임 전환 결정

- "포즈별 이미지를 각각 생성"하는 접근의 근본적 한계 확인
- 원본 1장 → 비디오 생성 → 프레임 추출로 방향 전환
- WAN 2.2 채널 불일치(**48ch** vs **16ch**) → WAN 2.1 I2V-14B GGUF로 다운그레이드하여 첫 성공

---

## 2부: WAN 도입 이후 — 자동화 파이프라인 구축

### 슬라이드 4 — WAN 파이프라인 전체 아키텍처

- Stage 1: 처리 모드 분류 (KEYFRAME_ONLY vs MOTION_NEEDED)
- Stage 2: WAN 생성 + 검증 루프
- Stage 3: 후처리 (마스크 합성, 배경 제거, Lottie 변환)
- 핵심 모듈 10개의 역할과 관계

### 슬라이드 5 — Stage 1: 사전 분류 (wan_mode_classifier)

- Gemini Vision으로 입력 이미지 분석
- 변형 가능한 부위 존재 여부로 2분류
- KEYFRAME_ONLY → 기존 키프레임 엔진(CPU, 빠름)으로 처리
- MOTION_NEEDED → WAN I2V 생성으로 진행
- 판단 오류 시 MOTION_NEEDED fallback (안전한 방향)

### 슬라이드 6 — Vision 분석 (wan_vision_analyzer)

- Gemini 2.5 Flash로 이미지 완전 자유 분석
- 출력: 액션 설명, 움직이는/고정 부위, moving_zone 좌표, fps, 프레임 수, 모션 범위, 프롬프트(중국어), pingpong 여부, 배경 타입
- 프리셋/분류 체계 없이 AI가 모든 수치를 직접 결정
- 실패 시 최대 3회 재시도

### 슬라이드 7 — 이미지 전처리 & 마스크 생성

- 소형 이미지(<200px) 자동 업스케일: **Real-ESRGAN (spandrel)** 4x AI 초해상도 적용 (타일링 처리, ~200MB VRAM, 즉시 해제). pixel_art일 경우 nearest-neighbor fallback
- 480×480 캔버스에 패딩 배치 (원본 < 캔버스면 축소 없이 유지)
- WanMaskGenerator: moving_zone → 흑백 마스크 PNG 생성
- 흰색(255) = fixed zone, 검정(0) = moving zone
- 경계에 Gaussian blur 적용으로 자연스러운 전환

### 슬라이드 8 — ComfyUI 워크플로우 & WAN 생성

- ComfyUI API 호출 방식 (워크플로우 JSON 파일 로드 + 파라미터 주입)
- WAN 2.1 I2V-14B GGUF — Q3_K_S(7.4GB/6.5GB VRAM), Q4_K_S(9.8GB/8.75GB), Q4_K_M(11GB/9.65GB) 3종 지원. 대시보드에서 설치된 모델만 선택 가능
- 노드 구성: CLIPLoader → VAELoader → CLIPVisionLoader → WanImageToVideo → KSampler → VAEDecode → VHS_VideoCombine
- 프로그레스 바 + 스피너로 실시간 진행 상태 표시

### 슬라이드 9 — 이중 검증 시스템

- 수치 검증 (WanValidator): no_motion, too_slow, too_fast, repeated_motion, frame_escape, no_return_to_origin, center_drift, ghosting, background_color_change
- AI 검증 (WanAIValidator): Gemini Vision이 원본+5개 프레임(0/25/50/75/100%) 비교하여 자유 판단
- 수치 통과 → AI 검증 순서 (비용 절감)
- soft issue (배경 색상 변화 등)는 수치 검증 통과 시 PASS 처리

### 슬라이드 10 — 자동 보정 & 재시도 루프 (최대 7회)

- 수치 실패 → 파라미터 자동 조정 (fps 단계적 증감, scale 감소)
- AI 실패 → Gemini가 fps/scale/프롬프트 수정안 직접 결정
- 연속 품질 실패 3회 → Vision 재분석으로 액션 전환 (exclude_action)
- 연속 no_motion → seed 교체 후 재시도, 3회 초과 시 액션 전환
- 검증 실패 통계 추적 (이미지별·누적)

### 슬라이드 11 — 후처리 파이프라인

- 마스크 기반 픽셀 합성: SetLatentNoiseMask가 WAN video latent(5D)와 비호환 → 프레임별 후처리로 대체
- 배경 제거 (WanBgRemover): 투명 APNG + WebM 출력
- Lottie 변환 (WanLottieConverter): 웹 배포 가능한 JSON 애니메이션

### 슬라이드 12 — Stage 2: 모션 후 키프레임 판단 (wan_post_motion_classifier)

- WAN 생성 완료 후 실제 영상을 Gemini Vision으로 분석
- 7가지 분류: no_travel, travel_lateral, travel_vertical, travel_diagonal, amplify_hop, amplify_sway, amplify_float
- Stage 1 예측과 WAN 실제 결과가 다를 수 있으므로 필요
- CSS 키프레임 보강 여부 + 방향 결정

### 슬라이드 13 — 대시보드 & REST API (wan_dashboard + wan_server)

- Flask 기반 REST API: classify → generate → status 폴링 → select_video → classify_motion
- 웹 대시보드: 이미지 업로드 → 분류 → 모션 생성 → 영상 선택 → 배경 제거/Lottie 변환까지 전 과정 GUI
- 모델 선택 (WAN 2.1/2.2, 다양한 GGUF 양자화), 생성 횟수 설정
- VRAM 관리: 생성 후 free_memory (ComfyUI /free + gc.collect + torch.cuda.empty_cache)

---

## 3부: 성과 & 교훈

### 슬라이드 14 — 기존 방식 vs WAN 방식 비교

- 기존: 포즈별 이미지 각각 생성 → 캐릭터 정체성 유지 실패
- WAN: 원본 1장 → 비디오 → 프레임 추출 → 캐릭터 정체성 100% 유지
- 기존: 수동 검증 → WAN: 이중 자동 검증(수치+AI) + 자동 보정
- 기존: 고정 프리셋 → WAN: AI가 모든 파라미터 자유 결정

### 슬라이드 15 — 핵심 교훈 & 향후 과제

- 교훈: Diffusion img2img의 "캐릭터 정체성 유지" 한계는 구조적
- 교훈: I2V 접근이 일관성 문제를 근본적으로 해결
- 교훈: Gemini Vision의 영상 직접 분석이 검증 자동화의 핵심
- 향후: VRAM 순차 언로드 최적화 (현재 --lowvram 대응, 44% 절감 가능성 확인)
- 향후: Prefect 워커 배포 + CLI animate 커맨드 완성
- 향후: 더 높은 해상도, 프로젝트 전체 파이프라인 통합

---

## 부록 (선택)

- 모듈 의존 관계도: wan_backend를 중심으로 10개 모듈의 호출 관계 다이어그램
- 검증 항목 상세표: 수치 검증 9개 항목의 기준값과 판단 로직 + AI 검증 Gemini Vision 자유 판단 구조
- ComfyUI 워크플로우 노드 맵: 16개 노드의 연결 구조 시각화
