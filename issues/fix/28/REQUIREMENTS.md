# 요구사항

## 분석

원본 이슈는 프로젝트 식별자와 패키지·import 경로를 일관되게 정리하는 내용을 다룬다. 저장소 이름과 로컬 경로는 `DefChord`로 설정되었으며, 사용자는 패키지·import·제품 문서까지 작업하도록 승인했다.

## 확정 범위

- 공개 Python 배포 패키지와 선택형 adapter 배포 이름을 DefChord 계열로 변경한다
- 공개 Python import 경로, 내부 자기 참조, 예제와 테스트를 새 이름에 맞춘다
- logger, 프로세스명, Metrics 및 OpenAPI vendor extension처럼 제품 이름을 내보내는 런타임 식별자를 새 이름으로 변경한다
- 한국어·영어 README, 상세 매뉴얼, 개발 지침, 빌드·CI 스크립트와 저장소 URL을 갱신한다
- 확정한 소개 문구를 두 언어 README에 반영한다
- 공개 배포물, import 경로와 문서에서 현행 제품 식별자를 일관되게 사용한다
- 기존 동기식 요청 처리, 공개 기능과 adapter의 선택 설치 동작을 유지한다
- 새 core와 adapter 배포물의 이름·의존성·import 및 wheel/sdist 구성을 검증한다

## 제외 범위 및 미확정 사항

새 배포물의 PyPI 게시, 커밋·푸시·병합·이슈 종료는 수행하지 않는다. PyPI API는 `DefChord`, `DefChord-Gunicorn`, `DefChord-Uvicorn`이 조회되지 않음을 확인했으나 실제 이름 예약·등록 가능 여부는 게시 과정에서 다시 확인해야 한다.
