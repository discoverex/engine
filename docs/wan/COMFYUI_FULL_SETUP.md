# ComfyUI + WAN I2V — WSL 환경 설치 가이드

> 대상: Windows WSL2에서 ComfyUI + WAN 2.1 모델 설치
> 최종 검증일: 2026-03-09 (RTX 5070 Ti, Ubuntu 24.04, CUDA 12.6, Python 3.12)

---

## 전체 흐름 요약

```
[1] WSL2 + Ubuntu 설치
    ↓
[2] NVIDIA 드라이버 확인 + CUDA Toolkit 설치
    ↓
[3] 시스템 패키지 설치 (python3, ffmpeg, git)
    ↓
[4] ComfyUI 설치 (별도 가상환경)
    ↓
[5] ComfyUI 커스텀 노드 설치
    ↓
[6] WAN 모델 4종 다운로드 + 경로 정리
    ↓
[7] Real-ESRGAN 업스케일 모델 설치
    ↓
[8] 실행 확인
```

---

## 1. WSL2 + Ubuntu 설치

Windows PowerShell (관리자 권한)에서 실행:

```powershell
wsl --install -d Ubuntu-24.04
```

설치 후 Ubuntu 터미널이 열리면 사용자 이름과 비밀번호를 설정합니다.
이후 모든 작업은 Ubuntu 터미널에서 진행합니다.

WSL 버전 확인 (PowerShell에서):

```powershell
wsl -l -v
```

VERSION이 **2**인지 확인합니다. 1이면:

```powershell
wsl --set-version Ubuntu-24.04 2
```

### 1-1. .wslconfig 설정 (RAM 16GB 환경 필수)

RAM이 16GB인 경우 스왑 설정이 필수입니다.
Windows에서 `C:\Users\<사용자명>\.wslconfig` 파일을 생성합니다:

```ini
[wsl2]
memory=14GB
swap=16GB
```

적용:

```powershell
wsl --shutdown
```

WSL 재시작하면 적용됩니다. 스왑 파일은 기본 경로에 자동 생성됩니다.

---

## 2. NVIDIA 드라이버 확인 + CUDA Toolkit 설치

### 2-1. Windows 측 NVIDIA 드라이버

WSL2에서 GPU를 사용하려면 **Windows 측에** 최신 NVIDIA 드라이버가 설치되어 있어야 합니다.
WSL2 내부에는 별도로 드라이버를 설치하지 않습니다.

Windows PowerShell에서 확인:

```powershell
nvidia-smi
```

드라이버 버전이 **470 이상**이어야 WSL2 GPU 패스스루를 지원합니다.

### 2-2. WSL2 내부에서 GPU 인식 확인

Ubuntu 터미널에서:

```bash
nvidia-smi
```

> ⚠️ "GPU access blocked by the operating system" 에러 시:
> PowerShell에서 `wsl --shutdown` 실행 후 Ubuntu를 다시 열면 해결됩니다.

### 2-3. CUDA Toolkit 설치 (WSL2 내부)

```bash
# CUDA 키링 설치
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update

# CUDA Toolkit 설치
# ⚠️ cuda-toolkit-12-4는 Ubuntu 24.04에서 libtinfo5 의존성 문제로 설치 실패
# cuda-toolkit-12-6 사용
sudo apt install -y cuda-toolkit-12-6

# 환경변수 추가
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# 설치 확인
nvcc --version
```

> 주의: WSL2에서는 `wsl-ubuntu` 저장소를 사용합니다 (`ubuntu2404`가 아님).

> ⚠️ `dpkg: error: dpkg frontend lock was locked by another process` 에러 시:
> `unattended-upgrades` 자동 업데이트가 실행 중입니다. 잠시 기다리거나:
> ```bash
> sudo lsof /var/lib/dpkg/lock-frontend  # PID 확인
> sudo kill <PID>                         # 프로세스 종료 후 재시도
> ```

---

## 3. 시스템 패키지 설치

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    git \
    build-essential \
    nano
```

설치 확인:

```bash
ffmpeg -version | head -1
python3 --version
```

| 패키지 | 용도 |
|---|---|
| python3, pip, venv | Python 실행 + 가상환경 |
| ffmpeg | 영상 프레임 추출, 재인코딩, APNG 생성 |
| git | 코드 클론 + 버전 관리 |
| build-essential | C 확장 빌드 (numpy 등) |
| nano | 텍스트 편집기 |

---

## 4. ComfyUI 설치

ComfyUI는 WAN 모델을 실행하는 **별도 서버**입니다.

```bash
cd ~
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# ⚠️ ComfyUI 버전 고정 (필수)
# 최신 버전(0.16.x)은 12GB VRAM 환경에서 생성 도중 85% 부근에서
# GPU-Util 0%, VRAM 풀 상태로 행(hang)이 발생하는 메모리 관리 문제가 있음.
# v0.15.1 (커밋 eb011733)은 12GB VRAM에서 정상 동작이 검증된 버전.
git checkout eb011733

# ComfyUI 전용 가상환경
python3 -m venv venv
source venv/bin/activate

# pip 업그레이드
pip install --upgrade pip

# PyTorch 설치
# ⚠️ GPU 아키텍처에 따라 설치 명령이 다릅니다
#
# RTX 50XX 시리즈 (Blackwell, sm_120) → cu128 nightly 권장
#   stable(2.10.0)은 sm_120 최적화가 부족하여 생성 속도가 ~50% 느림
#   nightly(2.12.0.dev+)는 Blackwell 최적화 포함 → 정상 속도
# RTX 40XX 시리즈 (Ada Lovelace, sm_89) → cu126 stable 이상
# RTX 30XX 시리즈 (Ampere, sm_86) → cu124 stable 이상
#
# 확인 방법: nvidia-smi로 GPU 이름 확인

# RTX 50XX (Blackwell) — cu128 nightly (권장, 최적화 포함)
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

# RTX 50XX (Blackwell) — cu128 stable (동작하지만 ~50% 느림)
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# RTX 40XX 이하 — cu126 stable
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126

# 설치 후 GPU 호환성 확인
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
# True와 GPU 이름이 출력되면 정상
# RTX 50XX는 버전이 2.12.0.dev 이상이어야 최적 성능

# ComfyUI 의존성 설치
pip install -r requirements.txt
```

---

## 5. ComfyUI 커스텀 노드 설치

ComfyUI venv가 활성화된 상태에서 진행합니다.

```bash
cd ~/ComfyUI/custom_nodes

# GGUF 로더 — WAN 양자화 모델(.gguf) 로드용
git clone https://github.com/city96/ComfyUI-GGUF.git
cd ComfyUI-GGUF && pip install -r requirements.txt && cd ..

# Video Helper Suite — 영상 출력(mp4) 생성용
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
cd ComfyUI-VideoHelperSuite && pip install -r requirements.txt && cd ..
```

---

## 6. WAN 모델 다운로드 + 경로 정리

5개 모델 파일을 ComfyUI의 models 디렉토리에 다운로드합니다 (WAN 4종 + 업스케일 1종).
ComfyUI venv가 활성화된 상태에서 진행합니다.

```bash
cd ~/ComfyUI/models
```

### 6-1. 모델 다운로드 (하나씩 순서대로 실행)

```bash
# (1) WAN I2V UNet — 영상 생성 본체 (~8GB, 약 7분)
mkdir -p unet
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('city96/Wan2.1-I2V-14B-480P-gguf', 'wan2.1-i2v-14b-480p-Q3_K_S.gguf', local_dir='unet/')
"

# (2) CLIP Vision — 이미지 인코더 (~1.2GB, 약 1분)
mkdir -p clip_vision
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/Wan_2.1_ComfyUI_repackaged', 'split_files/clip_vision/clip_vision_h.safetensors', local_dir='clip_vision/')
"

# (3) CLIP 텍스트 인코더 (~6.3GB, 약 6분)
mkdir -p clip
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/Wan_2.1_ComfyUI_repackaged', 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', local_dir='clip/')
"

# (4) VAE — 디코더 (~243MB, 약 15초)
mkdir -p vae
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/Wan_2.1_ComfyUI_repackaged', 'split_files/vae/wan_2.1_vae.safetensors', local_dir='vae/')
"
```

### 6-2. 파일 경로 정리

HuggingFace에서 다운로드하면 (2)(3)(4)가 `split_files/` 하위 폴더에 저장됩니다.
ComfyUI가 모델을 찾을 수 있도록 올바른 위치로 이동합니다.

```bash
# 파일 이동
mv clip_vision/split_files/clip_vision/clip_vision_h.safetensors clip_vision/
mv clip/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors clip/
mv vae/split_files/vae/wan_2.1_vae.safetensors vae/

# 빈 폴더 정리
rm -rf clip_vision/split_files clip/split_files vae/split_files
```

### 6-3. 최종 경로 확인

```bash
ls -lh unet/wan2.1-i2v-14b-480p-Q3_K_S.gguf
ls -lh clip_vision/clip_vision_h.safetensors
ls -lh clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors
ls -lh vae/wan_2.1_vae.safetensors
```

4개 파일이 모두 각 폴더 바로 아래에 있으면 정상입니다.

| 파일 | 크기 | 경로 |
|---|---|---|
| WAN UNet | ~7.4GB | `models/unet/wan2.1-i2v-14b-480p-Q3_K_S.gguf` |
| CLIP Vision | ~1.2GB | `models/clip_vision/clip_vision_h.safetensors` |
| CLIP Text | ~6.3GB | `models/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| VAE | ~243MB | `models/vae/wan_2.1_vae.safetensors` |
| Real-ESRGAN x4 | ~64MB | `models/upscale_models/RealESRGAN_x4plus.pth` |

---

## 7. Real-ESRGAN 업스케일 모델 설치

### 7-1. 왜 필요한가?

WAN I2V 모델은 **480×480** 해상도로 학습되었습니다. 입력 이미지가 이 크기보다 작으면 480×480 캔버스에 배치하는데, **원본이 매우 작은 경우(예: 60×83px)** 스프라이트가 캔버스의 2~3%만 차지하여 다음 문제가 발생합니다:

- WAN이 모션을 제대로 생성하지 못함 (대상이 너무 작음)
- Ghosting 아티팩트 발생
- 모션 검증(수치 검증) 실패율 증가

**해결 방식**: 소형 이미지를 WAN에 전달하기 전에 **Real-ESRGAN 4x** AI 초해상도 모델로 업스케일하여 적절한 크기로 만든 후 캔버스에 배치합니다.

### 7-2. VRAM 영향

Real-ESRGAN은 **WAN 모션 생성 이전 단계**에서 실행되며, ComfyUI가 자동으로 VRAM을 관리합니다:

```
[Real-ESRGAN 로드]  ██░░░░░░░░░░  (~64MB, GPU)
[업스케일 실행]     ████░░░░░░░░  (타일 512×512 단위)
[ESRGAN 해제]       ░░░░░░░░░░░░  (finally 블록에서 즉시 CPU로 이동)
[VRAM 캐시 정리]    ░░░░░░░░░░░░  (torch.cuda.empty_cache)
[WAN I2V 로드]      ░░░░████████  (~8GB, ESRGAN과 겹치지 않음)
```

- `nodes_upscale_model.py`의 `finally` 블록에서 **실행 즉시 GPU → CPU 이동**
- WAN 로드 시 `load_models_gpu()`가 `free_memory()` 호출하여 **이중 안전장치**
- 소형 이미지는 타일 1개로 처리 → 작업 VRAM 극소
- **WAN 생성에 VRAM 영향 없음**

### 7-3. 모델 다운로드

```bash
cd ~/ComfyUI/models/upscale_models

# Real-ESRGAN x4 모델 다운로드 (~64MB, 수초)
wget -O RealESRGAN_x4plus.pth \
  "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
```

### 7-4. 설치 확인

```bash
ls -lh ~/ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth
# -rw-r--r-- 64M RealESRGAN_x4plus.pth 가 출력되면 정상
```

### 7-5. 모델 정보

| 항목 | 값 |
|------|-----|
| 모델 | RealESRGAN_x4plus |
| 파일 크기 | ~64MB |
| 업스케일 배율 | 4x (고정) |
| 처리 방식 | 타일(512×512) 단위, OOM 시 타일 자동 축소 |
| VRAM 사용 | ~200MB (소형 이미지 기준, 타일 1개) |
| 용도 | 소형 스프라이트(~200px 이하) → WAN 입력 전 품질 보존 업스케일 |
| 적합 대상 | 일러스트, 사진, 벡터 이미지 |
| 부적합 대상 | 픽셀아트 (nearest-neighbor 방식이 더 적합) |

> **참고**: 이 모델은 ComfyUI의 `ImageUpscaleWithModel` 노드에서 사용됩니다.
> Spandrel 라이브러리가 모델을 자동으로 인식하므로 별도 설정은 필요 없습니다.

---

## 8. 실행 확인

### ComfyUI 서버 시작

```bash
cd ~/ComfyUI
source venv/bin/activate
python main.py --listen 0.0.0.0 --port 8188
```

정상 실행 시 아래 메시지가 출력됩니다:

```
Starting server
To see the GUI go to: http://0.0.0.0:8188
```

### VRAM별 실행 옵션

| VRAM | ComfyUI 실행 명령어 | 비고 |
|------|---------------------|------|
| 12GB+ | `python main.py --listen 0.0.0.0 --port 8188` | 기본 |
| 6~12GB | `python main.py --listen 0.0.0.0 --port 8188 --lowvram` | UNet 레이어별 GPU↔CPU 스왑, 2~3배 느림 |
| 6GB 이하 | `python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 1.0` | VRAM 1GB 예약, 안정성 우선 |

---

## 트러블슈팅

### nvidia-smi: "GPU access blocked by the operating system"

WSL을 완전 재시작하면 해결됩니다.

```powershell
# Windows PowerShell에서
wsl --shutdown
```

이후 Ubuntu를 다시 열고 `nvidia-smi` 확인.

### nvidia-smi가 아예 없음

Windows 측 NVIDIA 드라이버가 설치되지 않았거나, WSL1을 사용 중일 수 있습니다.

```powershell
# PowerShell에서 WSL 버전 확인
wsl -l -v
# VERSION이 2인지 확인
```

### cuda-toolkit-12-4 설치 실패 (libtinfo5)

Ubuntu 24.04에서 `libtinfo5` 의존성 문제가 발생합니다. **cuda-toolkit-12-6**을 설치합니다.

```bash
sudo apt install -y cuda-toolkit-12-6
```

### dpkg lock 에러

`unattended-upgrades` 자동 업데이트가 실행 중입니다.

```bash
sudo lsof /var/lib/dpkg/lock-frontend  # PID 확인
sudo kill <PID>                         # 종료 후 재시도
```

### huggingface-cli: command not found

`huggingface-hub` 버전에 따라 CLI가 PATH에 등록되지 않을 수 있습니다.
Python 코드로 직접 다운로드합니다 (6단계 참조).

### ComfyUI에서 모델을 찾지 못함

HuggingFace 다운로드 시 `split_files/` 하위 폴더가 생성됩니다.
파일을 올바른 위치로 이동해야 합니다 (6-2단계 참조).

### ComfyUI 시작 시 torch 관련 에러

PyTorch와 GPU 아키텍처가 맞지 않을 수 있습니다.

**증상 1 — "CUDA capability sm_120 is not compatible":**
RTX 50XX (Blackwell) GPU에 cu126 이하 PyTorch를 설치한 경우. cu128 이상이 필요합니다.

**증상 2 — "no kernel image is available for execution on the device":**
위 호환성 문제로 CUDA 커널이 실행되지 않는 경우. ComfyUI가 2~4초 만에 완료되고 비디오 파일이 생성되지 않습니다.

**해결:**

```bash
cd ~/ComfyUI && source venv/bin/activate
pip uninstall torch torchvision torchaudio -y

# RTX 50XX → cu128 nightly (권장)
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

# RTX 40XX 이하 → cu126
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126

# 호환성 확인
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

### ComfyUI 생성 속도가 비정상적으로 느림 (RTX 50XX)

PyTorch stable(2.10.0+cu128)을 사용하면 Blackwell 최적화가 부족하여 생성 속도가 약 50% 느려집니다.

**해결:** PyTorch nightly를 설치합니다.

```bash
cd ~/ComfyUI && source venv/bin/activate
pip uninstall torch torchvision torchaudio -y
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

# 버전 확인 — 2.12.0.dev 이상이어야 최적 성능
python -c "import torch; print(torch.__version__)"
```

### VRAM 부족 (Out of Memory)

Q3_K_S 모델(~8GB)은 VRAM 10GB 이상을 권장합니다.
VRAM이 부족한 경우 `--lowvram` 플래그를 사용합니다:

```bash
python main.py --listen 0.0.0.0 --port 8188 --lowvram
```

6GB VRAM 환경에서는 추가로 `--reserve-vram` 옵션을 사용합니다:

```bash
python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 1.0
```

### ComfyUI 생성 중 85%에서 행(hang) 발생

**증상:** 생성 진행률이 85% (17/20 steps) 부근에서 멈추고, `nvidia-smi` 확인 시
VRAM이 거의 차있지만(~9500MB/12227MB) GPU-Util이 0%인 상태.

**원인:** ComfyUI v0.16.x의 메모리 관리 방식이 12GB VRAM 환경에서 문제를 일으킵니다.

**해결:** ComfyUI를 검증된 버전(v0.15.1, 커밋 `eb011733`)으로 고정합니다.

```bash
cd ~/ComfyUI
git checkout eb011733
```

이미 v0.16.x로 실행한 적이 있어 DB 에러가 발생하면:

```bash
rm ~/ComfyUI/user/comfyui.db ~/ComfyUI/user/comfyui.db.lock
```

### Gemini API 429 Rate Limit

Google AI Studio 무료 티어의 분당 요청 제한입니다.
잠시 후 재실행하거나 유료 플랜을 사용합니다.

### WSL OOM으로 종료됨 (RAM 16GB 환경)

텍스트 인코더 CPU 오프로드(~6.4GB) 사용 시 RAM이 부족하여 WSL이 종료될 수 있습니다.

**해결:**

1. `.wslconfig`에 스왑 설정 (1-1단계 참조)
2. 불필요한 프로세스 최소화 (브라우저 탭 등)
3. ComfyUI + Engine 외 다른 프로세스 종료

---

## 하드웨어 요구사항 요약

| 항목 | 최소 | 권장 |
|---|---|---|
| OS | Windows 10 21H2+ (WSL2) | Windows 11 |
| GPU | NVIDIA, VRAM 6GB+ (`--lowvram` 필수) | VRAM 12GB+ |
| RAM | 16GB (스왑 16GB 필수) | 32GB |
| 디스크 | 40GB (모델 포함) | 60GB+ |
| Python | 3.10+ | 3.12 |
| CUDA Toolkit | 12.6 | 12.6 |

### VRAM별 구성

| VRAM | ComfyUI 옵션 | 텍스트 인코더 | 생성 속도 |
|------|-------------|-------------|----------|
| 12GB+ | 기본 | GPU | 정상 (~5분) |
| 8~12GB | 기본 | CPU 오프로드 | 정상 (~5분) |
| 6~8GB | `--lowvram` | CPU 오프로드 | 느림 (~10~15분) |
| 6GB 이하 | `--lowvram --reserve-vram 1.0` | CPU 오프로드 | 느림 (~10~15분) |

---

## 검증 완료 환경

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 5070 Ti Laptop (12GB VRAM, Blackwell sm_120) |
| OS | Ubuntu 24.04 on WSL2 (WSL 2.6.3) |
| Windows 드라이버 | 595.71 |
| CUDA Toolkit | 12.6 (V12.6.85) |
| Python | 3.12.3 |
| PyTorch | 2.12.0.dev+cu128 (nightly, Blackwell 최적화) |
| ComfyUI | v0.15.1 커밋 `eb011733` (버전 고정 필수) |

> ⚠️ RTX 50XX는 CUDA capability sm_120으로, PyTorch cu126 이하는 sm_90까지만 지원합니다.
> 반드시 cu128 이상을 설치해야 하며, **nightly 버전(2.12.0.dev+)**을 권장합니다.
> stable(2.10.0+cu128)은 동작하지만 최적화 부족으로 생성 속도가 약 50% 느립니다.
>
> ⚠️ ComfyUI v0.16.x는 12GB VRAM에서 생성 중 행(hang)이 발생합니다.
> 반드시 v0.15.1(커밋 `eb011733`)로 고정해야 합니다.

---

## 실행 명령어 (ComfyUI + Engine)

두 개의 터미널이 필요합니다. ComfyUI 서버를 먼저 실행한 후 Engine 대시보드를 실행합니다.

### VRAM 12GB+ (넉넉한 환경)

모든 모델을 GPU에 로드합니다. 최고 품질 + 정상 속도.

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate
python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine
cd ~/engine && export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui
```

| 컴포넌트 | 위치 | VRAM | RAM |
|----------|------|------|-----|
| UNet (14B Q3_K_S) | GPU | ~7.7GB | - |
| CLIPVision | GPU | ~1.2GB | - |
| 텍스트 인코더 | GPU | ~4.5GB | - |
| VAE | GPU | ~0.3GB | - |
| **합계** | | **~12GB** | **~6GB** |

### VRAM 8~12GB (텍스트 인코더 CPU 오프로드)

텍스트 인코더만 CPU(RAM)로 오프로드합니다. 품질 동일, 속도 동일.

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate
python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine
cd ~/engine && export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

| 컴포넌트 | 위치 | VRAM | RAM |
|----------|------|------|-----|
| UNet (14B Q3_K_S) | GPU | ~7.7GB | - |
| CLIPVision | GPU | ~1.2GB | - |
| 텍스트 인코더 | **CPU** | 0GB | ~6.4GB |
| VAE | GPU | ~0.3GB | - |
| **합계** | | **~9.2GB** | **~14GB** |

### VRAM 6~8GB (lowvram 모드)

ComfyUI `--lowvram`으로 UNet을 레이어별 GPU↔CPU 스왑합니다. 품질 동일, 속도 2~3배 느림.

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate
python main.py --listen 0.0.0.0 --port 8188 --lowvram

# 터미널 2: Engine
cd ~/engine && export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

| 컴포넌트 | 위치 | VRAM | RAM |
|----------|------|------|-----|
| UNet (14B Q3_K_S) | GPU↔CPU 스왑 | ~4-5GB | ~3-4GB |
| CLIPVision | GPU | ~1.2GB | - |
| 텍스트 인코더 | **CPU** | 0GB | ~6.4GB |
| VAE | GPU | ~0.3GB | - |
| **합계** | | **~5-6GB** | **~16GB (스왑 필수)** |

> ⚠️ RAM 16GB 환경에서는 `.wslconfig` 스왑 설정 필수 (1-1단계 참조)

### VRAM 6GB 이하 (lowvram + reserve-vram)

VRAM 예약으로 OOM을 방지합니다. 품질 동일, 속도 2~3배 느림.

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate
python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 1.0

# 터미널 2: Engine
cd ~/engine && export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

> `--reserve-vram 1.0`: VRAM 1GB를 시스템용으로 예약하여 5GB만 사용

### 실행 요약

| VRAM | ComfyUI 옵션 | Engine 프로필 | 품질 | 속도 |
|------|-------------|--------------|------|------|
| 12GB+ | 기본 | `animate_comfyui` | 최고 | ~5분 |
| 8~12GB | 기본 | `animate_comfyui_lowvram` | 최고 | ~5분 |
| 6~8GB | `--lowvram` | `animate_comfyui_lowvram` | 최고 | ~10~15분 |
| 6GB 이하 | `--lowvram --reserve-vram 1.0` | `animate_comfyui_lowvram` | 최고 | ~10~15분 |

### 전체 실행 명령어 (복사-붙여넣기용)

#### VRAM 12GB+ (넉넉한 환경)

```bash
# 터미널 1: ComfyUI 서버
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine 대시보드
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui
```

#### VRAM 8~12GB

```bash
# 터미널 1: ComfyUI 서버
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine 대시보드 (텍스트 인코더 CPU 오프로드)
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

#### VRAM 6~8GB

```bash
# 터미널 1: ComfyUI 서버 (UNet 레이어별 스왑)
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188 --lowvram

# 터미널 2: Engine 대시보드 (텍스트 인코더 CPU 오프로드)
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

#### VRAM 6GB 이하

```bash
# 터미널 1: ComfyUI 서버 (UNet 레이어별 스왑 + VRAM 1GB 예약)
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 1.0

# 터미널 2: Engine 대시보드 (텍스트 인코더 CPU 오프로드)
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```
