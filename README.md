# Publish Social

개인용 macOS 데스크톱 앱과 GUI 없이 동작하는 JSON CLI다. 두 인터페이스가 같은 서비스와 같은 로컬 데이터를 사용한다.

## 사용

앱은 `~/Applications/Publish Social.app`, CLI는 `~/.local/bin/publish-social`에 설치한다.

```bash
publish-social --json status
publish-social --json accounts list
publish-social --json posts create --title "첫 번째 인사" --text "안녕하세요."
publish-social --json posts list
```

앱을 켜지 않아도 모든 CLI 명령을 사용할 수 있다. `publish-social gui` 또는 앱 더블클릭으로 화면을 연다. 앱에서 만든 데이터도 CLI에 바로 보이며, CLI 변경은 실행 중인 앱에서 약 0.75초 간격으로 자동 반영된다.

## 데이터는 하나

기본 위치는 `~/Library/Application Support/Publish Social/`다.

- `state.sqlite3`: 계정 식별 정보, 게시물, 승인 버전, 게시 결과, 공용 설정
- `media/`: 사용자가 선택해 첨부한 이미지·영상. 내용 해시로 보관하고 원본은 변경하지 않는다.
- 인증 정보: 모든 인터페이스가 같은 `WhosekeyLabs.PublishSocial` macOS 키체인 항목을 사용한다. SQLite에 토큰을 저장하지 않는다.

앱 재설치와 버전 교체는 이 데이터를 지우지 않는다. 설치된 스킬도 이 앱의 CLI만 호출하므로 별도의 게시물·계정 데이터 사본을 만들지 않는다. `--data-dir` 또는 `PUBLISH_SOCIAL_DATA_DIR`로 명시적으로 위치를 바꿀 때에는 GUI와 CLI에 같은 위치를 지정한다. 이는 한 Mac의 로컬 공유 구조이며 여러 컴퓨터의 클라우드 동기화 기능은 아니다.

SQLite WAL과 쓰기 트랜잭션을 사용한다. 초안 수정은 버전 일치가 필요하며, 같은 버전·계정의 게시를 두 프로세스가 동시에 시작하지 못한다. GUI의 저장하지 않은 편집은 CLI 변경으로 덮어쓰지 않는다.

## CLI

모든 결과는 JSON이며 성공 종료는 0, 미완료 게시는 1, 입력·상태 오류는 2다.

```bash
publish-social --json accounts add --platform instagram --label "내 Instagram" --config '{"INSTAGRAM_USER_ID":"계정ID"}'
publish-social --json posts create --title "첫 인사" --text "게시 문구" --account ACCOUNT_ID --media "/absolute/path/photo.png"
publish-social --json posts show POST_ID
publish-social --json posts update POST_ID --version 1 --text "수정한 문구"
publish-social --json posts preview POST_ID
publish-social --json posts approve POST_ID --version 2
publish-social --json posts publish POST_ID --confirm
publish-social --json history list
publish-social --json settings show
```

`approve`는 사용자가 확인한 현재 버전을 기록하는 명령이다. 실제 게시 지시 없이 자동으로 실행할 승인 대체 수단이 아니다. 내용·대상 계정·첨부·계정 식별 정보가 바뀌면 승인이 무효화된다. X 유료 API는 별도 승인과 `--allow-paid-x`가 필요하다.

인증 정보는 GUI의 계정 설정에서 직접 입력하거나 안전한 표준 입력 JSON으로 전달한다. 토큰을 명령 인자나 터미널 기록에 넣지 않는다.

```bash
publish-social --json accounts credentials ACCOUNT_ID --from-stdin
```

이 명령은 비대화 표준 입력이 필요하다. 에이전트는 사용자에게 토큰을 대화에 붙여넣도록 요구하지 않는다. 실제 키체인 접근 승인은 macOS에서 사용자가 직접 처리한다.

공용 이미지 호스트는 GUI 설정이나 아래 CLI를 사용한다.

```bash
publish-social --json settings set --name IMAGE_HOST_BASE_URL --value "https://images.example.com"
publish-social --json settings set --name IMAGE_HOST_SSH --value "my-image-host"
publish-social --json settings set --name IMAGE_HOST_PATH --value "/var/www/images"
```

Instagram·Threads·Facebook 미디어 게시는 사용자가 설정한 SSH/rsync 이미지 호스트가 필요하다. 실제 게시 승인을 받은 작업에서만 파일을 전송한다. 미리보기·조회에는 호스트와 인증 정보가 필요하지 않다.

## 게시 결과와 재시도

완료한 버전·계정의 게시 명령을 반복하면 기존 결과를 반환하고 API를 다시 호출하지 않는다. 결과를 확정하지 못했거나 프로세스가 중단된 작업은 자동 재게시하지 않는다. GUI 게시 기록 또는 아래 명령으로 SNS의 실제 결과를 확인한다.

이미 게시된 내용은 초안 수정으로 바꾸지 않는다. 내용을 바꿔 다시 게시하려면 새 게시물로 만든다. GUI의 다시 불러오기는 저장되지 않은 편집을 확인한 뒤 최신 버전을 읽는다.

```bash
publish-social --json history resolve JOB_ID --url "https://실제로-게시된-주소"
publish-social --json history resolve JOB_ID --not-published
```

`--not-published`는 실제 계정을 확인하고 작업 프로세스가 종료됐음을 확인한 경우에만 사용한다. 미게시로 확인하면 승인이 해제되므로 다음 게시는 다시 승인해야 한다.

## 지원 범위

Instagram, Threads, Bluesky, Mastodon, Facebook Page, LinkedIn 조직 페이지, YouTube, X API 어댑터를 연결한다. 계정 등록은 개발자 앱 인증이나 실제 API 연결 검증을 대신하지 않는다. 초기 계정 설정은 [원본 연결 자료](UPSTREAM.md#5-connect-your-platforms)와 각 플랫폼 공식 문서를 참고한다.

이 버전은 개인용 macOS arm64 앱이다. 사진 한 장 또는 영상 한 개씩 지원한다. 캐러셀, 자동 SNS 가입·OAuth 설정, 예약 발행 큐, X 브라우저 게시, 다른 컴퓨터 동기화는 이 앱에 구현하지 않았다. 실제 SNS 인증·게시 성공은 아직 검증하지 않았다. 영상 속성 확인·변환에는 설치된 ffprobe/ffmpeg, 이미지 호스트 전송에는 ssh/rsync가 필요하다.

## 개발·검증·빌드

```bash
uv sync --locked --group dev --group desktop
uv run --locked python social.py --json status
uv run --locked python social.py gui
uv run --locked python -m pytest -q
uv run --locked python scripts/build_desktop.py --output dist
uv run --locked python scripts/install_desktop.py --app "dist/Publish Social.app"
```

앱은 Python·Qt·API 의존성을 포함한다. 설치된 CLI에는 별도 Python·uv나 실행 중인 GUI가 필요하지 않다. 소스 실행에는 Python 3.11 이상과 uv가 필요하다. Python 런타임에 포함된 SQLite도 함께 번들된다.

기존 `publish.py`는 내부 API 어댑터로 보존했다. 이전 Markdown 파일을 별도 데이터처럼 직접 게시하던 CLI는 비활성화했으며 사용자·에이전트는 `publish-social` 또는 `social.py`를 사용한다.

개인 데이터와 인증 정보는 Git에 넣지 않는다. 백업 명령은 SQLite 상태만 복사하며 첨부와 키체인은 제외한다. 앱은 로컬 사용을 위한 ad-hoc 서명을 적용하며 Apple Developer ID 서명·공개 배포용 공증을 완료한 앱은 아니다.

## 출처

[digitaljavelina/publish-social](https://github.com/digitaljavelina/publish-social)의 MIT 라이선스 API 어댑터를 기반으로 한다. [LICENSE](LICENSE)와 기존 기록을 보존한다. GUI·공유 서비스·SQLite 저장소·JSON CLI는 이 포크에서 추가했다. 설계는 [ARCHITECTURE.md](ARCHITECTURE.md), 에이전트 사용법은 [SKILL.md](SKILL.md)에 있다.
