# Extension 인스턴스 등록 및 시작 단계 연결 구현 계획서

## 1. 목표와 진행 상태

[최신 요구사항](./REQUIREMENTS.md)에 따라 Factory 구조를 걷어내고 Extension 인스턴스 등록·생성자 훅·`startup(application)` 중심으로 단순화한다.

아래 재설계 작업을 Python 코드·기본 확장·샘플·테스트에 반영했다. 이전 Factory 구현의 검증 결과와 구분하여 새 계약의 실행 결과를 7절에 기록한다.

## 2. 변경 요약

| 이전 Factory 구현 | 변경 후 |
| --- | --- |
| `Application(exts=(PingFactory(...),))` | `Application(exts=(Ping(...),))` |
| Factory가 Extension과 Route 시퀀스 반환 | `extension.startup(application)`이 라우트를 등록 |
| Extension 클래스 선언에 훅 설정 | Extension 생성자에서 인스턴스별 훅 설정 |
| Factory 로컬 하위 클래스로 자원 훅 바인딩 | 구현체 `startup/cleanup`에서 자원을 관리 |
| Application 참조 대신 조회 함수 주입 | 시작 시 Application 연결·필요시 직접 보관 허용 |
| FileSystem의 기존 RequestRunner 필터 보존 | Extension 요청·응답 훅으로 대체 |
| 배너에 Factory 이름 표시 | 시작 전 `str(extension)` 표시값·개수 출력 |

별도 `bind/route/routes` 계약, 자동 스케줄러, 범용 Context, 일반 RequestRunner 필터 API 제거는 추가하지 않는다.

## 3. 구현 단계

### 1단계: Extension 공개 계약 변경

- [Extension](../../../src/Extension.py)의 클래스 선언 훅과 상속 설정·생략 sentinel을 제거한다.
- 생성자에서 다섯 훅을 입력받고 단일·시퀀스·None을 검증하여 인스턴스별 튜플로 보관한다.
- `startup(application)`과 `cleanup()`을 제공하고 추상 `__call__(request)`를 유지한다.
- 기본 `__str__()`은 클래스 이름을 반환한다. 기본 구현체는 필요하면 생성자 설정으로 경로 등을 표현하되 시작 전 조회 가능·부수 효과 없음·비밀 값 제외를 지킨다.
- 시작 구현체는 의존성·라우트·자원을 준비한 뒤 부모 시작 메서드로 사용자 시작 훅을 실행한다.
- 정리는 사용자 훅 실패와 자원 정리 오류를 모두 다루고 자원 회수 누락·최초 오류 은폐를 방지한다. 부모 정리 호출 위치와 `try/finally` 패턴을 기본 구현·테스트로 명확히 한다.
- 공개 `ExtensionFactory` 모듈 및 기본 Factory 클래스·export를 제거하고 관련 문서를 갱신한다.

### 2단계: Application 등록과 수명 변경

- [Application](../../../src/Application.py)은 생성된 Extension 인스턴스 시퀀스를 검증·복사하고 시작 전부터 보관한다.
- Factory 생성 결과 검증 대신 인스턴스 소유권·시작 완료 상태와 Extension별 라우트 소유 관계를 관리한다.
- Application 시작 훅 → 등록 순 Extension 시작 → 실행 상태 전환 순서를 유지한다.
- `add_extension_route(extension, route)`는 현재 시작 중인 Extension의 라우트를 검증·등록한다. 기존 `add`의 일반 핸들러 등록 계약과 구분한다.
- 중간 Route 충돌·자원 준비·사용자 훅 실패에 대해 후속 중단, 완료 Extension 정리, 일반 라우트 보존과 부분 등록 롤백을 구현한다.
- 종료는 Extension 역순 `cleanup()` → Application 정리 훅 순서다. 모든 정리를 시도하고 첫 오류를 전파한다.
- 재시작 시 기존 Extension 인스턴스를 다시 사용한다. Factory 전용의 매번 새 인스턴스 요구를 제거하고 이전 Extension 라우트·상태를 재설정한다.
- 등록 목록 자체와 시작 완료 목록을 구분하여 실패해도 사용자 등록 구성이 사라지지 않게 한다.

### 3단계: 요청 경계와 필터 제거

- [Extension 실행기](../../../src/Runners/RunExtension.py)는 생성자에 저장된 인스턴스 훅으로 요청 → 호출 → 응답, 오류 시 오류 훅 순서를 실행한다.
- 현재 내부 `RunExtensionFactory`는 RequestRunner 어댑터 생성기다. 공개 ExtensionFactory 제거와 혼동하지 않고 필요한 어댑터 기능만 유지한다.
- Extension 어댑터에서 RequestFilter·ResponseFilter 인자와 연결을 제거한다. [공통 라우트 도우미](../../../src/Extensions/Utils/Routes.py)에서도 필터 타입 별칭·전달을 제거한다.
- 직접 출력·응답 교체·본문 정리·예외 체인과 Application 바깥 경계는 보존한다.
- FileSystem 요청 훅은 디코딩된 `path`를 수정하고 Request를 반환하며 응답 훅은 Response를 교체한다. 예전 필터 튜플·조기 응답 계약을 남기지 않는다.
- 일반 RequestRunner의 기존 필터와 서버 전송 오류 처리에는 손대지 않는다.

### 4단계: 기본 Extension과 샘플 이전

| 대상 | 작업 |
| --- | --- |
| [Ping](../../../src/Extensions/Ping.py) | 시작 시 Application 연결 후 현재 실행 상태 조회 |
| [File](../../../src/Extensions/File.py) | 생성자 파일·경로·새 훅 설정, 시작 시 GET/HEAD 등록 |
| [FileSystem](../../../src/Extensions/FileSystem.py) | 생성자 연결·경로·새 훅 설정, 시작 시 특수 라우트와 연결 준비, 정리 시 연결 회수 |
| [Status](../../../src/Extensions/Status.py), [Swagger](../../../src/Extensions/Swagger.py) | 기존 페이지 설정·검증 보존, 생성자 훅과 시작 시 라우트 등록 |
| [Specifications](../../../src/Extensions/Specifications.py) | 시작 시 Application 연결, 문서 생성 시 현재 일반 라우트 조회 |
| [Metrics](../../../src/Extensions/Metrics.py) | 시작 시 연결·초기화, 4절의 명시적 등록 API로 전체 요청 집계 연결 |

- 다중 경로·특수 매칭과 명시적인 Extension 소유 관계를 보존한다. URL만으로 일반 핸들러까지 문서에서 제외하지 않는다.
- [샘플](../../../samples/Sample.py)의 Factory 이름을 Extension으로 바꾸고 파일명 변환·응답 교체를 새 훅 클래스로 이전한다.
- [명세 스크립트](../../../samples/scripts/DescriptionToFile.py)는 이미 등록된 Specifications 인스턴스에 접근하되 Application 연결이 필요한 문서 생성은 시작 후 실행하고 `finally`로 정리한다.
- [공개 API](../../../src/__init__.py), [기본 Extension export](../../../src/Extensions/__init__.py), [사용 설명](../../../README.md)을 함께 이전한다.

### 5단계: 시작 배너

- [시작 배너](../../../src/Startup.py)는 Extension 라우트나 경로에 의존하지 않고 등록 인스턴스의 `str(extension)` 결과·개수를 출력한다. `__repr__()`과의 선택 로직이나 확장별 문자열 조립은 추가하지 않는다.
- 바인딩 성공 → 로고·구성 안내 → Application 시작 로그·Extension 시작 → 요청 수신 순서를 유지한다.
- 배너를 위해 Extension을 미리 시작하거나 별도 라우트 조회 메서드를 추가하지 않는다.
- Python·Uvicorn·Gunicorn에서 중복 로고, 시작 호출 횟수 및 시작 실패 시 표현을 검증한다.

## 4. Metrics 연결 확정 사항

사용자는 명시적인 Application 훅 등록·해제 API 도입을 선택했다. `Metrics('/metrics')`가 시작 시 수집 훅을 연결하고 정리 시 해제한다.

- Extension의 `on_request`를 모든 요청에 실행하는 방식은 사용하지 않는다.
- `add_request_hooks(...)`로 시작 중 Extension 소유 등록과 토큰을 만들고 `remove_request_hooks(token)`으로 소유 Extension의 시작·정리 중 해제한다.
- 동적 등록 순서 뒤에 기존 생성자 훅을 실행하고 요청별 구성을 복사한다. 생성자 훅 튜플은 변경하지 않는다.
- 시작 실패 롤백은 실패 Extension의 등록분까지 포함하고 정리 오류 시에도 소유 등록을 제거한다. 재시작 시 다시 등록하여 중복을 방지한다.
- 전체 요청 처리 시간 집계와 반환 후 전송 오류 제외는 유지한다.

이 등록 API는 전체 요청 관찰을 위한 것이며 Extension 자체의 요청 훅 적용 범위를 넓히지 않는다.

## 5. 검증 계획

| 범위 | 확인할 사례 | 수용 기준 |
| --- | --- | --- |
| 등록·생성자 | 인스턴스만 허용, 단일·복수·None, 잘못된 훅, 입력 복사와 인스턴스 격리 | AC-01, AC-02 |
| 시작·라우트 | 올바른 연결 순서, 일반·다중·FileSystem·빈 라우트, 충돌·소유권 | AC-03, AC-04 |
| 실패·종료 | 부분 등록 롤백, 자원 준비·사용자 훅 실패, 역순 정리, 복수 오류, 재시작 | AC-05, AC-06 |
| 요청 | 요청 변환, 응답 교체·실패·자원 회수, 오류 체인, 직접 출력 | AC-07 |
| 필터 | Extension에서 구 필터 제거, FileSystem 새 훅, 일반 RequestRunner 회귀 | AC-08 |
| 배너 | 로고가 시작 훅 로그보다 선행, 기본·재정의된 `__str__`, 시작 전 표시와 부수 효과 없음, 비HTTP 확장, 실패 경로 | AC-09 |
| 통합 | 기본 확장, 라이브 문서·메트릭, 샘플 HTTP와 명세 스크립트 | AC-10, AC-11 |
| 서버·동시성 | 서버별 수명·전송 정리, 요청 교체·중첩·동시 처리, 앱 격리 | AC-12 |

관련 테스트를 새 계약으로 이전한 뒤 집중 테스트를 먼저 실행하고 전체 unittest로 확대한다. 기존 도구만 사용하며 선택적 서버·플랫폼 건너뜀은 실제 통과와 구분한다. 문법·타입 진단과 실제 OpenAPI 생성도 확인한다.

## 6. 완료 조건

- Factory·클래스 선언 훅·Extension의 기존 필터 사용이 코드·샘플·export에 남지 않는다.
- 생성자·시작·요청·정리의 책임이 요구사항과 일치하며 불필요한 설치 추상화를 추가하지 않는다.
- Metrics의 명시적 훅 등록·해제와 실패·재시작 동작을 검증한다.
- 배너 출력 순서와 기본 기능을 보존하고 새 계약으로 실행한 검증 결과를 기록한다.

## 7. 검증 기록

인스턴스 계약 재구현 후 Python 3.12.10 가상환경에서 실행했다. 아래 결과는 이전 Factory 구현의 결과가 아니다.

| 검증 | 결과 |
| --- | --- |
| 전체 `unittest discover -s DefChord\tests` | 총 198개, 193개 통과·Gunicorn/POSIX 조건 5개 건너뜀 |
| Extension 훅·기본 확장·export 집중 검증 | 46개 통과 |
| 수명·실패 | 같은 인스턴스 재시작, 소유권, 부분 라우트·동적 훅 롤백, 정리 오류 시 후속 정리와 최초 오류 보존 |
| 요청 경계 | 요청·응답 변환, 직접 출력, 본문 회수, 오류 체인, 최초 Request 교체·중첩 처리 |
| 동적 관찰 | 사용자 훅보다 앞선 실행, 중복·잘못된 토큰 거부, 종료 중 진행 요청의 훅 스냅샷 유지 |
| 배너·기본 확장 | 로고 선행, 시작 전 표시값, 7종 생성자 훅과 FileSystem 자원 회수, Metrics 자동 연결 |
| 실제 명세 스크립트 | OpenAPI 3.1.0·24경로, `/api/run/{a}/{b}` 포함, `/metrics`·`/api/doc` 제외 |
| Pylance | 코어·기본 확장·새 테스트·명세 스크립트 확인 범위 타입 오류 없음, 미사용 매개변수 힌트만 유지 |
| 변경 형식·문서 | `git diff --check` 통과, 변경 문서 5개의 로컬 파일 링크 확인 |

일반 RequestRunner 필터 제거는 이번 변경에 포함하지 않았다. 테스트는 로컬 검증 결과이며 건너뛴 Gunicorn/POSIX 사례를 실행 통과로 간주하지 않는다.
