#!/usr/bin/env bash
set -euo pipefail
curl -s 127.0.0.1:80/generate \
  -X POST -H 'Content-Type: application/json' \
  -d '{
    "inputs":"You must output ONLY a single valid JSON object and nothing else. Use double quotes for all strings. No trailing commas. Output exactly 3 cautions.\n\nTopic: insulin safety.\n\nJSON:\n{\"role\":\"\",\"cautions\":[\"\",\"\",\"\"]}\n\nNow fill in the values for the topic. Output must start with { and end with }.\n",
    "parameters":{"max_new_tokens":180,"do_sample":false}
  }'
echo