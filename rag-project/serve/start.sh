#!/usr/bin/env bash
set -e

CONTAINER_NAME="tgi-med42"

IMAGE="ghcr.io/huggingface/text-generation-inference@sha256:b9e8c12e92cdd566e02fccc3c8243877a48061206f0012e67de214fd704ced0a"


MODEL_DIR="/mnt/data1/team20/med42"

docker run -d --rm \
  --name "${CONTAINER_NAME}" \
  --runtime=habana \
  --cap-add=sys_nice \
  --net=host \
  --ipc=host \
  -e HABANA_VISIBLE_DEVICES=all \
  -e OMPI_MCA_btl_vader_single_copy_mechanism=none \
  -v "${MODEL_DIR}:/data/model:ro" \
  "${IMAGE}" \
  --model-id /data/model \
  --sharded true \
  --num-shard 8 \
  --max-total-tokens 4096 \
  --max-batch-size 1

echo "Started container: ${CONTAINER_NAME}"
echo "Tail logs: docker logs -f ${CONTAINER_NAME}"

