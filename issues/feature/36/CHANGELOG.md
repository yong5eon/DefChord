# OpenAPI 명세 응답 형식 확장

`Specifications` 확장에서 OpenAPI 문서를 JSON 외 YAML로도 반환할 수 있습니다.

- 기본 동작은 기존과 동일하게 JSON(`application/json; charset=utf-8`)입니다.
- `document_format='yaml'`을 설정하면 YAML(`application/yaml; charset=utf-8`)로 응답합니다.
- YAML 직렬화에는 `PyYAML`이 필요하며, 미설치 상태에서 YAML 형식을 요청하면 오류가 발생해 설치 누락을 즉시 확인할 수 있습니다.
- JSON과 YAML은 동일한 OpenAPI 문서를 직렬화하므로 경로, 컴포넌트, 보안 정의, 확장 필드와 값 의미가 동일하게 유지됩니다.

현재 명세 버전 문자열은 기존과 동일하게 OpenAPI `3.1.0`을 유지합니다. OpenAPI 3.2 지원은 생성 로직·연동 도구 호환성 검토 후 별도 작업으로 진행해야 합니다.
