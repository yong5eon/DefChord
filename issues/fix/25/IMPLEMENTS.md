# 구현 결과

## 설치 파일의 배포 경계

`setup.py`는 단일 `src`에서 `DEF_BUILD_TARGET`에 따라 코어, `DefEssential-Gunicorn`, `DefEssential-Uvicorn`을 만든다. 코어는 공통 코드와 기본 Python 서버를 유지하고 두 선택 어댑터를 제외한다. 각 구현체는 기존 import 경로의 자기 하위 파일만 소유한다. 부모 패키지의 `__init__.py`는 코어만 소유한다.

코어 extras는 동일 버전 구현체 배포물에, 구현체는 동일 버전 코어와 기존 외부 의존성에 연결된다. 설치 시 extras를 감지하거나 import만 차단하는 방식이 아니다. sdist는 공통 소스 트리를 담으며, 선택 파일의 격리 경계는 wheel과 최종 설치 파일이다.

`TargetBuild`와 `TargetEggInfo`는 대상별 빌드·메타데이터 경로를 분리한다. `TargetEggInfo`는 pip가 지정한 메타데이터 출력 경로를 덮어쓰지 않는다. `TargetSdist`는 `.distribution-target`을 보존하고, 알 수 없는 대상과 sdist 대상 변경을 거부한다.

## 개발·CI·배포 준비

`TargetEditableWheel`은 가상환경별 선택 링크 트리와 경로 기반 `.pth`를 사용한다. `scripts/editable_view.py`는 설치 메타데이터로 코어·선택 구현체만 연결하며 제거·소스 교체·동시 시작을 처리한다. 부모 API와 선택 격리를 유지하고 IDE가 같은 파일 트리를 탐색하게 한다. 직접 정션을 만들 필요가 없다.

후속 요구에 따라 editable은 `scripts/build_backend.py`의 `EXTRAS` 설정으로 한 번에 갱신하는 단일 코어 배포물로 전환했다. `pip install -e .`은 코어만, `--config-settings EXTRAS=Gunicorn,Uvicorn`은 지정 목록으로 교체한다. 외부 의존성은 선택 코드와 함께 선언하되 자동 삭제하지 않는다. 일반 배포 분리와 extras는 유지하며 최초 전환 시 기존 별도 구현체 배포물은 제거해야 한다.

`scripts/build_distributions.py`는 한 버전으로 세 배포물을 순차 빌드한다. `scripts/check_distributions.py`는 설치 격리·파일 소유권·독립 재빌드·설치 수명주기·editable 동작을 검사한다. `scripts/prepare_upload.py`는 이름·버전·빌드 번호·기존 파일 해시를 확인하고 구현체와 코어의 게시 준비를 분리한다. CI에 빌드·검사와 구현체 우선 게시 순서를 연결했다.

한국어·영어 README와 [Packaging 매뉴얼](../../../docs/Packaging.md)에 설치·전환·개발·배포 방법을 반영했다. 실제 게시와 커밋은 하지 않았다.

## 검증과 기록

로컬 검증은 [작업 결과](./TASKS.md), 고객 영향은 [변경 로그](./CHANGELOG.md)를 참고한다. 외부 서비스·원격 CI와 실제 게시 검증은 남아 있다.

단계별 구현 기록:

1. [대상별 패키징 구성](./implements/1793294516718.md)
2. [CI와 설치 문서 연결](./implements/1793295445977.md)
3. [최소 런타임 검증 도구와 격리 범위](./implements/1793295838894.md)
4. [릴리즈 테스트 디렉터리 분리](./implements/1793296500294.md)
5. [선택 링크 트리 기반 editable 구성](./implements/1793299630934.md)
6. [EXTRAS 기반 단일 editable 설치](./implements/1793301537857.md)
