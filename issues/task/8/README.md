# PR 및 master push CI 동작 변경

모든 대상 브랜치의 pull request에서 Python 버전별 패키지 빌드·설치·테스트를 실행하도록 CI를 변경했습니다. `master` push에서도 같은 테스트를 수행합니다.

PR에서 만들어지는 패키지는 검증용이며 공개되지 않습니다. 버전 계획, 릴리즈 노트 작성, 배포용 artifact 보관, 태그 생성 및 PyPI·GitHub Release 배포는 `master` push에만 수행됩니다. 따라서 feature 브랜치 간 PR에서도 테스트 결과를 확인할 수 있고, PR 테스트가 릴리즈를 만들거나 패키지를 공개하지 않습니다.

이 동작을 PR에서 활성화하려면 워크플로 변경이 저장소의 기본 브랜치에 먼저 반영되어야 합니다.
