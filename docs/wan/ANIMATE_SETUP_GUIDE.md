# Animate Pipeline — 신규 환경 설치 및 실행 가이드

> Git에서 pull 받은 후 새 PC에서 처음부터 설치하여 실행하는 전체 절차
> 대상: engine (헥사고널 아키텍처) + sprite_gen (현재 운영 스크립트)

---

## 0. 시스템 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| OS | Ubuntu 22.04+ / WSL2 Ubuntu 24.04 | WSL2 Ubuntu 24.04 |
| GPU | NVIDIA 8GB VRAM | NVIDIA 12GB+ VRAM (RTX 3060 이상) |
| RAM | 16GB | 32GB |
| Python | 3.11+ | 3.11 |
| 저장공간 | 30GB (모델 포함) | 50GB |
| CUDA | 12.x | 12.4+ |

---

## 1. NVIDIA 드라이버 + CUDA 확인

```bash
# 드라이버 확인
nvidia-smi
# → CUDA Version: 12.x, GPU 이름, VRAM 확인

# 없으면 설치 (Ubuntu)
sudo apt update
sudo apt install -y nvidia-driver-560  # 또는 최신 버전
# WSL2는 Windows 측 드라이버만 설치하면 됨 (Linux 측 별도 설치 불필요)
```

---

## 2. 시스템 패키지 설치

```bash
sudo apt update
sudo apt install -y \
  git python3.11 python3.11-venv python3-pip \
  ffmpeg \
  build-essential
```

**ffmpeg**: 영상 프레임 추출, WebM 변환, 수치 검증에 필수.

---

## 3. 레포지토리 클론

### 3A. engine (헥사고널 아키텍처)

```bash
cd ~
git clone https://github.com/discoverex/engine.git
cd engine
git checkout wan/test  # animate 이식 브랜치
```

### 3B. anim_pipeline (sprite_gen 운영 스크립트)

```bash
cd ~
# anim_pipeline은 engine과 별도 프로젝트
# 이미 ~/anim_pipeline 경로에 존재하는 경우 클론 불필요
# 별도 레포에서 클론하는 경우:
git clone <anim_pipeline_repo_url> anim_pipeline
cd anim_pipeline
```

---

## 4. Python 가상환경 설정

### 4A. engine

```bash
cd ~/engine

# uv 설치 (없으면)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치 (tracking + dev + animate)
just init
uv sync --extra tracking --extra dev --extra animate
# → google-genai, scipy, pytest, mypy, ruff 등 설치됨

# 검증
just test
# → all passed, 0 failed 확인
```

### 4B. anim_pipeline (sprite_gen)

```bash
cd ~/anim_pipeline
python3.11 -m venv animVenv
source animVenv/bin/activate

pip install \
  flask flask-cors \
  google-genai \
  pillow \
  numpy \
  scipy \
  requests
```

---

## 5. ComfyUI 설치

### 5.1 ComfyUI 본체

```bash
cd ~
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# 특정 버전 고정 (운영 환경과 동일)
git checkout eb011733

# Python 가상환경
python3.11 -m venv venv
source venv/bin/activate

# PyTorch (CUDA 12.x)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# ComfyUI 의존성
pip install -r requirements.txt
```

### 5.2 ComfyUI 커스텀 노드

```bash
cd ~/ComfyUI/custom_nodes

# GGUF 모델 지원 (WAN 양자화 모델 로드용)
git clone https://github.com/city96/ComfyUI-GGUF.git

# VHS (Video Helper Suite — 비디오 출력)
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git

# 각 노드 의존성 설치
cd ComfyUI-GGUF && pip install -r requirements.txt && cd ..
cd ComfyUI-VideoHelperSuite && pip install -r requirements.txt && cd ..
```

### 5.3 WAN 모델 다운로드

```bash
cd ~/ComfyUI/models

# WAN I2V 14B (GGUF 양자화)
# 12GB VRAM → Q3_K_S (6.5GB) 권장
mkdir -p diffusion_models
cd diffusion_models
# huggingface에서 다운로드:
wget https://huggingface.co/city96/WAN2.1-I2V-14B-480P-GGUF/resolve/main/wan2.1-i2v-14b-480p-Q3_K_S.gguf

# CLIP Vision
cd ~/ComfyUI/models/clip_vision
wget https://huggingface.co/openai/clip-vit-large-patch14/resolve/main/model.safetensors -O clip_vision_h.safetensors
# 또는 ComfyUI 모델 관리자에서 다운로드

# VAE
cd ~/ComfyUI/models/vae
# WAN 2.1 VAE
wget https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/resolve/main/vae/wan_2.1_vae.safetensors

# CLIP Text (UMT5)
cd ~/ComfyUI/models/text_encoders
wget https://huggingface.co/Comfy-Org/WAN_2.1_ComfyUI/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
```

### 5.4 워크플로우 파일

```bash
mkdir -p ~/ComfyUI/user/default/workflows

# wan21_native_i2v_1.json 워크플로우
# anim_pipeline 레포에 포함되어 있으면:
cp ~/anim_pipeline/workflows/wan21_native_i2v_1.json \
   ~/ComfyUI/user/default/workflows/

# 없으면 ComfyUI 웹 UI에서 직접 구성 후 저장
```

### 5.5 ComfyUI 실행 테스트

```bash
cd ~/ComfyUI && source venv/bin/activate
python main.py --listen

# → http://127.0.0.1:8188 접속 확인
# → 모델 로드 테스트 (웹 UI에서 워크플로우 로드 → 실행)
# Ctrl+C로 종료
```

---

## 6. Gemini API 키 발급

```bash
# Google AI Studio에서 API 키 발급:
# https://aistudio.google.com/apikey

# 환경 변수 설정 (.bashrc 또는 .zshrc에 추가)
echo 'export GEMINI_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc

# 검증
python3 -c "
from google import genai
client = genai.Client(api_key='$(echo $GEMINI_API_KEY)')
print('Gemini API 연결 성공')
"
```

---

## 7. 실행

### 7A. sprite_gen 대시보드 (현재 운영 방식)

```bash
# 터미널 1 — ComfyUI
cd ~/ComfyUI && source venv/bin/activate
python main.py --listen

# 터미널 2 — WAN 대시보드
cd ~/anim_pipeline && source animVenv/bin/activate
PYTHONPATH=~/anim_pipeline python image_pipeline/sprite_gen/wan_server.py
# → http://localhost:5001 접속
```

대시보드에서:
1. 파일 브라우저로 이미지 선택
2. Stage 1 분류 실행
3. 모션 생성 (WAN I2V)
4. 영상 선택 → Lottie 변환
5. 키프레임 편집 → 내보내기 (📦통합/🎬모션/🔑키프레임)

### 7B. engine CLI (헥사고널 아키텍처)

```bash
# Dummy 어댑터로 실행 (GPU 불필요, 설치 확인용)
cd ~/engine && source .venv/bin/activate
bin/cli animate --image-path /path/to/image.png

# 실제 어댑터로 실행 (ComfyUI + Gemini 필요)
# ※ ComfyUI 어댑터 구현 후 (현재 미구현)
export GEMINI_API_KEY="your-key"
bin/cli animate \
  --image-path /path/to/image.png \
  -o flows/animate=animate_pipeline \
  -o models/mode_classifier=gemini \
  -o models/vision_analyzer=gemini \
  -o models/ai_validator=gemini \
  -o models/post_motion_classifier=gemini \
  -o models/animation_generation=comfyui
```

---

## 8. 검증 체크리스트

```bash
# ── 1. 시스템 ─────────────────────────────
nvidia-smi                           # GPU 확인
ffmpeg -version                      # ffmpeg 확인
python3.11 --version                 # Python 확인

# ── 2. engine ─────────────────────────────
cd ~/engine
just test                            # all passed 확인
uv run discoverex animate --help     # CLI 도움말 확인 (--image-path 인자 포함)

# ── 3. anim_pipeline ─────────────────────
cd ~/anim_pipeline && source animVenv/bin/activate
python -c "from image_pipeline.sprite_gen.wan_backend import WanBackend; print('OK')"

# ── 4. ComfyUI ────────────────────────────
curl -s http://127.0.0.1:8188/system_stats | python3 -m json.tool
# → ComfyUI 응답 확인 (서버 실행 중일 때)

# ── 5. Gemini ─────────────────────────────
python3 -c "
from google import genai
c = genai.Client(api_key='$(echo $GEMINI_API_KEY)')
r = c.models.generate_content(model='gemini-2.5-flash', contents='hello')
print('Gemini OK:', r.text[:50])
"

# ── 6. WAN 모델 ──────────────────────────
ls -lh ~/ComfyUI/models/diffusion_models/wan*.gguf
# → wan2.1-i2v-14b-480p-Q3_K_S.gguf (6.5GB) 확인
```

---

## 9. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `nvidia-smi` 실패 | 드라이버 미설치 | WSL: Windows 드라이버 업데이트. Linux: `apt install nvidia-driver-560` |
| ComfyUI `torch.cuda.is_available() = False` | PyTorch CUDA 미스매치 | `pip install torch --index-url https://download.pytorch.org/whl/cu124` |
| `ModuleNotFoundError: google.genai` | google-genai 미설치 | `pip install google-genai` |
| `ffmpeg: command not found` | ffmpeg 미설치 | `sudo apt install ffmpeg` |
| ComfyUI `Model not found` | WAN GGUF 모델 경로 오류 | `~/ComfyUI/models/diffusion_models/`에 파일 확인 |
| `VRAM OOM` | GPU 메모리 부족 | Q3_K_S (6.5GB) 사용, 다른 GPU 프로세스 종료 |
| `Gemini 429 Resource Exhausted` | API 레이트 리밋 | 1-2분 대기 후 재시도, 또는 API 키 풀링 |
| `wan_server.py import error` | PYTHONPATH 미설정 | `PYTHONPATH=~/anim_pipeline python ...` |
| pytest 실패 (engine) | animate extra 미설치 | `pip install -e ".[animate]"` |

---

## 10. 디렉토리 구조 요약

```
~/
├── engine/                          # 헥사고널 아키텍처 (git: wan/test)
│   ├── src/discoverex/              # 메인 코드
│   ├── conf/                        # Hydra 설정
│   ├── tests/                       # 234개 테스트
│   ├── bin/cli                      # CLI 진입점
│   └── pyproject.toml               # 의존성 (animate extra 포함)
│
├── anim_pipeline/                   # sprite_gen 운영 스크립트 (git: wan/test)
│   ├── image_pipeline/sprite_gen/   # WAN 파이프라인 13개 파일
│   ├── outputs/wan/                 # 생성 결과물
│   └── animVenv/                    # Python 가상환경
│
└── ComfyUI/                         # WAN I2V 생성 서버
    ├── models/                      # WAN GGUF, CLIP, VAE 모델
    ├── custom_nodes/                # GGUF + VHS 노드
    ├── user/default/workflows/      # 워크플로우 JSON
    └── venv/                        # Python 가상환경
```
