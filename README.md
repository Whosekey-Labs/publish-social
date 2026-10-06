# publish-social — WhosekeyLabs 포크

사용자가 승인한 이미지·영상·문구를 각 SNS 공식 API로 게시하는 로컬 도구와 Codex 스킬이다.

- 원본 저장소: [digitaljavelina/publish-social](https://github.com/digitaljavelina/publish-social)
- 검토한 upstream: `560b9b6b9d0f6e982a26413d556aeeedb30f43a3`
- 보완일: 2026-10-07
- 라이선스: [MIT](LICENSE). 원본 저작권과 커밋 기록을 보존한다.

## 이번 보완

- 기본 실행은 **로컬 미리보기**다. 실제 게시는 `--publish`가 필요하다.
- 미리보기는 미디어 변환·원본 변경·공개 서버 업로드·SNS 호출·토큰 갱신을 하지 않는다.
- 큰 사진은 임시 복사본에서만 축소한다. 원본과 같은 이름의 기존 JPEG도 덮어쓰지 않는다.
- 업로드는 게시 승인과 확인 뒤에만 실행한다.
- HTTP 오류에서 토큰이 포함된 요청 URL과 응답 본문을 출력하지 않는다.
- 비대화 실행은 자동으로 승인하지 않는다. 이미 받은 승인에는 `--yes`를 사용한다.
- X 유료 API는 별도 승인 후 `--allow-paid-x`가 필요하다.
- `uv.lock`으로 의존성을 고정하고 외부 통신을 차단한 회귀 테스트를 제공한다.

## 설치와 미리보기

Python 3.11 이상과 [uv](https://docs.astral.sh/uv/)가 필요하다. 이 저장소 폴더에서:

```bash
uv sync --locked
uv run --locked python publish.py --file "/absolute/path/post.md" --check
uv run --locked python publish.py --file "/absolute/path/post.md" --dry-run
```

`uv run python publish.py` 형태로 실행한다. `uv run publish.py`는 원본 스크립트의 개별 의존성 선언을 사용하므로 이 포크의 고정된 프로젝트 환경을 쓰려면 피한다.

초안(`status: draft`, `approved: false`)도 미리보기할 수 있다. `--check`는 설정값 존재 여부를 보는 로컬 검사다. 실제 토큰 유효성·게시 권한·SNS 연결 성공은 확인하지 않는다. 영상 미리보기는 설치된 ffprobe로 로컬 속성을 읽는다.

기본 게시물 형식은 [SKILL.md](SKILL.md)를 따른다. 첫 게시물은 한 플랫폼씩 연결하고 실제 계정과 결과 링크를 확인한다.

## 실제 게시

사용자에게 계정, 플랫폼, 문구, 첨부를 보여 주고 게시 승인을 받는다. 승인한 게시물 파일에 `status: ready`와 `approved: true`를 기록한 뒤:

```bash
uv run --locked python publish.py --file "/absolute/path/post.md" --platforms instagram --publish
```

Codex처럼 비대화 환경에서는 이미 받은 승인을 입력하는 `--yes`를 추가한다. 승인 없는 게시를 자동으로 허용하는 옵션이 아니다.

## 지원과 연결 조건

| 플랫폼 | 방식과 필요한 준비 |
|---|---|
| Instagram | 공식 Instagram API, Business/Creator 계정, 개발자 앱·게시 권한·사용자 토큰, 미디어 URL |
| Threads | 공식 Threads API, 개발자 앱·게시 권한·사용자 토큰, 이미지·영상 게시에는 미디어 URL |
| Bluesky | AT Protocol, 사용자 계정과 앱 비밀번호 |
| Mastodon | 사용자 인스턴스와 게시·미디어 권한 토큰 |
| Facebook | 관리하는 Page와 게시 권한·Page 토큰, 이미지·영상에는 미디어 URL |
| LinkedIn | 조직 페이지 게시 권한과 토큰. 이 구현은 개인 프로필 게시용이 아님 |
| YouTube | Google OAuth와 영상 업로드 권한, 영상 파일·제목 |
| X | 별도 승인한 유료 API 또는 사용자가 인증한 브라우저 |

각 플랫폼의 개발자 앱 설정과 과거 연결 예시는 [원본 연결 안내](UPSTREAM.md#5-connect-your-platforms)를 참고한다. API 버전·권한·심사 조건·요금·호출 한도는 실제 연결 시 공식 문서로 다시 확인한다. 원본 안내의 실행 명령보다 이 README와 SKILL.md의 현재 명령을 우선한다.

## 인증과 이미지 호스트

인증 파일은 Git 저장소 밖의 `~/.config/publish-social/.env`에 두고 필요한 플랫폼만 설정한다. 형식은 [.env.example](.env.example)을 참고한다. 폴더는 700, 파일은 600 권한을 적용하며 인증 정보를 대화·로그·커밋에 넣지 않는다. X 브라우저 세션 역시 로컬에만 보관한다.

Instagram·Threads·Facebook은 미디어를 URL로 가져온다. 현재 구현은 사용자가 설정한 호스트에 SSH/rsync로 업로드한다. `IMAGE_HOST_BASE_URL`, `IMAGE_HOST_SSH`, `IMAGE_HOST_PATH`를 설정하며 이 업로드는 실제 게시 승인 뒤에만 수행된다. 게시를 취소하거나 미리보기만 할 때에는 호스트가 필요하지 않다.

SNS 관리 서비스 구독은 필요하지 않지만 사용자 이미지 호스트·실행 환경·AI 사용 비용은 별개다. 공개 호스트에 올린 파일은 자동 삭제되지 않는다.

X 브라우저 기능을 사용할 때만 `uv sync --locked --extra browser`로 의존성을 준비한다. 저장된 세션은 게시 권한을 가지므로 공유하지 않는다. 기본 미리보기는 브라우저 패키지가 없어도 가능하다.

## 검증과 제한

```bash
uv sync --locked --group dev
uv run --locked python -m pytest -q
```

회귀 검증 범위: 미리보기의 무통신·무업로드·원본 보존, 승인 없는 게시 차단, 취소 후 업로드 차단, HTTP 오류와 인증 갱신 오류의 비밀값 보호, 명시 승인 뒤 업로드, X 유료 API 차단, 비대화 자동 승인 방지, X 단독 실행의 기본 미리보기.

**실제 SNS 계정 인증과 실게시 성공은 아직 검증하지 않았다.** 계정별 앱 권한과 API 버전 호환성은 연결 후 확인해야 한다. 이미지 한 장 또는 영상 한 개씩 지원하며 캐러셀은 구현되어 있지 않다.

여러 플랫폼 중 일부만 성공하거나 플랫폼이 게시 후 링크 조회에 실패하면, 재시도 전에 이미 게시된 결과를 먼저 확인한다. 현재 기록은 게시물 파일 단위이므로 완전한 멱등 재시도나 자동 예약 큐를 제공하지 않는다. 의존성을 고정했지만 전체 의존성의 CVE 검사를 완료했다는 의미는 아니다.

## Codex 스킬

이 폴더의 [SKILL.md](SKILL.md)와 실행 파일을 함께 스킬 폴더에 설치한다. 설치 후 다음 대화부터 `$publish-social`을 사용할 수 있다. 계정 가입·최초 인증·실게시 승인은 스킬 설치와 별도로 진행한다.
