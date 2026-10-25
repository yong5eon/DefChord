# 구현 기록

## 적용 요구사항

- 오류 훅 계약의 `Optional[Response]` 반환, 등록 순서 실행, 최초 `Response` 채택과 처리 완료 시의 전파 중단
- 계층별 오류 응답 fallback, 바깥 계층 정상 응답 처리, 이미 시작된 writer의 응답 교체 방지
- 오류 처리 상세 매뉴얼의 한국어·영어 분리 및 생명주기 문서 경로 정리

## 구현 내용

- `RequestRunnerRequestError`, `ExtensionRequestError`, `ApplicationRequestError`의 반환 타입을 `Optional[Response]`로 변경하고 기존 `(request, error)` 인자는 유지했다.
- RequestRunner·Extension·Application 실행 경계에서 오류 훅을 등록 순서대로 실행하도록 변경했다. `None`은 다음 훅으로 전달하고, 처음 반환된 `Response`는 현재 계층에서 채택해 후속 오류 훅을 중단한다. 잘못된 반환은 `TypeError`, 훅 자체의 예외는 예외 체인과 함께 전파한다.
- 안쪽 계층이 오류 응답을 반환하면 같은 계층의 응답 훅을 반복하지 않고 바깥 정상 응답 경로를 진행한다. 바깥 응답 처리에서 새 예외가 발생하면 그 바깥 계층 오류 훅이 처리한다.
- Application 응답 훅의 예외·교체 경로에 응답 본문 정리를 적용해 복구 응답 전환 시 이전 본문이 누수되지 않도록 했다.
- 이미 시작된 응답 writer에 오류 응답을 대체 전송하지 않도록 세 계층에서 확인하고, 채택할 수 없는 응답 본문을 정리한 뒤 `RuntimeError`를 원래 예외 체인과 함께 전파한다.
- RequestRunner 및 Application 오류 응답이 adapter에 전달되는 통합 테스트와, RequestRunner·Extension·Application writer 시작 후 교체 방지 테스트를 추가했다. 복수 훅의 `[None, Response, sentinel]`, 바깥 응답 훅의 새 예외, 같은 계층 응답 훅 재실행 방지도 테스트한다.
- `docs/ErrorHandling.md`와 `docs/ErrorHandling.en.md`를 작성하고, 기존 `LifecycleAndErrors` 문서를 `Lifecycle.md`와 `Lifecycle.en.md`로 분리했다. 문서 진입점·라우팅·확장 안내의 링크와 오류 처리 소개를 갱신했다.
- 통합 샘플에 `GET /api/run/error`를 추가했다. 해당 `RequestRunner`는 의도적으로 HTTP 418 `ClientError`를 발생시키고 전용 오류 훅이 사용자 정의 `text/plain` 응답을 반환한다. 기존 `ErrorLog` 관찰 훅의 `None` 반환과 오류 전파 동작은 유지했다.
- Getting Started 한·영 문서에 샘플 route와 기대 응답을 안내하고, 해당 endpoint가 실제 HTTP 요청으로 상태 코드·본문·Content-Type을 반환하는 샘플 회귀 테스트를 추가했다.

## 영향 범위

- 오류 훅의 공개 반환 계약이 `None` 전용에서 `None` 또는 `Response`로 확장됐다. 기존 `None` 반환 관찰 훅은 계속 동작한다.
- 오류 응답을 반환하는 계층의 정상 응답 훅은 다시 실행하지 않는다. 오류 응답은 바깥 계층 정상 응답 처리 대상이다.
- 직접 출력 writer가 시작된 뒤에는 반환 응답으로 상태 코드와 본문을 교체할 수 없다. RequestRunner에서 복구 응답을 반환하면 해당 계층의 CORS 응답 처리도 다시 적용되지 않으므로, 필요한 헤더는 응답에 명시해야 한다.
- adapter의 미처리 예외 기본 응답 정책은 수정하지 않았다.

## 검증 결과

- 변경 전 focused 기준 테스트:
  - `test_*hooks.py`: 53개 통과
  - `test_transport_conformance.py`: 5개 중 4개 건너뜀, 나머지 통과
  - `test_writers.py`: 19개 통과
- 변경 후:
  - `test_*hooks.py`: 62개 통과
  - `test_transport_conformance.py`: 5개 중 4개 건너뜀, 나머지 통과
  - `test_writers.py`: 19개 통과
  - 전체 `python -m unittest discover -s tests`: 252개 통과, 15개 건너뜀
- 변경된 Python 소스의 Pylance 진단에서 오류가 없음을 확인했다.
- 상세 매뉴얼 상대 링크 검사와 `git diff --check`를 통과했다.
- 통합 샘플의 HTTP 오류 응답 테스트: `python -m unittest discover -s tests -p 'test_samples.py' -k error_hook -q` (2개 통과)
- 저장소 전체 Markdown 링크 점검에서는 이번 변경과 무관한 `issues/feature/4/IMPLEMENTS.md`의 기존 상대 링크 오류가 확인됐다. 변경한 매뉴얼과 `feature/21` 문서 범위의 링크 검사는 통과했다.

Focused 테스트 실행 전에는 패키지가 설치되어 있지 않아 import가 실패했다. 저장소 안내에 따라 editable 설치 후 `unittest discover`로 기준 및 회귀 테스트를 실행했다.
