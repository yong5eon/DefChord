# 작업 계획

## 구현 계획

1. `src/Extensions/Specifications.py` 확장
- 생성자에 문서 형식 선택 인자(`document_format`)와 YAML 미디어 타입 인자(`yaml_media_type`)를 추가한다.
- 지원 형식을 `json`, `yaml`로 제한하고 잘못된 값은 `ValueError`로 처리한다.
- `json`은 기존 `ResponseJSON` 경로를 유지한다.
- `yaml`은 `PyYAML`을 런타임 로딩해 UTF-8 YAML 응답(`Response`)을 생성한다.
- `PyYAML` 미설치와 직렬화 실패는 예외를 그대로 전파한다.

2. 테스트 추가 (`tests/test_extensions.py`)
- JSON 기본 회귀 테스트 추가
- YAML 응답 Content-Type/UTF-8/의미 동등성 테스트 추가
- 비ASCII 및 오인 가능 문자열, `$ref`, 보안 정의, `x-defchord-*` 보존 확인
- 잘못된 포맷 선택, YAML 의존성 누락, YAML 직렬화 실패 전파 테스트 추가

3. 매뉴얼 갱신 (`docs/ExtensionsAndServers.md`, `docs/ExtensionsAndServers.en.md`)
- 형식 선택 방법과 코드 예시
- YAML 미디어 타입 선택 방법
- `PyYAML` 설치 조건 및 미설치 시 동작
- 현재 OpenAPI 버전 표기(3.1.0)

4. 이슈 문서 갱신 (`issues/feature/36/*`)
- 요구사항/검증 계획/변경 로그/IR 문서 작성
- OpenAPI 3.2 검토 결론(보류 근거와 후속 항목) 반영

## 검증 계획

- 대상 테스트: `tests/test_extensions.py`의 `SpecTests` 중심 실행
- 문서 확인: 한/영 문서에 동일한 선택 API/설치 조건 반영 여부 대조
- 보안 확인: 변경 파일 대상 secret scan 실행
- 최종 점검: 변경 범위가 이슈 요구사항(형식 선택·직렬화·문서화)으로 한정되는지 확인
