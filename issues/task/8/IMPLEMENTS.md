# CI 테스트 및 릴리즈 작업 분리 구현 기록

## 요구사항

[모든 PR과 master push의 테스트 실행 요구사항](./REQUIREMENTS.md)의 CI-01~CI-04를 반영했다.

## 변경 내용

### 트리거와 테스트

- [CI 워크플로](../../../.github/workflows/ci.yml)의 `pull_request` 트리거에서 base branch 필터를 제거했다.
- `push` 트리거는 `master`만 대상으로 유지했다.
- PR 변경 경로를 검사해 테스트를 생략하던 단계를 제거하고 테스트 job의 조건부 실행을 없앴다.
- PR과 `master` push 모두 기존 Python 3.9~3.14 버전 매트릭스로 패키지 빌드, 설치 및 테스트를 수행한다.
- PR 빌드는 테스트 job 안에서만 사용한다. 릴리즈용 배포물 업로드 단계는 `master` push에서만 실행된다.

### 릴리즈 경로

- 버전 계획, 릴리즈 노트 수집, 릴리즈 노트 artifact 보관은 `push` 이벤트와 `refs/heads/master`일 때만 실행한다.
- 배포 job은 동일하게 `master` push 조건을 유지한다. 이에 따라 태그 기록, PyPI 업로드 및 GitHub Release 생성·갱신은 PR에서 실행되지 않는다.
- PR 경로에는 릴리즈용 쓰기 권한이나 배포 비밀 사용을 추가하지 않았다.

## 영향 범위와 운영 참고

- 비-master 브랜치 PR마다 Python 버전 매트릭스 전체가 실행되므로 이전보다 CI 실행량이 늘어난다.
- GitHub는 `pull_request` workflow를 실행할 때 저장소 기본 브랜치의 workflow 정의를 사용한다. 새 트리거 동작이 실제 PR에서 적용되려면 이 변경이 기본 브랜치에 반영되어야 한다.
- 이 환경에서 YAML 파싱 및 조건 검증은 수행했지만, GitHub 원격의 실제 PR 이벤트와 PyPI/GitHub Release 연동은 실행하지 않았다.

## 검증 결과

- PyYAML로 `.github/workflows/ci.yml` 파싱을 확인했다.
- 정적 assertion으로 다음을 확인했다.
  - PR 트리거에 대상 브랜치 제한이 없다.
  - push 트리거는 `master`만 대상으로 한다.
  - 테스트 job에 PR을 생략하는 `if` 조건이 없다.
  - 버전 계획, 릴리즈 변경 로그 수집, 릴리즈 노트 artifact 보관은 `master` push 조건을 가진다.
  - 배포 job은 `master` push 조건을 가진다.
- `git diff --check`를 통과했다.
- GitHub Actions에서의 실제 트리거 및 배포 테스트는 수행하지 않았다.
