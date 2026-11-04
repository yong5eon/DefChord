# SSE 주석 전송 지원

## 추가 기능

`ServerSentEventsWriter.comment(text)`로 연결 유지용 SSE 주석을 보낼 수 있습니다. 하위 writer에 주석 바이트를 직접 쓰지 않아도 UTF-8 주석을 전송하고 즉시 flush합니다.

`begin()` 이후 열린 출력에서 `comment('keep-alive')`를 호출하세요. 일반 출력과 기존 chunked 출력에서 같은 API를 사용할 수 있습니다.

여러 줄 입력과 CRLF·CR·LF, 빈 문자열을 처리하며 모든 줄을 주석으로 전송합니다. 업무 이벤트를 발생시키거나 마지막 이벤트 ID와 재연결 간격을 변경하지 않습니다. write·flush 실패는 호출자에게 전파됩니다.

## 사용 시 주의사항

- 주기적인 호출과 전송 간격은 애플리케이션에서 관리해야 합니다. 자동 heartbeat 스케줄러는 제공하지 않습니다.
- 즉시 flush가 클라이언트 수신, 프록시 버퍼링 해제나 유휴 연결 유지 성공을 보장하지는 않습니다.
- 기존 이벤트 API와 사용 방식은 유지되며 설정·데이터 마이그레이션은 필요하지 않습니다.

사용 예시와 자세한 설명은 [SSE 매뉴얼](../../../docs/StreamingAndWebSockets.md#server-sent-events)을 참고하세요.
