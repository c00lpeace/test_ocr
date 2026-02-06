# n8n 워크플로우 가이드: 이미지 + vLLM API 처리

## 📋 워크플로우 구조

```
[Form 입력] → [Switch 분기] → [파일/URL/JSON 처리] → [Merge 통합]
    → [이미지 확인] → [순차 Loop] → [API 요청 구성] → [vLLM API 호출]
    → [응답 파싱] → [텍스트 결과 표시] + [이미지 결과 표시]
                  → [최종 요약]
```

## 🔧 사전 설정 (필수)

### 1. 환경변수 설정

n8n Settings > Environment Variables에 추가:

|변수명              |값 예시                     |설명        |
|-----------------|-------------------------|----------|
|`VLLM_API_URL`   |`http://your-server:8000`|vLLM 서버 주소|
|`VLLM_MODEL_NAME`|`llava-v1.6-mistral-7b`  |사용할 모델명   |

### 2. Credentials 설정

- n8n > Credentials > 새로 생성 > **Header Auth**
  - Name: `vLLM API Key`
  - Header Name: `Authorization`
  - Header Value: `Bearer YOUR_API_KEY`
- (인증 불필요 시 HTTP Request 노드에서 authentication을 `none`으로 변경)

### 3. vLLM 서버 요구사항

vLLM이 **멀티모달(Vision) 모델**로 실행 중이어야 합니다:

```bash
# 예시: LLaVA 모델 실행
python -m vllm.entrypoints.openai.api_server \
  --model llava-hf/llava-v1.6-mistral-7b-hf \
  --chat-template template_llava.jinja \
  --max-model-len 4096
```

## 📥 임포트 방법

1. n8n 대시보드 열기
1. **Import from File** 클릭
1. `vllm_image_workflow.json` 파일 선택
1. 위 환경변수 / Credentials 설정 후 활성화

## 🔀 노드별 설명

### Step 1: Form 입력

- 웹 폼으로 입력 방식 선택 + 프롬프트 입력
- Form Trigger URL로 외부 접근 가능

### Step 2: Switch 분기

- 3가지 입력 방식에 따라 분기:
  - **파일 업로드** → base64 변환
  - **URL 입력** → 줄바꿈 기준 분리
  - **JSON 업로드** → 다양한 JSON 구조 지원

### Step 3: 지원하는 JSON 구조

```json
// 형식 1
{ "images": ["https://...", "https://..."] }

// 형식 2
{ "images": [{"url": "https://..."}, {"url": "https://..."}] }

// 형식 3
{ "data": [{"image_url": "https://..."}, {"image_url": "https://..."}] }

// 형식 4
["https://...", "https://..."]
```

### Step 4: vLLM API 호출

- OpenAI-compatible `/v1/chat/completions` 엔드포인트 사용
- 이미지: URL은 직접 전달, 파일은 base64 data URL로 전달
- `SplitInBatches`로 여러 이미지 순차 처리 (1초 간격)

### Step 5: 결과 표시

- **5-1 텍스트**: `choices[0].message.content`에서 결과 텍스트 추출
- **5-2 이미지**: 처리된 이미지를 바이너리로 변환하여 미리보기

## ⚠️ 커스터마이징 포인트

### API 응답 파싱 수정

`Code: 응답 파싱` 노드에서 vLLM 응답 구조에 맞게 수정:

```javascript
// 기본 (OpenAI-compatible)
resultText = body.choices[0].message.content;

// 커스텀 키가 있는 경우
resultText = body.your_custom_key.result;
```

### 모델 파라미터 수정

`Code: API 요청 구성` 노드에서:

```javascript
const requestBody = {
  model: 'your-model',
  max_tokens: 4096,      // 최대 토큰
  temperature: 0.3,      // 낮을수록 확정적
  top_p: 0.9,
  // 추가 vLLM 파라미터
  stop: ["\n\n"],
  frequency_penalty: 0.0
};
```

### 배치 처리 간격 조정

`Loop: 이미지 순차 처리` 노드에서 batchInterval 조정 (ms 단위)

## 🐛 트러블슈팅

|증상              |원인         |해결                    |
|----------------|-----------|----------------------|
|401 Unauthorized|API 키 오류   |Credentials 재확인       |
|연결 실패           |vLLM 서버 미실행|서버 상태 확인              |
|이미지 인식 불가       |비-Vision 모델|멀티모달 모델로 변경           |
|JSON 파싱 에러      |미지원 JSON 구조|Code 노드에서 구조 추가       |
|타임아웃            |큰 이미지/느린 서버|timeout 값 증가 (기본 120초)|