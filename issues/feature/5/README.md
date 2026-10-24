# Extension 생명 주기 훅 변경 로그

## 구현 내용

- Application이 생성된 Extension 인스턴스를 등록하고 같은 인스턴스로 재시작하도록 변경했다.
- Extension 생성자에 시작·정리·요청·응답·오류 훅을 추가했다. 단일 훅·시퀀스·None을 지원하고 인스턴스별로 보관한다.
- `startup(application)`에서 연결·라우트 등록·자원 준비를 수행하고 `cleanup()`에서 정리하도록 단순화했다.
- 부분 시작 실패 시 라우트·동적 훅을 롤백하고, 시작 완료 확장을 역순 정리하면서 최초 오류를 보존한다.
- 기본 확장 7종과 샘플을 새 계약으로 이전했다.

## 전체 요청 집계와 파일 라우트

- Application 요청 훅의 명시적 등록·토큰 기반 해제 API를 추가했다.
- Metrics가 시작·정리 단계에서 전체 요청 관찰을 자동 연결·해제한다. 사용자가 수집기와 세 Application 훅을 수동 연결할 필요가 없다.
- 요청 교체·중첩 호출의 집계 연결, 후속 응답 훅 오류의 실패 재분류와 재시작 중복 방지를 유지했다.
- FileSystemRoute를 FileSystem 모듈로 이관하고 Specifications·테스트의 참조를 수정했다. 접두 경로 매칭·디코딩·우선순위는 유지한다.

## 시작 출력과 후속 수정

- 로고·구성 안내를 시작 훅 로그보다 먼저 출력한다.
- 확장 표시는 라우트 조회 대신 `str(extension)`을 사용한다. URI와 파일 경로·설정 등 표시 형식은 구현체가 결정한다.
- 표시 형식 변경으로 실패한 배너·HTTP 테스트를 수정하여 고정 문자열 대신 각 인스턴스의 실제 표시값과 등록 순서를 검증한다.
- 기존 명세 저장 스크립트는 Application 시작 후 문서를 생성하고 `finally`로 종료하도록 이전했다.

## 호환성 변경

| 이전 사용 | 변경 후 |
| --- | --- |
| 공개 Factory 또는 Extension 클래스 등록 | 생성한 Extension 인스턴스 등록 |
| 클래스 선언에서 Extension 훅 설정 | 생성자에서 훅 설정 |
| 별도 `bind/route/routes` 계약 | `startup(application)`에서 연결·등록 |
| Extension의 `onRequest/onResponse` 필터 | `on_request/on_request_response` 훅 |
| FileSystem 요청 필터의 튜플 반환 | Request 반환 |
| `DefEssential.FileSystemRoute` import | `DefEssential.Extensions.FileSystem`에서 import |
| 명세 호출 시 Application 전달 | 시작 단계에서 연결한 뒤 `spec.document()` 호출 |

공개 ExtensionFactory는 제공하지 않는다. 내부 RunExtensionFactory는 RequestRunner 어댑터 생성기로 유지한다. 일반 RequestRunner 필터 제거는 이번 변경에 포함하지 않는다.

## 검증

- 재구현 전체 검증: **총 198개 중 193개 통과, 5개 건너뜀**.
- FileSystemRoute 이관 후 관련 테스트: **48개 통과**.
- 표시 문자열 기대값 수정 후 배너·HTTP 확장 테스트: **26개 통과**.
- 실제 OpenAPI 문서: **3.1.0, 24경로** 생성 확인.
- 구현 시 확인 범위의 타입 오류와 `git diff --check` 검사 통과.

검증 시점과 환경, 건너뜀 및 Linux CI 재확인 한계는 [구현 기록](./IMPLEMENTS.md#검증-기록과-한계)에 구분했다. 위 결과는 문서 작성 중 새로 실행한 결과가 아니다.

## 관련 문서

- [이슈](./ISSUE.md)
- [요구사항 명세서](./REQUIREMENTS.md)
- [구현 계획서](./PLAN.md)
- [상세 구현 기록](./IMPLEMENTS.md)
