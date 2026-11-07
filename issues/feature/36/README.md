# Specifications YAML OpenAPI 응답 지원

## 이슈 메타데이터

- 원본 이슈: [yong5eon/DefChord #36](https://github.com/yong5eon/DefChord/issues/36)
- 유형·레이블: 기능 (`feature`), `feature` 레이블 확인
- 작업 저장소: `yong5eon/DefChord`
- 작업 브랜치: `codex/support-yaml-response`
- 병합 대상 브랜치: `master` (저장소 기본 브랜치 기준)
- 진행 상태: 구현 및 문서 갱신 진행 중

## 이슈 원문 보존

### 제목

Specifications 확장에 YAML 형식의 OpenAPI 문서 응답 지원

### 본문

현재 `Specifications` 확장은 `ResponseJSON(self.document())`을 반환해 JSON 응답만 제공한다. 본 이슈는 JSON 기본 동작을 유지하면서 YAML 출력 선택을 추가하고, 형식 선택 API·오류 처리·문서화 및 OpenAPI 3.2 지원 검토 결과를 요구사항과 검증 계획에 반영하도록 요구한다.

## 작업 기록

- 요구사항: [REQUIREMENTS.md](./REQUIREMENTS.md)
- 계획: [PLAN.md](./PLAN.md)
- 구현 종합: [IMPLEMENTS.md](./IMPLEMENTS.md)
- 구현 외 작업 종합: [TASKS.md](./TASKS.md)
- 변경 적용 요청 문서: [IR.md](./IR.md)
- 변경 로그: [CHANGELOG.md](./CHANGELOG.md)
- 단계별 기록: [context/](./context/), [implements/](./implements/), [tasks/](./tasks/)
