# Discoverex Context Index

이 문서는 `.context` 탐색 시작점입니다. 기술적 상세 정의와 아키텍처 결정을 담고 있습니다.

## 1. 핵심 기술 문서 (Primary Documents)

- [Scene Canonical Spec v1](canon.md): 제품/아키텍처의 기준 계약 (SSOT).
- [Architecture & Organization](architecture.md): 시스템 설계 원칙 및 모듈 레이어링 가이드.
- [Capabilities & Specs](capabilities.md): 현재 실행 능력, 생성 파이프라인 명세, 제약 사항.

## 2. 문서 사용 규칙

1. **규약 및 설계**: 아키텍처적 판단이나 데이터 규약은 `canon.md`와 `architecture.md`를 최우선으로 참고합니다.
2. **실행 가능성**: 현재 엔진이 무엇을 할 수 있는지, 생성 품질의 한계가 어디인지 파악하려면 `capabilities.md`를 확인합니다.
3. **개발 상태**: 최신 구현 현황과 후속 작업은 `docs/dev/handoff.md`에서 관리합니다.

## 3. 관련 링크 (Internal)

- [Git Conventions](git-conventions.md): 프로젝트 Git 사용 및 커밋 규칙.
- [Project Documentation Root](../README.md): 프로젝트 전체 문서 지도.
