# 오류 응답 처리 작업 계획

## 목표와 기준 문서

세 계층의 기존 오류 훅이 `Optional[Response]`를 반환하도록 구현하고, `Response` 반환 시 해당 응답을 요청 처리의 결과로 전달한다. `None` 반환, 오류 훅 실패, writer 시작 이후의 오류 및 오류가 발생하지 않는 요청은 기존 계약을 유지한다.

- 요구사항: [REQUIREMENTS.md](./REQUIREMENTS.md)
- 현재 문제 분석과 해결 제안: [README.md](./README.md)

## 진행 원칙

- 변경 대상 저장소는 `DefEssential`이며 작업 브랜치는 `feature/21`이다.
- 구현과 검증은 요구사항의 인수 기준을 기준으로 진행한다. 미확인 동작을 편의상 기본값으로 정하지 않는다.
- 병합 대상 브랜치는 현재 확인되지 않았으며 이 계획에서 추정하거나 변경하지 않는다.
- 아래 단계와 검증은 계획이며, 수행 결과는 구현 후 이슈 실행 기록에 기록한다.

## 작업 단계

| 순서 | 작업 | 변경 대상 | 선행 조건 | 완료 조건 |
| --- | --- | --- | --- | --- |
| 1 | 기준 동작과 관련 테스트 확인 | `tests/test_request_runner_hooks.py`, `tests/test_extension_hooks.py`, `tests/test_application_hooks.py`, `tests/test_transport_conformance.py`, `tests/test_writers.py` | 없음 | 관련 테스트를 변경 전에 실행해 기준 결과를 기록하고, 실패가 있으면 기존 실패인지 확인 |
| 2 | 오류 훅 응답 계약 및 단위 테스트 구현 | `src/RequestRunner.py`, `src/Runners/RunRequest.py`, `src/Extension.py`, `src/Runners/RunExtension.py`, 관련 RequestRunner·Extension 테스트 | 1 | 타입 주석이 `Optional[Response]`를 반영하고, 반환된 응답은 오류를 처리하며 `None`은 기존처럼 전파 |
| 3 | Application 경계 및 계층 통합 검증 | `src/Application.py`, 관련 Application·통합 테스트 | 2 | 기존 Application 오류 훅이 `Response`를 반환할 때 adapter까지 정상 응답으로 전달되고, 미처리 오류는 기존 경로 유지 |
| 4 | 직접 출력·전송 경계 회귀 검증 및 필요한 수정 | `src/Adapter/RequestHandler.py` (요구사항 충족에 필요한 경우만), `tests/test_transport_conformance.py`, `tests/test_writers.py` | 2, 3 | writer 시작 전에는 오류 응답 처리 가능 여부가 계약에 맞고, 시작 후에는 응답 교체 없이 기존 실패·정리 동작 유지 |
| 5 | 오류 처리 상세 매뉴얼 분리 및 진입점 연결 | `docs/ErrorHandling.md`, `docs/ErrorHandling.en.md`, `docs/Lifecycle.md`, `docs/Lifecycle.en.md`, `docs/README.md`, `docs/README.en.md` | 2, 3, 4 | 오류 운영 안내를 별도 한국어·영어 문서에서 충분히 설명하고, 생명주기 문서와 양 언어 진입점에서 연결 |
| 6 | 전체 검증 및 결과 대조 | 관련 테스트 전체, 공개 export·타입 선언, 문서 링크 | 2–5 | 관련 테스트 통과, 인수 기준 확인, 문서 설명과 구현 동작 일치 |

## 구현 세부 계획

### 1. 기준 동작 확인

- 아래 관련 테스트 모듈을 변경 전에 실행하고 결과를 기록한다.
  - `tests.test_request_runner_hooks`
  - `tests.test_extension_hooks`
  - `tests.test_application_hooks`
  - `tests.test_transport_conformance`
  - `tests.test_writers`
- 기존 오류 관찰 훅, 오류 훅 자체의 실패, 계층 간 예외 전파와 writer 전송 후 실패의 현재 동작을 확인한다.
- 기준 실행 실패가 있으면 이번 변경과 무관한 기존 실패인지 분리하고, 무관한 문제는 별도 수정하지 않는다.

### 2. RequestRunner 및 Extension 처리

- 오류 계약 타입의 반환 주석을 `Optional[Response]`로 수정하고, 기존 `(request, error)` 시그니처와 export를 유지한다.
- 오류 훅을 설정 순서대로 호출한다. `None`이면 다음 훅을 실행하고, `Response`이면 현재 계층에서 오류를 처리하고 남은 같은 계층 훅을 중단한다.
- 복수 훅 회귀 테스트는 `[None, Response, sentinel]` 순서로 구성해 첫 번째는 다음 훅으로 진행하고 두 번째 응답을 채택하며 sentinel 훅은 호출되지 않는지 확인한다. 모든 훅이 `None`인 경우에는 모두 등록 순서대로 호출되고 예외가 전파되는지 별도 확인한다.
- 각 계층에서 정상 응답 생성·검증·응답 훅이 오류 훅보다 먼저 실행되는지 확인한다. 응답 검증 또는 응답 훅 실패 시 그 계층 오류 훅으로 전환하고, 오류 훅이 만든 응답에는 같은 계층 응답 훅을 다시 실행하지 않는다.
- 응답 검증은 각 요청 계층이 소유한 범위로 한정한다. Application이 응답을 adapter에 반환한 뒤의 직렬화·네트워크·전송 실패가 Application 오류 훅으로 재진입하지 않는지 transport 회귀 테스트로 확인한다.
- 해당 계층의 오류 훅이 전부 `None`이면 원래 예외를 다시 발생시킨다.
- 오류 훅이 잘못된 타입을 반환하거나 예외를 발생시키면 실패를 전파하고 원래 예외의 체인을 보존한다.
- 처리된 오류 응답은 오류가 발생한 계층의 응답 훅을 다시 거치지 않도록 하며, 바깥 계층은 정상 응답을 받은 것처럼 계속 처리하게 한다.
- RequestRunner 검증·생성·실행·응답 처리 실패와 Extension 요청·호출·응답 처리 실패 각각에 대해 복수 오류 훅의 첫 `Response` 채택, 후속 훅 미호출, 전부 `None`인 경우의 전파 및 잘못된 반환값 테스트를 추가한다.

### 3. Application 및 계층 간 응답 전달

- Application에 이미 있는 `ApplicationRequestError`와 `on_request_error`만 확장하고 별도의 오류 훅 API를 추가하지 않는다.
- Application 오류 훅이 `Response`를 반환하면 해당 응답을 Application 요청 결과로 반환해 adapter의 기본 오류 변환으로 넘어가지 않게 한다.
- Application에 여러 오류 훅이 등록된 경우 `None` 반환 훅 다음으로 실행을 계속하고 최초 `Response` 반환 후 나머지 Application 훅을 중단하는지 확인한다.
- 안쪽 계층에서 `Response`로 처리한 예외는 바깥 오류 훅에 다시 전달하지 않는다. 다만 응답을 정상 반환으로 전달받은 바깥 계층의 정상 응답 훅은 기존 순서대로 적용한다.
- 안쪽 오류 응답을 처리하는 바깥 응답 훅이 실패하면 바깥 계층의 오류 훅으로 전환되는지, 이미 처리한 안쪽 오류 훅은 재호출되지 않는지 통합 테스트로 확인한다.
- Application 응답을 adapter에 반환한 뒤 발생한 전송 오류가 Application 오류 훅으로 재진입하지 않고 기존 transport 오류 경로를 따르는지 확인한다.
- 계층 통합 테스트에서 RequestRunner → Application, Extension → 바깥 RequestRunner → Application, Application → adapter 경로와 각 계층의 오류 훅 실행 횟수를 확인한다.

### 4. 직접 출력과 응답 자원

- `ResponseWriter`가 시작되지 않은 경우에만 반환된 오류 `Response`를 전송할 수 있는지 확인한다.
- writer가 이미 시작된 경우 응답 상태 코드나 본문을 대체하지 않으며 현재 전송 실패 동작을 유지한다.
- 오류 처리로 생성되거나 교체된 `Response` 본문이 정확히 한 번 닫히는지 기존 응답 자원 소유권 규칙으로 검증한다.
- 현재 adapter의 미처리 `Error` 상태 코드 응답과 예상하지 못한 예외의 일반 500 응답, 민감한 예외 세부 정보 비노출을 회귀 검증한다. 요구사항 충족에 이미 충분하면 adapter 동작은 변경하지 않는다.

### 5. 오류 처리 상세 매뉴얼 분리

- 오류 처리 내용을 별도 `docs/ErrorHandling.md`에 한국어 기준 매뉴얼로 작성하고 대응하는 `docs/ErrorHandling.en.md`를 함께 제공한다.
- 기존 `LifecycleAndErrors.md`와 `LifecycleAndErrors.en.md`를 각각 `Lifecycle.md`와 `Lifecycle.en.md`로 변경하고, 시작·정지, extension 생명주기, 요청 처리 단계와 정상 요청 훅 범위에 집중하도록 정리한다. 오류 처리 계약·운영 설명은 중복해서 유지하지 않고 새 매뉴얼로 안내한다.
- `docs/README.md`와 `docs/README.en.md`의 학습 순서와 매뉴얼 목록에 오류 처리 문서를 독립 주제로 추가한다. 양 언어에서 설명과 목차 범위를 맞춘다.
- 신규 오류 처리 매뉴얼은 운영자가 실제 동작과 제약을 이해할 수 있도록 다음 내용을 체계적으로 다룬다.
  1. 오류 처리의 목적, HTTP 요청 오류와 생명주기·전송 오류의 경계
  2. 요청 입력·검증·라우팅·handler·extension·application·adapter에 걸친 처리 흐름과 Mermaid 시퀀스 다이어그램
  3. `Error`, `ClientError`, `ServerError`와 예상하지 못한 예외의 기본 adapter 응답 동작
  4. `RequestRunnerRequestError`, `ExtensionRequestError`, `ApplicationRequestError`의 역할, 등록 위치, 호출 인자 및 `Optional[Response]` 반환 계약
  5. `None` 반환 시 전파, `Response` 반환 시 처리 완료, 훅 순서·조기 종료 및 계층별 우선순위
  6. 계층마다 오류 훅을 사용하는 실행 가능한 예제와 어느 훅이 관찰·응답을 담당하는지 설명
  7. 오류 훅 자체의 예외·잘못된 반환값, 오류 응답 훅의 재실행 방지 및 실패 전파
  8. 로깅·요청 상관관계·메트릭 등 운영 시 관찰 방법과 응답 본문·자격 증명·개인정보의 안전한 취급
  9. 직접 출력, 스트리밍 및 응답 writer 시작 후에는 상태 코드·본문을 새 오류 응답으로 바꿀 수 없는 제약
  10. adapter 기본 오류 응답을 유지할지 사용자 응답으로 처리할지 정하는 기준, 검증·테스트 권고와 운영 점검 항목
- 예제와 모든 주장은 코드·공개 API·테스트에 대조한다. 구현되지 않은 보장이나 설정을 안내하지 않고, 코드 예제는 필요한 import와 최소 실행 흐름을 포함한다.
- `Lifecycle`, `ErrorHandling` 및 `docs/README`의 상대 링크와 제목 앵커를 확인하고, 영어판은 한국어판과 설명 범위·예제 의미를 맞춘다.

## 검증 계획

### 단계별 테스트

| 요구사항 | 검증 방법 |
| --- | --- |
| FR-1, FR-2, FR-3, FR-5, FR-6 | RequestRunner·Extension·Application 훅 각각의 복수 등록 순서, `[None, Response, sentinel]` 첫 응답 채택 및 후속 훅 미호출, 전체 `None` 전파, 잘못된 반환, 훅 예외 단위 테스트 |
| FR-4 | 응답 훅 실패 시 같은 계층 오류 훅으로 전환되는지, 처리된 오류 응답이 같은 계층 응답 훅을 재실행하지 않고 바깥 정상 응답 훅을 통과하는지, 바깥 응답 훅 실패는 해당 바깥 오류 훅으로 전환되는지, adapter 인계 후 전송 실패가 Application 오류 훅에 재진입하지 않는지 확인 |
| FR-7 | writer 미시작·시작 상태별 오류 응답 교체 여부와 본문 정리 확인 |
| FR-8 | adapter 통합 테스트로 `Error` 상태 코드·본문 및 일반 예외의 500 응답·세부 정보 비노출 확인 |
| 호환성 | 기존 `None` 반환 훅 및 오류 없는 정상 경로의 회귀 테스트 |
| 공개 문서 | 별도 한국어·영어 오류 처리 매뉴얼의 반환 계약·운영 안내 일치, 생명주기 문서와 진입점의 연결 링크 확인 |

### 실행 명령

변경 전 기준 테스트와 변경 후 회귀 테스트:

```powershell
python -m unittest `
  tests.test_request_runner_hooks `
  tests.test_extension_hooks `
  tests.test_application_hooks `
  tests.test_transport_conformance `
  tests.test_writers
```

단위·통합 테스트가 통과하면 저장소 전체 테스트를 실행한다.

```powershell
python -m unittest discover -s tests
```

저장소에서 제공하는 타입 검사나 문서 검증 명령이 확인되면 해당 도구로 변경 영향 범위를 추가 검증한다. 실행하지 않은 검증은 완료로 기록하지 않는다.

## 위험과 대응

- **계층별 응답 훅 순서 혼선:** 오류를 처리한 계층의 응답 훅과 바깥 계층의 정상 응답 훅을 별도로 테스트하고 문서에도 구분해 설명한다.
- **오류 훅의 오류가 원래 예외를 가림:** 훅 예외의 전파와 `__context__`/예외 체인을 검증하며 실패를 무시하지 않는다.
- **writer 시작 이후 응답 재작성 시도:** 시작 여부를 경계 조건으로 테스트하고 기존 스트리밍 실패 동작을 보존한다.
- **기존 관찰 훅 호환성:** `None` 반환 코드와 기존 공개 인자 시그니처의 테스트를 유지한다.
- **자원 누수 또는 중복 닫기:** 반환·대체·실패 경로별 Response 본문 정리 횟수를 테스트한다.

## 완료 확인

- [ ] [REQUIREMENTS.md](./REQUIREMENTS.md)의 모든 인수 기준을 구현 및 검증 결과와 대조한다.
- [ ] 위에 명시한 테스트 명령의 실제 결과와 미실행 검증을 실행 기록에 남긴다.
- [ ] 두 언어의 매뉴얼, 테스트, 공개 API와 구현 동작이 서로 일치하는지 확인한다.
- [ ] 변경 목록에 무관한 파일, 사용자 데이터 또는 임시 산출물이 섞이지 않았는지 확인한다.
- [ ] 미충족 기준이나 제한사항이 있으면 완료로 표현하지 않고 이유와 후속 작업을 기록한다.
