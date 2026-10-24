# RequestRunner 에 생명 주기 훅 추가 및 변경

## 해결하려는 문제

RequestRunner 에 RequestFilter 를 대신하는 훅을 추가 변경

## 제안하는 해결 방법

- 기존 RequestFilter 방식 제거
- on_request, on_request_response, on_error 훅 추가

## 상위 이슈

feature/2
