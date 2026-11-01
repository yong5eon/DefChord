# DefChord 제품 식별자

제품, Python 배포 패키지, import 경로와 런타임 식별자가 DefChord 이름 체계로 통일됩니다.

```shell
git remote set-url origin https://github.com/yong5eon/DefChord.git
```

Gunicorn 또는 Uvicorn adapter는 `DefChord[Gunicorn]` 또는 `DefChord[Uvicorn]` extra로 설치합니다. Metrics 이름은 `defchord_*`, OpenAPI vendor extension 키는 `x-defchord-*`를 사용합니다.

새 소스 저장소 주소는 [yong5eon/DefChord](https://github.com/yong5eon/DefChord)입니다.
