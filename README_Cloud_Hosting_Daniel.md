# Cloud Hosting Guide for Med42 Large Model (70B/80B)

This guide covers:

1. Which service to use
2. How to deploy the large model
3. How to connect it to the existing model router in this repo

---

## 1) Recommended service

### Recommended default: AWS EC2 GPU + vLLM (OpenAI-compatible API)

Why this is the best fit for your codebase now:

- You already implemented router support for `openai` and `tgi` styles.
- vLLM gives high throughput, continuous batching, and an OpenAI-compatible endpoint.
- Fastest practical route to production-like hosting with full control.

### When to choose TGI instead

Choose TGI if your team already standardizes on Hugging Face TGI APIs and tooling.
Your router already supports TGI (`generated_text`) responses.

### Alternative providers (quick start)

- Together / Fireworks / similar managed inference
- Faster startup, less infra work
- Less control over networking/compliance hardening

---

## 2) Capacity planning before deployment

For Med42 70B/80B class models, plan GPU memory carefully.

Practical guidance:

- 70B/80B in FP16 often needs multi-GPU (commonly 4x A100 80GB or more)
- Quantized variants (AWQ/GPTQ/INT4) reduce memory and cost, with some quality tradeoff
- Start with a staging endpoint first, benchmark latency/quality, then scale

On AWS, common choices:

- `p4d/p4de` (A100)
- `p5` (H100)
- `g6e` for cost-sensitive experimentation (validate compatibility first)

---

## 3) AWS architecture (recommended)

Use this minimal production architecture:

1. EC2 GPU instance in private subnet (model server)
2. Internal ALB or NLB in front of model server
3. API Gateway or backend direct VPC call (depending on your architecture)
4. Security group allowing only backend service/network to call inference
5. CloudWatch logs + alarms

If your backend runs outside AWS, expose via HTTPS and strict auth token + IP restrictions.

---

## 4) Deploy Med42 with vLLM (OpenAI-compatible)

### 4.1 Provision EC2 GPU

- Launch Ubuntu 22.04 GPU AMI (or NVIDIA Deep Learning AMI)
- Attach enough EBS for model weights
- Install Docker + NVIDIA Container Toolkit

### 4.2 Pull model weights

- Store model in local disk/EBS (or mount from object store if needed)
- Ensure license/compliance is satisfied for your chosen Med42 checkpoint

### 4.3 Start vLLM server

Example pattern:

```bash
docker run --gpus all --rm -p 8000:8000 \
  -v /models:/models \
  vllm/vllm-openai:latest \
  --model /models/med42-80b \
  --tensor-parallel-size 4 \
  --dtype float16 \
  --max-model-len 4096
```

Adjust `--tensor-parallel-size` to number of GPUs and available VRAM.

### 4.4 Health check

- Verify endpoint responds on `/v1/models`
- Test one request on `/v1/chat/completions`

---

## 5) (Optional) Deploy with TGI instead

If you choose TGI, expose a `/generate` endpoint and configure backend style as `tgi`.

Your existing router supports both:

- OpenAI-compatible: `choices[0].message.content`
- TGI: `generated_text`

---

## 6) Integrate with your current code

Your integration points are already in place:

- Router logic: [backend/src/services/model_router.py](backend/src/services/model_router.py)
- Chat endpoint usage: [backend/src/api/chats.py](backend/src/api/chats.py)

Set backend environment variables (already scaffolded in compose):

- `MODEL_CLOUD_URL=https://<your-cloud-endpoint>/v1/chat/completions` (for vLLM)
- `MODEL_CLOUD_API_STYLE=openai`
- `MODEL_CLOUD_NAME=med42-80b`
- `MODEL_CLOUD_API_KEY=<token>`

For local model endpoint:

- `MODEL_LOCAL_URL=http://host.docker.internal:80/generate` (or your colleague URL)
- `MODEL_LOCAL_API_STYLE=tgi` (or `openai` if local server is OpenAI-style)
- `MODEL_LOCAL_NAME=med42-7b`

Routing/tuning knobs:

- `MODEL_ROUTER_FORCE_TARGET=auto`
- `MODEL_ROUTER_CLOUD_MIN_TOKENS=500`
- `MODEL_ROUTER_CLOUD_MIN_COMPLEXITY=2`
- `MODEL_TIMEOUT_SECONDS=60`

---

## 7) Smoke test checklist

1. Set `MODEL_ROUTER_FORCE_TARGET=cloud` and send one chat message
2. Verify response returns from cloud endpoint
3. Set `MODEL_ROUTER_FORCE_TARGET=local` and repeat
4. Restore `auto`
5. Temporarily break cloud URL to verify fallback to local works

---

## 8) Security baseline (minimum)

- HTTPS only
- Bearer auth token required
- Restrict source IPs/security groups to backend only
- Avoid sending raw PHI where possible; redact if policy requires
- Log request IDs, latency, model target, and error codes (not sensitive payloads)

---

## 9) Cost control baseline

- Autoscale down in off-hours (if orchestration allows)
- Keep max output tokens bounded
- Route simple prompts to local 7B
- Add request timeout/circuit breaker to avoid long GPU hangs

---

## 10) Suggested next implementation in this repo

To make operations easier, add:

1. `/admin/router-test` endpoint returning route decision for input text
2. Structured route telemetry (target, reason, latency, fallback used)
3. Health probe for cloud endpoint in backend startup diagnostics

This will help you tune thresholds quickly and prove behavior during demos.
