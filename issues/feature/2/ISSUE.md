# 생명 주기 훅 추가 및 변경

## 해결하려는 문제

Application 과 Extension, RequestRunner 에 생명 주기가 없어서 상황에 따른 핸들링을 못함

## 제안하는 해결 방법

- Application 에 생명 주기 훅을 넣어서 사용자로 하여금 핸들링을 할 수 있게 지원
- Extensioni 에 생명 주기 훅 추가
- RequestRunner 에 생명 주기 훅 추가 및 변경
