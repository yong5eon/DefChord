# ServerSentEventsWriter에 SSE 주석 전송 API 지원

## 작업 정보

- 원본 이슈: GitHub Issues [yong5eon/DefChord #30](https://github.com/yong5eon/DefChord/issues/30)
- 작업 대상 저장소: [yong5eon/DefChord](https://github.com/yong5eon/DefChord)
- 이슈 유형·접두사: 기능 · `feature`
- 원본 레이블: `feature` (이미 적용되어 있어 변경하지 않음)
- 분기 기준 브랜치: `master`
- 병합 대상 브랜치: 미지정
- 작업 브랜치: `feature/30`
- 진행 상태: 로컬 구현·관련 회귀 검증·매뉴얼 갱신 완료, 커밋·푸시 미수행
- 관련 문서: [요구사항 명세](./REQUIREMENTS.md), [작업 계획](./PLAN.md), [구현 결과](./IMPLEMENTS.md), [작업 결과](./TASKS.md), [변경 로그](./CHANGELOG.md)
- 최신 구현 기록: [SSE 주석 전송 API 구현](./implements/1793779562884.md)
- 최신 작업 기록: [매뉴얼 예제 검증 및 인수 기준 검토](./tasks/1793779646282.md)

아래는 이슈 본문 원문입니다.

## 해결하려는 문제

SSE 연결을 유지하거나 유휴 중 연결 종료를 확인하기 위해 업무 이벤트가 아닌 주석을 주기적으로 전송할 필요가 있습니다.

현재 `ServerSentEventsWriter`에는 `begin()`·`emit()`·`retry()`·`end()`가 있지만 주석 전송 API가 없습니다. 따라서 호출자가 `ResponseWriter` 등 하위 writer에 직접 SSE 주석 바이트를 쓰고 flush해야 합니다. 프로토콜상 유효하더라도 SSE 인코딩 책임이 애플리케이션으로 새어 나가고 동일한 포맷 처리를 반복하게 됩니다.

## 제안하는 해결 방법

`ServerSentEventsWriter`에서 SSE 주석을 전송하는 공개 API를 지원해 주세요. 예를 들어 `comment(text)` 형태를 고려할 수 있으며 구체적인 이름·시그니처는 기존 API와 대조해 결정하면 됩니다.

- 문자열을 SSE 주석으로 인코딩해 쓰고, 기존 `emit()`·`retry()`처럼 즉시 flush합니다.
- 각 주석 줄은 `:`로 시작하고, 주석 전송 단위를 빈 줄로 마칩니다.
- 여러 줄 문자열의 CRLF·CR·LF를 안전하게 처리하고 모든 줄을 주석으로 인코딩하여 입력이 `data`·`event`·`id` 등으로 해석되지 않게 합니다.
- `data`·`event`·`id`·`retry` 필드를 임의로 추가하지 않습니다. 업무 이벤트를 발생시키거나 마지막 이벤트 ID를 변경하지 않습니다.
- 하위 write·flush 실패는 호출자에게 전파합니다.
- 일반 출력과 기존 chunked StreamWriter 경로 모두에서 같은 주석 전송 기능을 사용할 수 있어야 합니다.

원하는 전송 형식의 예시입니다.

```text
: keep-alive

```

### 확인 기준

- 단일·여러 줄 주석의 UTF-8 바이트와 빈 줄 경계를 확인합니다.
- 줄바꿈이 포함된 입력도 모든 줄이 주석으로 해석되는지 확인합니다.
- 주석 앞뒤의 기존 이벤트·재접속 ID·retry 처리에 영향이 없는지 확인합니다.
- write·flush 실패가 숨겨지지 않는지 확인합니다.
- 기존 SSE emit·retry 동작과 일반·chunked 출력의 회귀를 검증합니다.
- 관련 매뉴얼에 주석 전송과 연결 유지 사용 예시를 반영합니다.

## 고려한 대안

- 하위 writer로 주석 바이트 직접 전송: 현재 가능한 방법이지만 애플리케이션이 SSE 문법과 flush를 직접 관리해야 합니다.
- 빈 `data` 이벤트 또는 별도 heartbeat 업무 이벤트 전송: 주석과 의미가 다르고 소비자의 이벤트 처리에 영향을 주므로 대체하지 않습니다.

## 추가 정보

WHATWG SSE 규격은 `:`로 시작하는 줄을 주석으로 정의하고 수신 측에서 무시하도록 명시합니다. 주석을 이용한 연결 유지도 설명합니다. 이 요청은 주석의 직렬화·전송 지원이며 DefChord에 주기 타이머나 자동 heartbeat 스케줄러를 추가해 달라는 요청은 아닙니다.

- 현재 구현: https://github.com/yong5eon/DefChord/blob/master/src/IO/Writers/ServerSentEventsWriter.py
- SSE 파싱 규격: https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream
- 연결 유지 관련 설명: https://html.spec.whatwg.org/multipage/server-sent-events.html#authoring-notes
