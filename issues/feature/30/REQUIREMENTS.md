# SSE 주석 전송 API 요구사항

## 목적과 근거

[원본 이슈 및 작업 정보](./README.md)에 따라 애플리케이션이 SSE 문법과 flush를 직접 관리하지 않고 주석을 전송할 수 있도록 한다. 이 문서는 현재 구현을 대조한 분석과 사용자가 동의한 해결 방향을 기준으로 작성한 구현 전 명세다.

### 현재 동작과 문제

- [ServerSentEventsWriter](../../../src/IO/Writers/ServerSentEventsWriter.py)는 `emit()`과 `retry()`에서 바이트를 쓰고 즉시 flush하지만 주석 전송 API는 제공하지 않는다.
- [ServerSentEvents](../../../src/IO/Writers/ServerSentEvents.py)의 이벤트 인코딩은 항상 `data:` 줄을 생성하므로 빈 이벤트로 주석을 대체할 수 없다.
- [StreamWriter](../../../src/IO/Writers/StreamWriter.py)와 [ChunkedStreamWriter](../../../src/IO/Writers/ChunkedStreamWriter.py)는 같은 쓰기 인터페이스를 제공한다. HTTP chunk framing과 전송 상태·실패 처리는 [ResponseWriter](../../../src/IO/ResponseWriter.py)가 담당한다.

### 해결 방향

기존 SSE writer에 문자열을 주석으로 직렬화해 쓰고 flush하는 메서드를 추가한다. 기존 출력 경로를 재사용하며 주석 전용 클래스나 별도 출력 계층은 추가하지 않는다.

## 범위

포함 범위는 공개 API, 주석 인코딩·전송, 관련 회귀 테스트와 한국어·영어 상세 매뉴얼이다.

다음 항목은 제외한다.

- 주기 타이머, 자동 heartbeat 스케줄러 및 전송 주기 설정
- 자동 재시도, 자동 재연결 및 연결 상태 관리 기능
- 이벤트 모델에 주석 필드 추가 또는 iterable 출력용 신규 API
- 기존 이벤트 필드, HTTP framing 및 응답 생명주기 변경

## 확정 요구사항

### R1. 공개 API

- `ServerSentEventsWriter`에 동기 메서드 `comment(self, text: str) -> None`을 추가한다.
- `text`는 필수 문자열 인자이며 기본 메시지를 자동으로 제공하지 않는다.
- 기존과 같이 `begin()` 이후, 출력이 종료되거나 실패하기 전에 호출한다. 호출 가능 상태는 하위 writer의 기존 검사에 따른다.

### R2. 주석 인코딩

- 입력의 CRLF를 하나의 LF로 정규화하고 나머지 CR도 LF로 정규화한다.
- 정규화한 문자열을 LF 기준으로 나누고 모든 줄 앞에 `: `를 붙인다.
- 각 주석 줄은 LF로 끝내며 전송 단위 마지막에 LF를 하나 더 붙여 빈 줄로 마친다.
- 빈 문자열도 한 줄의 주석으로 전송한다. 중간 빈 줄과 마지막 줄바꿈으로 생긴 빈 줄을 보존한다.
- 결과는 UTF-8 바이트로 인코딩한다. 입력 내용을 삭제하거나 `data`·`event`·`id`·`retry` 필드로 변환하지 않는다.

아래는 구현 후 충족해야 할 예상 출력이며 현재 지원되는 동작을 나타내는 예시는 아니다.

| 입력 문자열 | 예상 UTF-8 바이트 |
| --- | --- |
| `"keep-alive"` | `b": keep-alive\n\n"` |
| `""` | `b": \n\n"` |
| `"a\r\nb\rc"` | `b": a\n: b\n: c\n\n"` |
| `"a\n\nb\n"` | `b": a\n: \n: b\n: \n\n"` |
| `"a\nid: changed"` | `b": a\n: id: changed\n\n"` |

### R3. 전송과 오류

- 인코딩 결과를 기존 writer에 쓰고, 쓰기가 성공하면 반환 전에 즉시 flush한다.
- `ResponseWriter` 직접 전달, `StreamWriter` 및 `ChunkedStreamWriter` 전달 경로에서 같은 SSE 주석 바이트를 전송한다.
- chunked 출력은 기존 HTTP framing과 종료 처리를 그대로 사용한다.
- write·flush 실패는 호출자에게 전파한다. 예외를 숨기거나 성공으로 처리하거나 자동 재시도하지 않는다.
- write가 실패하면 후속 flush를 실행하지 않는다. 실패 상태는 하위 writer의 기존 계약을 유지한다.

### R4. 기존 동작과 호환성

- 주석 전송 때문에 업무 이벤트를 생성하거나 수신 측의 마지막 이벤트 ID 및 재연결 간격을 변경하지 않는다.
- 주석 앞뒤의 `emit()`·`retry()` 출력과 이벤트 경계를 유지한다.
- `begin()`·`emit()`·`retry()`·`end()`의 기존 시그니처, 헤더 및 동작은 변경하지 않는다.
- 기존 응답 상태 검사와 일반·chunked 전송의 책임을 새 메서드에 중복 구현하지 않는다.

### R5. 사용 문서와 보장 범위

- [한국어 상세 매뉴얼](../../../docs/StreamingAndWebSockets.md)과 [영어 상세 매뉴얼](../../../docs/StreamingAndWebSockets.en.md)에 주석 API와 연결 유지 용도의 호출 예시를 같은 범위로 추가한다.
- 전송 주기와 반복 호출은 애플리케이션 책임이며 자동 heartbeat 기능이 아님을 설명한다.
- 즉시 flush는 하위 writer에 대한 호출을 의미한다. 클라이언트 수신, 프록시 버퍼링 해제, 유휴 연결 유지 성공을 보장하지 않는다.

## 인수 기준

| 기준 | 관련 요구사항 | 검증 내용 |
| --- | --- | --- |
| AC1 | R1, R2 | 단일 줄, 빈 문자열 및 비ASCII 문자열의 정확한 UTF-8 바이트와 마지막 빈 줄 확인 |
| AC2 | R2 | CRLF·CR·LF, 혼합 개행, 중간 빈 줄 및 마지막 줄바꿈의 정확한 출력 확인 |
| AC3 | R2, R4 | 개행 뒤에 `data:`·`event:`·`id:`·`retry:`가 있는 입력도 모든 줄이 주석으로 출력되고 별도 필드가 생기지 않는지 확인 |
| AC4 | R3 | 직접 전달·일반·chunked 경로의 주석 본문, 기존 chunk framing 및 쓰기 성공 직후 flush 호출 확인 |
| AC5 | R3, R4 | write·flush 실패가 각각 전파되고 write 실패 후 flush하지 않으며 기존 실패 상태 계약이 유지되는지 확인 |
| AC6 | R1, R4 | 시작 전·종료 후 호출의 기존 상태 오류와 이벤트 → 주석 → retry → 이벤트 순서의 출력 및 경계 확인 |
| AC7 | R4 | 기존 SSE 인코딩·필드 검증 및 일반·chunked 출력 관련 회귀 테스트 통과 |
| AC8 | R5 | 한국어·영어 매뉴얼의 API, 예시, 호출 주체 및 보장 범위가 구현과 일치하는지 확인 |

인수 기준은 구현 후 검증할 항목이다. 현재 분석 단계에서 실행한 기존 테스트 결과는 [작업 기록](./TASKS.md)에 구분해 남긴다.

## 미확정 사항

공개 API와 주석 인코딩·전송 동작에 남은 미확정 사항은 없다. 병합 대상 브랜치는 [작업 정보](./README.md)에 기록한 대로 미지정이며 이 명세 작성으로 확정하지 않는다.
