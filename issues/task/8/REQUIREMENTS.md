# 모든 PR과 master push의 테스트 실행 요구사항

## 목적

GitHub Actions가 `master` 대상 PR에서만 테스트하던 제한을 제거해, 모든 대상 브랜치의 PR과 `master` push에서 테스트를 실행한다. 패키지 검증은 각 이벤트에서 수행하되, 버저닝 및 배포 관련 작업은 `master` push에만 허용한다.

## 범위

- 대상 파일: [CI 워크플로](../../../.github/workflows/ci.yml)
- GitHub Actions 이벤트 트리거, 테스트 job, 버전 계획·릴리즈 노트·배포 단계의 조건을 다룬다.
- 테스트 코드나 패키지 배포 방식 자체는 변경하지 않는다.

## 기능 요구사항

### CI-01: PR 트리거

- `pull_request` 이벤트는 대상 브랜치 필터 없이 설정한다.
- 모든 base branch로 생성되거나 갱신되는 PR에서 테스트 workflow가 실행되어야 한다.
- 테스트 여부를 변경 경로에 따라 조건부로 생략하지 않는다.

### CI-02: master push 트리거

- `push` 이벤트는 `master` 브랜치에 대해서만 workflow를 실행한다.
- `master` push에서도 테스트를 실행한다.

### CI-03: 검증용 패키지 빌드

- PR에서도 패키지를 빌드하고 깨끗한 환경에 설치해 패키지 설치 및 전체 테스트를 검증한다.
- PR 빌드는 검증 목적이며 공개 버전 산정, PyPI 업로드, GitHub Release 생성·갱신에 사용하지 않는다.
- PR에서 생성된 배포 산출물은 릴리즈용 artifact로 보관하거나 게시하지 않는다.

### CI-04: master 전용 릴리즈 작업

아래 작업은 `push` 이벤트이면서 ref가 `refs/heads/master`인 경우에만 실행되어야 한다.

- 릴리즈 버전 및 빌드 번호 계획
- 릴리즈 변경 로그 수집 및 릴리즈 노트 artifact 보관
- 릴리즈 배포용 배포물 보관
- 버전 태그 기록
- PyPI 업로드와 GitHub Release 생성·갱신

## 제약 및 보안

- PR 테스트는 PR의 변경 코드와 테스트를 실행하므로, 기본 권한은 읽기 전용으로 유지한다.
- PR 실행 경로에서 배포 비밀이나 릴리즈 쓰기 권한을 사용하지 않는다.
- `pull_request_target`으로 전환하여 PR 코드를 특권 컨텍스트에서 실행하지 않는다.
- GitHub Actions에서 PR 테스트를 실제로 트리거하려면 workflow 정의가 저장소 기본 브랜치에 존재해야 한다.

## 수용 기준

| ID | 기준 |
| --- | --- |
| AC-01 | `pull_request` 트리거에 base branch 제한이 없어 모든 대상 브랜치 PR에서 실행된다. |
| AC-02 | `master` push가 테스트 workflow를 실행하고, 다른 브랜치 push는 트리거하지 않는다. |
| AC-03 | PR과 `master` push에서 Python 버전 매트릭스 테스트를 실행한다. |
| AC-04 | PR에서는 검증용 패키지 빌드·설치·테스트가 가능하지만 배포용 산출물 보관이나 공개 배포를 하지 않는다. |
| AC-05 | 버전·릴리즈 노트·태그·PyPI·GitHub Release 작업은 `master` push에서만 실행된다. |
| AC-06 | PR 테스트에서 쓰기 권한이나 배포 비밀을 사용하지 않는다. |
