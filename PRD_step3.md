# PRD - Step 3: 사용자 프로필 및 레시피 저장

## 1. 개요
사용자 계정을 만들고, Step 2에서 생성된 레시피를 프로필에 저장/조회/삭제할 수 있게 한다.

## 2. 목표
- 간단한 회원가입/로그인으로 사용자를 식별한다.
- 로그인한 사용자가 마음에 든 레시피를 저장하고, 마이페이지에서 다시 볼 수 있다.

## 3. 사용자 흐름
1. 사용자가 이메일/비밀번호로 회원가입 또는 로그인한다.
2. Step 2 결과 화면에서 레시피 카드의 "저장" 버튼을 누른다.
3. 저장된 레시피는 마이페이지(레시피함)에서 목록으로 확인 가능하다.
4. 마이페이지에서 저장된 레시피를 삭제할 수 있다.

## 4. 기능 요구사항
- 인증: 이메일 + 비밀번호 기반 회원가입/로그인 (비밀번호는 해시 저장, 평문 저장 금지).
- 프로필 정보(선택 항목): 닉네임, 알레르기/비선호 재료 목록 (추후 레시피 필터링에 활용 가능하나 이번 단계는 저장만).
- 레시피 저장: 로그인 사용자만 저장 가능. 비로그인 상태에서 저장 시도 시 로그인 유도.
- 레시피함: 저장일 기준 최신순 정렬, 개별 삭제 가능.

## 5. 데이터 모델 (JSON 파일 기반)
- 별도 DB 없이 서버 로컬에 JSON 파일로 저장한다 (예: `data/users.json`, `data/recipes.json`).
- 파일 접근/쓰기는 항상 서버 사이드에서만 수행하고, 동시 쓰기 충돌 방지를 위해 파일 단위 락(또는 단순 순차 처리)을 둔다.

**`data/users.json`** — 사용자 목록 (배열)

| 필드 | 타입 | 설명 |
|---|---|---|
| id | string | 사용자 고유 ID (예: `u_1`) |
| email | string | 로그인 이메일, 유일값 |
| password_hash | string | 해싱된 비밀번호 (평문 저장 금지) |
| nickname | string | 닉네임 |
| created_at | string (ISO 8601) | 가입 일시 |

**`data/recipes.json`** — 저장된 레시피 목록 (배열)

| 필드 | 타입 | 설명 |
|---|---|---|
| id | string | 레시피 고유 ID (예: `r_1`) |
| user_id | string | 소유자(`users.json`의 id) |
| title | string | 레시피 제목 |
| used_ingredients | string[] | 사용된 보유 재료 목록 |
| extra_ingredients | string[] | 추가로 필요한 재료 목록 |
| steps | string[] | 조리 순서 |
| cook_time_minutes | number | 예상 조리 시간(분) |
| difficulty | string | 난이도 (예: 쉬움/보통/어려움) |
| saved_at | string (ISO 8601) | 저장 일시 |

## 6. API 스펙 (초안)
```
POST /api/auth/signup   { email, password, nickname } -> 201
POST /api/auth/login    { email, password } -> 200 { token }
POST /api/recipes/save  (auth 필요) { recipe 객체 } -> 201
GET  /api/recipes/saved (auth 필요) -> { recipes: [...] }
DELETE /api/recipes/saved/:id (auth 필요) -> 204
```

## 7. 비기능 요구사항
- 인증 토큰(세션 또는 JWT)으로 저장/조회/삭제 API를 보호한다.
- 비밀번호는 반드시 해싱(bcrypt 등) 후 저장하며, 평문 비밀번호가 JSON 파일에 그대로 남지 않도록 한다.
- `data/*.json` 파일은 웹 서버의 정적 파일 경로 밖에 두어 외부에서 직접 요청으로 다운로드되지 않게 한다.
- 다른 사용자의 레시피는 조회/삭제할 수 없도록 소유권 검증 필수.

## 8. 완료 기준 (Acceptance Criteria)
- 회원가입 후 로그인이 정상 동작한다.
- Step 2에서 생성한 레시피를 저장하면 마이페이지에서 확인된다.
- 삭제한 레시피는 목록에서 사라진다.
- 로그인하지 않은 상태에서는 저장/조회/삭제 API가 거부된다.

## 9. 제외 범위 (Out of Scope)
- 소셜 로그인, 레시피 공유/커뮤니티 기능
- 알레르기/선호 재료 기반 자동 필터링 (프로필 데이터만 저장, 활용은 향후 단계)


## 10. 기술스택
python, flask, supabase 이용