# 구현 종합

- `Specifications`에 문서 응답 형식 선택 API(`document_format`)를 추가하고 기본값 `json`으로 기존 동작을 유지했다.
- `document_format='yaml'`일 때 `PyYAML.safe_dump(..., allow_unicode=True, sort_keys=False)`로 문서를 직렬화해 UTF-8 YAML 응답을 반환하도록 구현했다.
- YAML 응답의 Content-Type은 `yaml_media_type`로 설정하고 기본값은 `application/yaml`로 두었다.
- 지원하지 않는 형식은 생성자에서 `ValueError`로 거부한다.
- YAML 의존성 누락과 직렬화 오류는 예외를 그대로 전파해 조용한 폴백을 방지했다.
