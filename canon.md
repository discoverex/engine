# Discoverex Scene Canonical Spec v1 (엄밀 정의)

> 목적

* 생성/검증/UX/학습 준비 전 파이프라인이 공통으로 사용하는 **단일 Scene 표현**
* 파이프라인 조합이 늘어나도 흔들리지 않는 **전역 계약(Contract)**
* 현재 버전은 **Region-first + bbox-only**

---

## 1) 용어

* Scene: 배경 + 배치된 구성 + 목표/정답 + 검증 결과를 포함한 퍼즐 아이템 1개
* Region: Scene 좌표계 상의 2D 영역. 현재는 bbox만 사용
* AssetRef: 파일/오브젝트스토리지/URL 등 외부 저장소의 참조 문자열
* Signals: 스코어 산출에 사용된 요약 신호(수치/카운트/간단 통계). 상세 정책은 비포함

---

## 2) 전역 불변 조건(Invariants)

* Scene은 항상 `scene_id`와 `version_id`를 가진다
* 좌표는 **background 이미지의 절대 픽셀 좌표계** 기준이다
* Region geometry는 현재 **bbox-only**
* Answer는 **Region 기반**이다: `answer.answer_region_ids`가 정답의 유일한 판정 기준이다
* Verification은 score 중심이며, `final.pass`는 `logical.pass`와 `perception.pass`에 의해 결정된다(결정 정책 자체는 외부 정책)
* `meta.model_versions`는 실행에 사용된 모델/컴포넌트 버전을 기록한다

---

## 3) 데이터 타입

* `ID`: 문자열. 충돌 방지 목적(예: ULID/UUID). 구체 포맷은 미정
* `Timestamp`: ISO 8601 문자열
* `Score`: 실수(float). 범위는 정책에 의해 정의
* `PassFlag`: boolean
* `JsonDict`: JSON object
* `StringMap`: `{ string: string }`

---

## 4) 최상위 구조

### 4.1 Scene

필수 필드:

* `meta: Meta`
* `background: Background`
* `regions: Region[]` (빈 배열 허용. 단, answer가 존재하면 해당 region_id는 존재해야 함)
* `composite: Composite` (최소 final_image_ref 필요)
* `goal: Goal` (구조만. 정책 상세 미정)
* `answer: Answer`
* `verification: VerificationBundle`
* `difficulty: Difficulty`

선택 필드:

* `objects: ObjectGroup[]` (의미/관계용 grouping. 판정 기준 아님)

---

## 5) Meta

### 5.1 Meta

필수:

* `scene_id: ID`
* `version_id: ID`
* `status: "candidate" | "approved" | "failed"`
* `pipeline_run_id: ID` (해당 Scene version을 생성/갱신한 실행 단위)
* `config_version: string` (생성/검증 정책 묶음 버전. 예: "v1")
* `model_versions: StringMap` (키 예: "hidden_region", "inpaint", "perception", "fx")
* `created_at: Timestamp`
* `updated_at: Timestamp`

권장(옵션):

* `parent_version_id?: ID` (편집/재생성 등으로 파생된 경우)
* `tags?: string[]` (목표 유형 등 검색용)
* `notes?: string` (사람 메모)

불변:

* `scene_id`는 동일 퍼즐 아이템 계열에서 고정, `version_id`는 변경마다 새로 발급

---

## 6) Background

### 6.1 Background

필수:

* `asset_ref: AssetRef`
* `width: int` (px)
* `height: int` (px)

권장(옵션):

* `metadata?: JsonDict` (촬영/출처/라이선스/해상도 등)

---

## 7) Region

### 7.1 Region

필수:

* `region_id: ID`
* `geometry: Geometry`
* `role: "candidate" | "distractor" | "answer" | "object"`
* `source: "candidate_model" | "inpaint" | "fx" | "manual"`
* `attributes: JsonDict` (예: 점수, 임베딩, occlusion ratio 등)
* `version: int` (region 자체 변경 카운트. Scene version과 별개)

선택:

* `linked_object_id?: ID` (ObjectGroup과 연결)

불변/제약:

* geometry 좌표는 background 기준
* bbox는 이미지 경계를 넘지 않는 것을 권장(필수 여부는 정책)

### 7.2 Geometry (bbox-only)

필수:

* `type: "bbox"`
* `bbox: BBox`

미래 확장 슬롯(미구현, 저장만 가능):

* `mask_ref?: AssetRef`

### 7.3 BBox

필수:

* `x: float`
* `y: float`
* `w: float`
* `h: float`

의미:

* (x, y)는 좌상단 기준
* w/h는 양수
* 단위는 px

---

## 8) ObjectGroup (선택)

### 8.1 ObjectGroup

목적:

* 관계/의미 목표에서 여러 region을 하나의 “개념적 객체”로 묶기 위한 보조 구조
* 판정은 region 기준이므로 없어도 됨

필수:

* `object_id: ID`
* `region_ids: ID[]` (해당 Scene.regions에 존재해야 함)

선택:

* `type?: string`
* `properties?: JsonDict`

---

## 9) Composite

### 9.1 Composite

필수:

* `final_image_ref: AssetRef`

권장(옵션):

* `render_meta?: JsonDict` (합성 파라미터 요약, 레이어 링크 등)

---

## 10) Goal

### 10.1 Goal

필수:

* `goal_type: "relation" | "count" | "shape" | "semantic"`
* `constraint_struct: JsonDict` (정책 미정. 구조만 담는다)
* `answer_form: "region_select" | "click_one" | "click_multiple"`

선택:

* `scope_region_ids?: ID[]` (목표 적용 범위를 특정 region 집합으로 제한)

불변:

* Goal은 “검증 가능하도록 구조화된 정보”를 담는다. 문장 여부는 비중요

---

## 11) Answer

### 11.1 Answer

필수:

* `answer_region_ids: ID[]`
* `uniqueness_intent: true`

제약:

* `answer_region_ids`는 Scene.regions 내 region_id의 부분집합
* 현재 기본은 단일 정답을 목표로 하나, 수량 목표를 위해 복수 region도 허용
* 단, 정답 집합 자체는 1개로 수렴해야 함(유일성)

---

## 12) Verification

### 12.1 VerificationBundle

필수:

* `logical: VerificationPart`
* `perception: VerificationPart`
* `final: VerificationFinal`

### 12.2 VerificationPart

필수:

* `score: Score`
* `pass: PassFlag`
* `signals: JsonDict` (예: 후보 수, 혼동 위험 수치 등. 상세 정책은 비포함)

### 12.3 VerificationFinal

필수:

* `total_score: Score`
* `pass: PassFlag`
* `failure_reason: string` (pass면 "" 허용)

제약:

* `failure_reason`는 사람이 읽을 수 있는 요약 문자열
* 별도의 표준 코드 체계는 추후 확정(현재는 string)

---

## 13) Difficulty

### 13.1 Difficulty

필수:

* `estimated_score: Score`
* `source: "rule_based" | "learned"`

권장(옵션):

* `calibration_version?: string`

---

## 14) 저장/참조 규칙(최소)

* Scene은 **단일 JSON**으로 직렬화 가능해야 함
* AssetRef는 다음 중 하나를 지원

  * 로컬 경로(개발)
  * S3/MinIO 경로(협업)
  * 기타 URL
* 권장 디렉토리 규칙(로컬 기준)

  * `artifacts/scenes/{scene_id}/{version_id}/scene.json`
  * `.../composite.png`
  * `.../verification.json` (scene.json에서 파생 가능)

---

## 15) 버전 업그레이드 규칙

* 스키마 변경 시 `config_version`과 별도로 `schema_version` 필드 도입 가능
* v1에서는 schema_version 생략(암묵 v1)

---

## 16) 비목표(명시)

* 세그멘테이션(mask) 계산/판정 로직은 v1에서 구현하지 않는다
* constraint_struct 내부 구조/정책(임계값/규칙)은 본 문서 범위가 아니다
* 모델 학습/데이터셋 설계는 본 문서 범위가 아니다
tmuix