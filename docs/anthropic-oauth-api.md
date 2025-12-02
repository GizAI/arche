# Anthropic OAuth API 사용 가이드

- 추가 참고
  - https://zp.gy/blog/how-opencode-use-claude-subscription/
  - https://opencode.ai/docs/providers

Claude CLI가 API 키 없이 OAuth 토큰으로 Anthropic API를 호출하는 방법을 분석한 결과입니다.

## 개요

Claude CLI는 `~/.claude/.credentials.json`에 저장된 OAuth 토큰을 사용하여 Anthropic API를 직접 호출합니다. 기존에는 OAuth 토큰으로는 API 호출이 불가능하다고 알려져 있었으나, 특정 베타 헤더를 사용하면 가능합니다.

## OAuth 토큰 위치

```
~/.claude/.credentials.json
```

### 토큰 구조

```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-...",
    "refreshToken": "...",
    "expiresAt": "2025-01-01T00:00:00.000Z",
    "scopes": ["user:inference", "user:profile", "user:sessions:claude_code"],
    "subscriptionType": "pro"
  }
}
```

## 필수 헤더

OAuth 토큰으로 API를 호출하려면 다음 헤더가 **필수**입니다:

| 헤더 | 값 | 설명 |
|------|-----|------|
| `Authorization` | `Bearer sk-ant-oat01-...` | OAuth 토큰 |
| `anthropic-version` | `2023-06-01` | API 버전 |
| `anthropic-beta` | `oauth-2025-04-20` | **핵심!** OAuth 베타 플래그 |
| `anthropic-dangerous-direct-browser-access` | `true` | 브라우저 직접 접근 허용 |

## 사용 가능한 API 엔드포인트

### 1. 모델 목록 조회 (`GET /v1/models`)

```python
import requests
import json

with open('~/.claude/.credentials.json') as f:
    creds = json.load(f)
token = creds['claudeAiOauth']['accessToken']

headers = {
    'Authorization': f'Bearer {token}',
    'anthropic-version': '2023-06-01',
    'anthropic-beta': 'oauth-2025-04-20',
    'anthropic-dangerous-direct-browser-access': 'true',
}

response = requests.get('https://api.anthropic.com/v1/models', headers=headers)
print(response.json())
```

**응답 예시:**
```json
{
  "data": [
    {"type": "model", "id": "claude-opus-4-5-20251101", "display_name": "Claude Opus 4.5"},
    {"type": "model", "id": "claude-sonnet-4-5-20250929", "display_name": "Claude Sonnet 4.5"},
    {"type": "model", "id": "claude-haiku-4-5-20251001", "display_name": "Claude Haiku 4.5"}
  ]
}
```

### 2. 메시지 생성 (`POST /v1/messages`)

```python
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json',
    'anthropic-version': '2023-06-01',
    'anthropic-beta': 'oauth-2025-04-20',
    'anthropic-dangerous-direct-browser-access': 'true',
}

data = {
    'model': 'claude-haiku-4-5-20251001',
    'max_tokens': 1000,
    'messages': [{'role': 'user', 'content': 'Hello!'}]
}

response = requests.post(
    'https://api.anthropic.com/v1/messages',
    headers=headers,
    json=data
)
print(response.json())
```

### 3. 토큰 카운트 (`POST /v1/messages/count_tokens`)

```python
headers['anthropic-beta'] = 'oauth-2025-04-20,token-counting-2024-11-01'

data = {
    'model': 'claude-opus-4-5-20251101',
    'messages': [{'role': 'user', 'content': 'Hello!'}]
}

response = requests.post(
    'https://api.anthropic.com/v1/messages/count_tokens',
    headers=headers,
    json=data
)
```

## 추가 베타 플래그

CLI에서 사용하는 전체 베타 플래그:

```
oauth-2025-04-20
interleaved-thinking-2025-05-14
context-management-2025-06-27
tool-examples-2025-10-29
claude-code-20250219
token-counting-2024-11-01
```

## 기타 API 엔드포인트

패킷 캡처에서 발견된 추가 엔드포인트:

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/oauth/claude_cli/client_data` | GET | 클라이언트 데이터 |
| `/api/oauth/account/settings` | GET/PATCH | 계정 설정 조회/변경 |
| `/api/oauth/profile` | GET | 계정 및 조직 프로필 정보 |
| `/api/oauth/usage` | GET | 사용량 정보 |
| `/api/claude_code_grove` | GET | Grove(데이터 수집) 정책 상태 |
| `/api/oauth/account/grove_notice_viewed` | POST | Grove 알림 확인 표시 |

**주의:** 일부 엔드포인트는 `User-Agent: claude-cli/x.x.x` 헤더가 필요합니다.

---

## 사용량 조회 API

### 사용량 조회 (`GET /api/oauth/usage`)

```python
headers = {
    'Authorization': f'Bearer {token}',
    'anthropic-beta': 'oauth-2025-04-20',
    'User-Agent': 'claude-cli/2.0.56 (external, cli)',
}

response = requests.get('https://api.anthropic.com/api/oauth/usage', headers=headers)
```

**응답 예시:**
```json
{
  "five_hour": {
    "utilization": 28.0,
    "resets_at": "2025-12-03T00:00:00.208132+00:00"
  },
  "seven_day": {
    "utilization": 14.0,
    "resets_at": "2025-12-08T21:00:00.208156+00:00"
  },
  "seven_day_oauth_apps": {
    "utilization": 0.0,
    "resets_at": null
  },
  "seven_day_opus": null,
  "seven_day_sonnet": {
    "utilization": 4.0,
    "resets_at": "2025-12-08T23:00:00.208171+00:00"
  },
  "iguana_necktie": null,
  "extra_usage": {
    "is_enabled": true,
    "monthly_limit": 2000,
    "used_credits": 1338.0,
    "utilization": 66.9
  }
}
```

| 필드 | 설명 |
|------|------|
| `five_hour.utilization` | 5시간 사용량 (%) |
| `seven_day.utilization` | 7일 전체 사용량 (%) |
| `seven_day_sonnet.utilization` | Sonnet 모델 7일 사용량 (%) |
| `extra_usage.monthly_limit` | 월간 추가 사용량 한도 (크레딧) |
| `extra_usage.used_credits` | 사용한 추가 크레딧 |
| `extra_usage.utilization` | 추가 사용량 비율 (%) |

---

## 프로필 조회 API

### 프로필 조회 (`GET /api/oauth/profile`)

```python
headers = {
    'Authorization': f'Bearer {token}',
    'anthropic-beta': 'oauth-2025-04-20',
    'User-Agent': 'claude-cli/2.0.56 (external, cli)',
}

response = requests.get('https://api.anthropic.com/api/oauth/profile', headers=headers)
```

**응답 예시:**
```json
{
  "account": {
    "uuid": "1ad79a19-41d0-4191-a2c7-6f55cb2456e7",
    "full_name": "username",
    "display_name": "username",
    "email": "user@example.com",
    "has_claude_max": true,
    "has_claude_pro": false
  },
  "organization": {
    "uuid": "243a2aa4-7bd6-4d4b-afe4-b81f36260e81",
    "name": "user@example.com's Organization",
    "organization_type": "claude_max",
    "billing_type": "stripe_subscription",
    "rate_limit_tier": "default_claude_max_20x",
    "has_extra_usage_enabled": true
  }
}
```

| 필드 | 설명 |
|------|------|
| `account.uuid` | 계정 고유 ID |
| `account.has_claude_max` | Max 플랜 여부 |
| `account.has_claude_pro` | Pro 플랜 여부 |
| `organization.organization_type` | 조직 유형 (`claude_max`, `claude_pro`) |
| `organization.rate_limit_tier` | Rate limit 티어 |
| `organization.has_extra_usage_enabled` | 추가 사용량 활성화 여부 |

---

## Grove (데이터 수집 정책)

### Grove란?

Grove는 "Help improve Claude" 기능으로, 사용자의 대화 데이터를 모델 학습에 사용할지 결정하는 프라이버시 설정입니다.

### Grove API 엔드포인트

#### 1. Grove 상태 조회 (`GET /api/claude_code_grove`)

```python
headers = {
    'Authorization': f'Bearer {token}',
    'anthropic-beta': 'oauth-2025-04-20',
    'User-Agent': 'claude-cli/2.0.56 (external, cli)',  # 필수!
}

response = requests.get('https://api.anthropic.com/api/claude_code_grove', headers=headers)
```

**응답:**
```json
{
  "grove_enabled": true,
  "domain_excluded": false,
  "notice_is_grace_period": false,
  "notice_reminder_frequency": 0
}
```

| 필드 | 설명 |
|------|------|
| `grove_enabled` | 조직/플랜 레벨에서 데이터 수집이 활성화되었는지 |
| `domain_excluded` | 도메인이 데이터 수집에서 제외되었는지 |
| `notice_is_grace_period` | 알림 유예 기간 여부 |
| `notice_reminder_frequency` | 알림 표시 주기 (일) |

#### 2. 계정 설정에서 Grove 변경 (`PATCH /api/oauth/account/settings`)

```python
headers = {
    'Authorization': f'Bearer {token}',
    'anthropic-beta': 'oauth-2025-04-20',
    'User-Agent': 'claude-cli/2.0.56 (external, cli)',
    'Content-Type': 'application/json',
}

# Grove 비활성화
response = requests.patch(
    'https://api.anthropic.com/api/oauth/account/settings',
    headers=headers,
    json={"grove_enabled": False}
)
# Status: 202 Accepted
```

### Grove 설정의 두 레벨

1. **개인 설정** (`/api/oauth/account/settings`)
   - 사용자가 직접 변경 가능
   - `grove_enabled: true/false`

2. **조직/플랜 정책** (`/api/claude_code_grove`)
   - 조직 또는 플랜 레벨에서 강제
   - 개인 설정보다 우선

**예시:** Max 플랜의 경우 개인 설정을 `false`로 해도 조직 정책이 `true`면 데이터 수집이 활성화됨.

### 데이터 수집 범위

Grove가 `true`일 때:
- `/v1/messages`로 전송된 대화 데이터가 모델 학습에 **사용될 수 있음**
- 대화 내용, 프롬프트, 응답이 포함됨

Grove가 `false`일 때:
- 대화 데이터는 API 호출에 필요하므로 서버로 전송되지만
- 모델 학습에는 **사용되지 않음**

---

## 계정 설정 상세

### 계정 설정 조회 (`GET /api/oauth/account/settings`)

```python
response = requests.get(
    'https://api.anthropic.com/api/oauth/account/settings',
    headers=headers
)
```

**주요 설정 필드:**

| 필드 | 설명 |
|------|------|
| `grove_enabled` | 개인 데이터 수집 동의 여부 |
| `grove_updated_at` | Grove 설정 변경 시간 |
| `enabled_web_search` | 웹 검색 활성화 |
| `paprika_mode` | Extended Thinking 모드 (`extended`/`normal`) |
| `enabled_saffron` | Saffron 기능 활성화 |
| `enabled_saffron_search` | Saffron 검색 활성화 |

### 기능 코드네임 목록

CLI 분석에서 발견된 내부 기능 코드네임들:

| 코드네임 | 추정 기능 |
|----------|----------|
| `paprika_mode` | Extended Thinking |
| `saffron` / `saffron_search` | 검색 관련 기능 |
| `turmeric` | 미확인 |
| `sourdough` / `foccacia` | 미확인 |
| `yukon_gold` | 미확인 |
| `wiggle_egress` | 외부 연결 관련 |
| `bananagrams` | 미확인 |
| `monkeys_in_a_barrel` | 미확인 |

---

## 텔레메트리

### DataDog 로그

CLI는 운영 메트릭을 DataDog으로 전송합니다:

**엔드포인트:** `https://http-intake.logs.datadoghq.com/api/v2/logs`

**전송 데이터 (대화 내용 미포함):**
```json
{
  "message": "tengu_api_success",
  "model": "claude-haiku-4-5-20251001",
  "session_id": "...",
  "input_tokens": 1176,
  "output_tokens": 134,
  "duration_ms": 2888,
  "cost_u_s_d": 0.001846,
  "platform": "linux",
  "version": "2.0.56"
}
```

**참고:** 텔레메트리에는 실제 프롬프트나 응답 내용이 포함되지 않습니다.

**전체 DataDog 로그 필드:**

| 필드 | 설명 |
|------|------|
| `message` | 로그 유형 (`tengu_api_success`, `tengu_api_error`) |
| `model` | 사용된 모델 ID |
| `session_id` | 세션 ID |
| `user_type` | 사용자 유형 (`external`, `internal`) |
| `betas` | 사용된 베타 플래그 목록 |
| `entrypoint` | 진입점 (`cli`) |
| `is_interactive` | 대화형 모드 여부 |
| `client_type` | 클라이언트 유형 (`cli`) |
| `platform` | 플랫폼 (`linux`, `darwin`, `win32`) |
| `arch` | 아키텍처 (`x64`, `arm64`) |
| `node_version` | Node.js 버전 |
| `terminal` | 터미널 유형 (`vscode`, `iterm2` 등) |
| `package_managers` | 감지된 패키지 매니저 |
| `runtimes` | 감지된 런타임 |
| `is_ci` | CI 환경 여부 |
| `is_claude_ai_auth` | OAuth 인증 사용 여부 |
| `version` | CLI 버전 |
| `input_tokens` | 입력 토큰 수 |
| `output_tokens` | 출력 토큰 수 |
| `cached_input_tokens` | 캐시된 입력 토큰 수 |
| `duration_ms` | API 호출 소요 시간 (ms) |
| `ttft_ms` | 첫 토큰까지 시간 (ms) |
| `cost_u_s_d` | 비용 (USD) |
| `query_source` | 쿼리 소스 (`agent:builtin:Explore` 등) |
| `permission_mode` | 권한 모드 |

### Statsig (A/B 테스트)

**엔드포인트:**
- `https://statsig.anthropic.com/v1/initialize` - 기능 플래그 초기화
- `https://statsig.anthropic.com/v1/rgstr` - 이벤트 등록

**Initialize 요청 예시:**
```json
{
  "user": {
    "customIDs": {
      "sessionId": "1e56209f-a1c5-41c1-87a4-1f4f1498dbe4",
      "organizationUUID": "243a2aa4-7bd6-4d4b-afe4-b81f36260e81",
      "accountUUID": "1ad79a19-41d0-4191-a2c7-6f55cb2456e7"
    },
    "userID": "f7d53c1f2a5708d81bcac3b488a28fe8c554e36a66273f9c2a93c8e9130ab3c6",
    "appVersion": "2.0.56",
    "custom": {
      "userType": "external",
      "subscriptionType": "max",
      "firstTokenTime": 1758618671174
    },
    "statsigEnvironment": {
      "tier": "production"
    }
  }
}
```

| 필드 | 설명 |
|------|------|
| `userID` | 해시된 사용자 ID |
| `custom.userType` | 사용자 유형 (`external`, `internal`) |
| `custom.subscriptionType` | 구독 유형 (`max`, `pro`, `free`) |
| `custom.firstTokenTime` | 첫 토큰 발행 시간 (Unix timestamp) |

---

## 전체 계정 설정 필드

`/api/oauth/account/settings` 응답에서 발견된 모든 필드:

| 필드 | 타입 | 설명 |
|------|------|------|
| `input_menu_pinned_items` | array | 고정된 메뉴 항목 |
| `has_seen_mm_examples` | bool | MM 예시 확인 여부 |
| `has_started_claudeai_onboarding` | bool | 온보딩 시작 여부 |
| `has_finished_claudeai_onboarding` | bool | 온보딩 완료 여부 |
| `dismissed_claudeai_banners` | array | 닫은 배너 목록 |
| `enabled_artifacts_attachments` | bool | Artifacts 첨부 활성화 |
| `enabled_turmeric` | bool | Turmeric 기능 |
| `enable_chat_suggestions` | bool | 채팅 제안 활성화 |
| `enabled_mm_pdfs` | bool | MM PDF 활성화 |
| `enabled_gdrive` | bool | Google Drive 연동 |
| `enabled_bananagrams` | bool | Bananagrams 기능 |
| `enabled_gdrive_indexing` | bool | Google Drive 인덱싱 |
| `enabled_web_search` | bool | 웹 검색 활성화 |
| `enabled_compass` | bool | Compass 기능 |
| `enabled_sourdough` | bool | Sourdough 기능 |
| `enabled_foccacia` | bool | Foccacia 기능 |
| `enabled_yukon_gold` | bool | Yukon Gold 기능 |
| `enabled_geolocation` | bool | 지리 위치 활성화 |
| `enabled_mcp_tools` | bool | MCP 도구 활성화 |
| `paprika_mode` | string | Extended Thinking 모드 (`extended`/`normal`) |
| `enabled_monkeys_in_a_barrel` | bool | Monkeys in a Barrel 기능 |
| `enabled_wiggle_egress` | bool | 외부 연결 기능 |
| `wiggle_egress_allowed_hosts` | array | 허용된 외부 호스트 |
| `wiggle_egress_hosts_template` | string | 외부 호스트 템플릿 |
| `enabled_saffron` | bool | Saffron 기능 |
| `enabled_saffron_search` | bool | Saffron 검색 활성화 |
| `grove_enabled` | bool | 데이터 수집 동의 |
| `grove_updated_at` | datetime | Grove 설정 변경 시간 |
| `grove_notice_viewed_at` | datetime | Grove 알림 확인 시간 |

---

## 참고 사항

1. **토큰 갱신**: OAuth 토큰은 만료될 수 있으며, `refreshToken`을 사용하여 갱신해야 합니다.

2. **Scope 제한**: 현재 scope가 `user:inference`를 포함해야 API 호출이 가능합니다.

3. **Rate Limit**: Pro 구독 기준 rate limit이 적용됩니다.

4. **베타 기능**: `oauth-2025-04-20`는 베타 기능이므로 향후 변경될 수 있습니다.

## 분석 방법

이 문서는 mitmproxy를 사용한 패킷 캡처로 분석되었습니다:

```bash
# mitmproxy 설치
pip install mitmproxy

# 프록시 시작
mitmdump -w /tmp/traffic.flow -p 10001

# 프록시를 통해 CLI 호출
HTTPS_PROXY=http://127.0.0.1:10001 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
claude --print "hello"

# 캡처 분석
python3 << 'EOF'
from mitmproxy import io as mio
with open("/tmp/traffic.flow", "rb") as f:
    for flow in mio.FlowReader(f).stream():
        if hasattr(flow, 'request'):
            print(flow.request.url)
            print(dict(flow.request.headers))
EOF
```

---

*문서 작성일: 2024-12-03*
*분석 대상: Claude CLI 2.0.56*
