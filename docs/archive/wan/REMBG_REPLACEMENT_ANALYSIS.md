# BG 제거 방식 교체 분석: flood-fill → rembg (U2Net)

> 작성일: 2026-03-19
> 브랜치: wan/test
> 상태: 분석 완료, 구현 대기

---

## 1. 문제

WAN I2V로 생성된 영상의 배경 제거 시, **흰색 캐릭터(나비 등)의 흰색 영역이 흰색 배경과 함께 삭제**되는 문제.

현재 flood-fill 알고리즘은 색상 차이(tolerance=50)로 배경을 판별하므로,
배경색과 유사한 색상의 캐릭터 부위를 구분하지 못함.

```
원본: 흰 나비 + 흰 배경
  ↓ flood-fill (tolerance=50)
결과: 날개 흰색 부분도 투명 처리 → 날개 손상
```

### 이전 시도 이력

| 커밋 | 접근 | 결과 |
|------|------|------|
| `207791a` | 원본 이미지 flood-fill 보호 마스크 | revert됨 (`64d7590`) |
| `64ae43b` | 원본 알파 채널 기반 보호 마스크 | revert됨 |
| `1aa135c` | 밝은 캐릭터 → 검은 배경 자동 전환 | revert됨 |
| `f37a3d2` | 크로마키 배경 자동 선택 | revert됨 (`94df400`) |
| **현재** | 흰색 배경 + 순수 flood-fill (보호 없음) | **문제 미해결** |

---

## 2. 해결 방안: rembg (U2Net)

### rembg란

- 딥러닝 기반 배경 제거 라이브러리 (PyPI: `rembg`)
- **시맨틱 객체 인식** — 색상이 아닌 형태/텍스처로 전경 판별
- ONNX Runtime 로컬 추론 — **API 불필요, 100% 오프라인 동작**
- 모델 파일: `~/.u2net/u2net.onnx` (167.8MB, 이미 다운로드 완료)

### 왜 해결되는가

| 방식 | 판별 기준 | 흰 나비 + 흰 배경 |
|------|----------|-------------------|
| flood-fill (현재) | "이 픽셀이 배경색과 비슷한가?" | ❌ 날개도 배경으로 오인 |
| rembg U2Net | "이 픽셀이 전경 객체의 일부인가?" | ✅ 형태 인식으로 날개 보존 |

---

## 3. 벤치마크 결과

### 환경

- GPU: NVIDIA GeForce RTX 5070 Ti Laptop (12GB)
- CPU: 현재 CPU 모드 사용 (cuDNN 미설치로 GPU ONNX 사용 불가)
- 테스트 영상: WAN 생성 나비 영상 (64프레임, 480x480)

### 품질 비교 (동일 프레임)

| 방식 | 투명 비율 | 결과 |
|------|----------|------|
| flood-fill (현재) | 95.0% | ❌ 날개 흰색 부분 손상 |
| rembg ISNet | 85.4% | △ 날개 내부 흰색 일부 손실 |
| **rembg U2Net** | **81.4%** | **✅ 날개 형태 완전 보존, 배경만 제거** |

### 속도 비교 (CPU, 64프레임, 480x480)

| 모델 | 프레임당 | 64프레임 전체 | 모델 크기 |
|------|---------|-------------|----------|
| flood-fill (현재) | ~0.001초 | ~0.1초 | 0MB |
| **U2Net (CPU)** | **0.108초** | **~7초** | 176MB |
| ISNet (CPU) | 0.329초 | ~21초 | 44MB |

> WAN 생성 자체가 4-5분 소요되므로, 7초 추가는 전체 파이프라인 대비 무시할 수준 (약 2% 증가)

### GPU 참고

- 현재: `onnxruntime` CPU 버전 사용 (cuDNN 미설치)
- `onnxruntime-gpu` 설치됨, CUDA provider 존재하나 cuDNN 누락으로 CPU 폴백
- cuDNN 설치 시 2-3배 속도 향상 예상 (~3초/64프레임)

---

## 4. 기술 상세

### 실행 방식

```
100% 로컬 ONNX 추론
- 세션: rembg.sessions.u2net.U2netSession
- 엔진: onnxruntime.InferenceSession
- provider: CPUExecutionProvider (GPU 가능)
- 모델: ~/.u2net/u2net.onnx (167.8MB, 캐시 완료)
- API 키: 불필요
- 네트워크: 최초 다운로드 시에만 필요
```

### rembg 사용 가능 모델

| 모델명 | 크기 | 특징 | 벤치마크 |
|--------|------|------|---------|
| `u2net` | 176MB | 범용, 품질 최고 | ✅ 0.108초/프레임 |
| `isnet-general-use` | 44MB | 경량, 이분할 특화 | ✅ 0.329초/프레임 |
| `u2net_human_seg` | 176MB | 인물 전용 | 미테스트 |
| `birefnet-general` | 214MB | 고해상도 경계 | 미테스트 |
| `isnet-anime` | 168MB | 애니메이션 특화 | 미테스트 |

### API 예시

```python
from rembg import remove, new_session

session = new_session("u2net", providers=["CPUExecutionProvider"])

# PIL Image → PIL RGBA Image (투명 배경)
result = remove(pil_image, session=session)
```

---

## 5. 교체 영향 범위

### 변경 필요 파일 (3개)

| 파일 | 변경 내용 |
|------|----------|
| `adapters/outbound/animate/bg_remover.py` | `FfmpegBgRemover` 내부 로직 → rembg 호출로 교체 |
| `conf/animate_adapters/bg_remover/real.yaml` | `tolerance` → `model_name` 파라미터 변경 |
| `pyproject.toml` | `rembg` 의존성 추가 (이미 설치됨) |

### 변경 없음

| 파일 | 이유 |
|------|------|
| `BackgroundRemovalPort` (포트 인터페이스) | 시그니처 동일: `remove(video, fps) → TransparentSequence` |
| `orchestrator.py` | 포트만 호출, 내부 구현 무관 |
| `TransparentSequence` (도메인 타입) | 출력 형식 동일 |
| `FormatConversionPort` (하류 변환) | 입력이 PNG 프레임 리스트로 동일 |
| `DummyBgRemover` (테스트) | 테스트용 Dummy 그대로 |

### 예상 구현

```python
class RembgBgRemover:
    def __init__(self, model_name: str = "u2net") -> None:
        from rembg import new_session
        self._session = new_session(model_name)

    def remove(self, video: Path, fps: int = 16) -> TransparentSequence:
        frames = _extract_raw_frames(str(video))  # 기존 ffmpeg 추출 재사용
        output_dir = video.parent / f"{video.stem}_transparent"
        output_dir.mkdir(parents=True, exist_ok=True)
        result_paths = []
        for i, frame_arr in enumerate(frames):
            pil_img = Image.fromarray(frame_arr)
            rgba = remove(pil_img, session=self._session)
            out = output_dir / f"{video.stem}_frame_{i:04d}.png"
            rgba.save(out, "PNG")
            result_paths.append(out)
        return TransparentSequence(frames=result_paths)
```

---

## 6. 주의 사항

| 항목 | 내용 |
|------|------|
| 프레임 간 일관성 | rembg는 프레임별 독립 처리 → 마스크 플리커 가능. 단색 배경 스프라이트에서는 영향 적음 |
| 반투명 경계 | `alpha_matting=True` 옵션으로 개선 가능 (속도 증가) |
| 모델 다운로드 | 최초 실행 시 인터넷 필요 (167.8MB). 이후 `~/.u2net/`에 캐시 |
| cuDNN 미설치 | 현재 GPU 사용 불가, CPU 폴백. cuDNN 설치 시 속도 향상 |

---

## 7. 결론

| 항목 | flood-fill (현재) | rembg U2Net (교체) |
|------|-------------------|-------------------|
| 흰 나비 문제 | ❌ 미해결 | ✅ 해결 |
| 속도 (64프레임) | ~0.1초 | ~7초 (CPU) |
| 전체 파이프라인 영향 | — | ~2% 증가 (무시 가능) |
| API 필요 | 없음 | 없음 (로컬 ONNX) |
| 교체 범위 | — | 3파일 수정 |
| 포트 인터페이스 변경 | — | 없음 |

**U2Net 교체를 권장합니다.**
