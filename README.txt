QUICK SUMMARY

Med42 Inference Server – Usage Summary

The Med42-70B model is served on guell.cs.ucl.ac.uk via Hugging Face Text
Generation Inference (TGI) and exposed as a local HTTP API.

The model runs unchanged and is intended to be used by a downstream RAG backend.


API

Health check:

GET http://127.0.0.1:80/health


Text generation:

POST http://127.0.0.1:80/generate


Example:

curl 127.0.0.1:80/generate \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{
    "inputs": "Prompt text here",
    "parameters": { "max_new_tokens": 256 }
  }'


Token Limit

Hard limit:

input_tokens + max_new_tokens <= 4096

Requests exceeding this limit return HTTP 422.

Retrieved context must be truncated or compacted to leave space for generation.


Output Format

Model output is plain text.

Structured outputs (e.g. JSON) are not guaranteed and should be validated or
post-processed by the backend.

The server must be running on guell for the API to be available.
If /health returns HTTP 200, the model is ready.


Server Control Commands (run on guell)

All service scripts are located in:

/mnt/data1/team20/serve


Start the inference server:

/mnt/data1/team20/serve/start.sh


Wait until the server is ready (recommended):

/mnt/data1/team20/serve/wait_ready.sh


Check container and health status:

/mnt/data1/team20/serve/status.sh


Run a quick JSON-format test request:

/mnt/data1/team20/serve/test_json.sh


Stop the server:

/mnt/data1/team20/serve/stop.sh


One-line start + wait:

/mnt/data1/team20/serve/start.sh && /mnt/data1/team20/serve/wait_ready.sh


Querying the Model from guell

Once the server is running and /health returns HTTP 200, the model can be queried
locally from guell via HTTP on 127.0.0.1:80.

Example request:

curl 127.0.0.1:80/generate \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{
    "inputs": "What is the role of insulin?",
    "parameters": { "max_new_tokens": 64 }
  }'

Requests must be sent from guell itself (or from a process running on guell),
as the API is bound to the local host.


FULL DOCUMENTATION


Server Information

Host: guell.cs.ucl.ac.uk
Hardware: 8 x Intel Gaudi2 (HL-225)
Runtime: Habana (HPU)
Access: SSH
Availability: until end of January


What Runs Where

Host Machine (guell)

- Stores model weights on shared disk
- Runs Docker containers
- Provides access to Gaudi2 accelerators via Habana runtime


Docker Container (tgi-med42)

- Runs Hugging Face Text Generation Inference (TGI) configured for Gaudi
- Loads the model sharded across 8 Gaudi2 devices
- Exposes a local HTTP API on port 80
- Uses --net=host, so the service is reachable at 127.0.0.1:80 on the host


Storage Locations (Shared Disk)

All persistent project data lives under:

/mnt/data1/team20


Model Files (read-only inside container)

/mnt/data1/team20/med42

Contains:

- config.json
- tokenizer.json
- special_tokens_map.json
- model-00001-of-00030.safetensors ... model-00030-of-00030.safetensors

These files are mounted read-only into the container.


Service Scripts

/mnt/data1/team20/serve

Scripts provided for convenience:

- start.sh       : launch the container
- wait_ready.sh  : wait until /health is OK
- status.sh      : container + health check
- test_json.sh   : quick structured output test
- stop.sh        : stop the container


Docker Image (Pinned for Reproducibility)

The TGI image is pinned by immutable RepoDigest to ensure reproducibility:

ghcr.io/huggingface/text-generation-inference@sha256:b9e8c12e92cdd566e02fccc3c8243877a48061206f0012e67de214fd704ced0a

Pinning ensures:

- Everyone runs the exact same TGI build
- No silent changes if latest-gaudi updates upstream


Start / Stop Commands

Start the service:

/mnt/data1/team20/serve/start.sh
/mnt/data1/team20/serve/wait_ready.sh


Convenience (start + wait):

/mnt/data1/team20/serve/start.sh && /mnt/data1/team20/serve/wait_ready.sh


Check status:

/mnt/data1/team20/serve/status.sh


Stop the service:

/mnt/data1/team20/serve/stop.sh


API Usage (Local on guell)

Health check:

curl -i http://127.0.0.1:80/health

Expected: HTTP 200 OK


Generate text:

curl http://127.0.0.1:80/generate \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"inputs":"What is the role of insulin?","parameters":{"max_new_tokens":64}}'


Confirm It Is Using Gaudi (HPU)

Run on guell:

sudo hl-smi

Expected:

- text-generation processes listed under Compute Processes
- Activity across AIP 0–7
- High HBM memory usage per device

This confirms inference is running on Gaudi2, not CPU.


Token Limits (Important for RAG)

The service is configured with:

--max-total-tokens 4096

TGI enforces:

input_tokens + max_new_tokens <= 4096

If exceeded, the server returns HTTP 422 with an error like:

inputs tokens + max_new_tokens must be <= 4096


Implications for RAG

The backend must:

- Limit retrieved context length
- Reserve space for generation (e.g. 512–1024 tokens)
- Truncate or compress retrieved chunks when necessary


Startup Time and Performance

Cold start: approximately 60–90 seconds
(model load plus Gaudi graph warmup)

Warm inference: approximately 3–4 seconds for ~64 tokens

Long startup times are expected and normal on Gaudi2.


About Output Being Cut Off Mid-Sentence

This usually happens when:

- max_new_tokens is too low
- A stop condition is triggered early

Solutions:

- Increase max_new_tokens
- Use stop sequences deliberately
- Do not rely on the model to finish naturally


JSON Output Guidance

The model can produce JSON.
It is not guaranteed to always be valid JSON.

The backend must validate and repair JSON.

Recommendation:
Treat model output as untrusted text.
Parse, validate, and fix in the backend.


RAG Architecture Plan

- Retrieval happens entirely in the backend
- Retrieved documents are injected into the prompt
- The model remains unchanged (no fine-tuning)

This approach meets project requirements and avoids costly retraining.


Persistence Notes

Docker containers are temporary by design. When a container is stopped or removed,
anything stored inside it is lost unless it was saved outside the container.

- Model weights and scripts persist on /mnt/data1/team20
- The pinned Docker image may be cached locally; otherwise Docker pulls it automatically
- All critical setup information should be preserved in this document,
  since server access ends in January