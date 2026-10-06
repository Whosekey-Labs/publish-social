---
name: publish-social
description: 개인용 Publish Social 앱의 JSON CLI로 계정·초안·승인·게시 결과를 관리하고 사용자가 승인한 SNS 게시물을 전송한다. GUI를 실행하지 않고 앱과 동일한 로컬 데이터를 사용하는 SNS 작업에 적용한다.
---

# Publish Social 에이전트 사용

설치된 `publish-social` CLI를 호출한다. GUI를 실행하거나 스킬 폴더에 데이터 사본을 만들지 않는다. 계정·게시물·설정·결과는 앱과 같은 저장소를 사용한다.

## 실행 파일 확인

`command -v publish-social`로 확인한다. PATH에 없으면 기본 설치 위치인 `"$HOME/.local/bin/publish-social"` 또는 `"$HOME/Applications/Publish Social.app/Contents/MacOS/publish-social"`을 사용한다. 실행 파일이 없으면 앱 설치가 필요함을 알린다. 이전 `publish.py`나 스킬 안의 구버전 코드로 대신 게시하지 않는다.

```bash
publish-social --json status
publish-social --json accounts list
publish-social --json posts list
```

기본 저장 위치는 모든 호출에서 동일하다. `--data-dir`은 사용자가 다른 작업실을 명시하거나 격리된 검증을 요청한 경우에만 사용하고, 해당 GUI에도 같은 위치를 사용한다.

에이전트의 파일 샌드박스에서 공용 Application Support 폴더 접근이 막히면 승인된 호스트 실행으로 같은 CLI를 호출한다. Codex의 `exec_command`에서는 `sandbox_permissions: "require_escalated"`를 사용한다. 권한 오류를 피하려고 임시 DB·프로젝트별 사본을 만들거나 GUI를 대신 조작하지 않는다. 공유 폴더 밖의 추가 권한이나 설정 변경은 이 스킬의 범위가 아니다.

## 초안과 수정

대상 계정을 실제 목록의 ID로 선택한다. 인증값 존재와 실제 API 연결 성공을 구분한다. 사용자가 제공한 이미지·영상·문구만 요청 범위에서 준비한다.

```bash
publish-social --json posts create --title "게시물 제목" --text "게시 문구" --account ACCOUNT_ID --media "/absolute/path/photo.png"
publish-social --json posts show POST_ID
publish-social --json posts update POST_ID --version CURRENT_VERSION --text "수정한 문구"
publish-social --json posts preview POST_ID
```

`--text-file`은 UTF-8 문구 파일을 받는다. `--captions`는 플랫폼별 문구 JSON 객체를 받는다. 여러 대상은 `--account`를 반복한다. 수정 충돌은 최신 내용을 읽고 사용자 의도와 합쳐 해결한다. 저장되지 않은 GUI 편집을 버리거나 버전을 임의로 조작하지 않는다.

미리보기·목록·조회는 외부 API를 호출하거나 이미지를 공개 서버에 올리지 않는다. 첨부 시 앱이 원본을 보존한 관리 사본을 만들며, 실제 업로드는 게시 작업에서만 실행한다.

## 실제 게시

1. 계정, 현재 버전, 문구, 첨부와 미리보기의 확인 항목을 검토한다.
2. 현재 게시에 대한 사용자의 명시적 지시가 있으면 승인 버전을 기록한다. 승인 파일·과거 게시·계정 연결을 새 게시의 승인으로 해석하지 않는다.
3. 실제 게시 명령을 실행하고 결과 상태와 URL을 보고한다.

```bash
publish-social --json posts approve POST_ID --version CURRENT_VERSION
publish-social --json posts publish POST_ID --confirm
publish-social --json history list
```

`--confirm`은 이미 받은 실제 게시 지시를 명령에 전달하는 플래그다. 내용이나 계정 설정을 수정하면 승인이 해제된다. X 유료 API는 별도 명시 승인 후 `--allow-paid-x`를 추가하며, 토큰 발급·등록·X API 검색을 임의로 진행하지 않는다.

반복 호출 시 완료된 작업의 기존 결과를 사용한다. `uncertain` 또는 남아 있는 `publishing` 작업은 자동 재시도하지 않는다. 실제 계정을 확인하고 프로세스가 종료됐음을 확인한 뒤에만 다음 결과 확인 명령을 쓴다.

```bash
publish-social --json history resolve JOB_ID --url "https://확인한-게시-주소"
publish-social --json history resolve JOB_ID --not-published
```

미게시로 확인하면 승인이 해제된다. 다음 게시에는 다시 승인한 현재 버전이 필요하다.

## 인증과 오류

GUI에서 사용자가 직접 입력하거나 안전한 표준 입력을 통해 같은 macOS 키체인에 저장한다. 토큰·비밀번호·쿠키를 대화, 명령 인자, 로그, JSON 결과, Git에 넣지 않는다. 에이전트는 인증값을 조회해 출력하지 않는다.

명령의 JSON `ok`, 종료 코드, `data.post.status`를 함께 확인한다. 조회·초안 준비 완료와 실제 게시 성공을 구분한다. 앱 설치·계정 추가만으로 최초 인증이나 SNS 가입이 완료됐다고 주장하지 않는다.
