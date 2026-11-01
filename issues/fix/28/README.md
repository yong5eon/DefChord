# DefChord 제품 식별자와 문서 정리

- 원본 이슈: GitHub [#28](https://github.com/yong5eon/DefChord/issues/28)
- 유형: `fix` — 원본 이슈의 `fix` 레이블 적용 확인
- 작업 대상: DefChord 저장소
- 작업 브랜치: `fix/28`
- 분기 기준 및 병합 대상: `master`
- 승인 범위: 저장소·패키지·import·프로젝트 및 문서의 전체 이름 변경
- 확정 소개 문구: `Just def. / Define your code. Compose your chord. / You don't need to await this.`

## 요청 및 확정 범위

### 목적

프로젝트·배포물·import 및 문서에 DefChord를 일관되게 사용한다. 일반 Python의 `def`로 정의한 동작들이 함께 웹 앱이라는 화음을 이룬다는 의미를 소개 문구에 담는다.

### 확정한 소개 문구

```markdown
# DefChord

The Modern Synchronous Python Web Application Framework

**Just def.**<br>
**Define your code. Compose your chord.**<br>
**You don't need to await this.**
```

### 변경 범위

- 프로젝트 및 Python 배포 패키지 이름을 DefChord로 변경
- 공개 import 경로와 서버 어댑터 구현체 패키지 등 연관 이름 변경
- 패키징 설정, 빌드·배포·검증 스크립트와 테스트의 관련 참조 갱신
- 한국어·영어 README, 패키지 소개 문서, 상세 문서와 샘플의 이름·설치 명령·import 예제 갱신
- 기존 동기식 요청 처리, 공개 기능과 서버 어댑터의 선택 설치 동작 유지

### 구현 전 확인 사항

- DefChord의 PyPI 프로젝트 조회는 404였으나, 실제 배포 이름 사용 가능 여부는 별도 확인 필요
- GitHub 저장소 이름 및 연관 링크 변경 여부와 수행 시점 확인

### 인수 기준

- 새 이름으로 빌드한 배포물의 설치와 기본 import, 최소 서버 실행 검증
- 선택형 서버 어댑터의 패키지 이름·의존성·import 경로 일치 확인
- 관련 테스트와 배포물 검증으로 기존 동작 유지 확인
- 한국어·영어 문서의 주요 내용과 코드 예제가 실제 변경 결과와 일치
- 현재 소스·문서·작업 기록과 생성 산출물이 현행 제품 식별자를 사용

## 확정된 결정 및 실제 상태

- PyPI JSON API에서 `DefChord`, `DefChord-Gunicorn`, `DefChord-Uvicorn`은 작업 시점에 모두 404였다. 실제 게시 가능 여부는 게시 시 다시 확인하며, 이번 작업에서는 배포하지 않는다.
- GitHub 저장소와 로컬 폴더 이름은 이미 `DefChord`로 변경되었고, `fix/28` 브랜치와 새 `origin`을 유지한다.
- Metrics와 OpenAPI vendor extension 이름도 새 이름으로 통일한다.

## 작업 문서

- [요구사항](./REQUIREMENTS.md)
- [계획](./PLAN.md)
- [구현 요약](./IMPLEMENTS.md)
- [최신 구현 기록](./implements/1793542993332.md)
- [작업 결과](./TASKS.md)
- [최신 작업 기록](./tasks/1793544105753.md)
- [변경 로그](./CHANGELOG.md)
