# Optional reproducible build helper. The digest is deliberately supplied by
# the caller after resolving a Linux amd64 image; this file never invents one.
ARG PYTHON_IMAGE=python:3.12-slim
ARG PYTHON_IMAGE_DIGEST
FROM ${PYTHON_IMAGE}@${PYTHON_IMAGE_DIGEST}

ARG PR_AGENT_SOURCE_COMMIT=53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c
ARG PR_AGENT_VERSION=0.45.0
LABEL org.lmdj.pr-agent.source-commit="${PR_AGENT_SOURCE_COMMIT}" \
      org.lmdj.pr-agent.version="${PR_AGENT_VERSION}" \
      org.lmdj.pr-agent.platform="linux/amd64"

WORKDIR /opt/lmdj/pr-agent
COPY requirements.lock /opt/lmdj/pr-agent/requirements.lock
RUN printf '%s\n' \
      'setuptools==80.9.0 --hash=sha256:062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922' \
      'wheel==0.46.1 --hash=sha256:f796f65d72750ccde090663e466d0ca37cd72b62870f7520b96d34cdc07d86d8' \
      'packaging==25.0 --hash=sha256:29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484 --hash=sha256:d443872c98d677bf60f6a1f2f8c1cb748e8fe762d2bf9d3148b5599295b0fc4f' \
      > /tmp/pr-agent-build-requirements.txt
RUN python -m pip install --no-compile --no-build-isolation --require-hashes \
      --no-deps \
      --target /opt/lmdj/pr-agent/vendor \
      -r /tmp/pr-agent-build-requirements.txt
RUN PYTHONPATH=/opt/lmdj/pr-agent/vendor python -m pip install --no-compile --no-build-isolation --require-hashes \
      --target /opt/lmdj/pr-agent/vendor \
      -r /opt/lmdj/pr-agent/requirements.lock
# The bootstrap packages are installed before the bytecode guard is applied;
# remove any installer-created bytecode before the vendor tree becomes an artifact.
RUN find /opt/lmdj/pr-agent/vendor -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /opt/lmdj/pr-agent/vendor -type f -name '*.pyc' -delete
RUN mkdir -p /opt/lmdj/pr-agent/tokenizer-cache \
    && cp /opt/lmdj/pr-agent/vendor/litellm/litellm_core_utils/tokenizers/fb374d419588a4632f3f557e76b4b70aebbca790 \
      /opt/lmdj/pr-agent/tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790 \
    && python -c "import hashlib, pathlib; p=pathlib.Path('/opt/lmdj/pr-agent/tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790'); data=p.read_bytes(); assert len(data) == 3613922; assert hashlib.sha256(data).hexdigest() == '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'"
ENV PYTHONDONTWRITEBYTECODE=1
ENV LITELLM_LOCAL_MODEL_COST_MAP=true
ENV TIKTOKEN_CACHE_DIR=/opt/lmdj/pr-agent/tokenizer-cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY pr_agent /opt/lmdj/pr-agent/pr_agent
COPY LICENSE /opt/lmdj/pr-agent/LICENSE
COPY config.toml /opt/lmdj/pr-agent/config.toml
COPY pr_agent_review.py /opt/lmdj/pr-agent/pr_agent_review.py
COPY IDENTITY /opt/lmdj/pr-agent/IDENTITY
ENV PYTHONPATH=/opt/lmdj/pr-agent/vendor:/opt/lmdj/pr-agent
RUN python -c "import importlib.metadata, platform, sys, litellm, pr_agent; version = importlib.metadata.version('litellm'); assert sys.version_info[:2] == (3, 12); assert platform.machine() == 'x86_64'; assert platform.system() == 'Linux'; assert version == '1.100.0'; print({'python': sys.version, 'platform': platform.platform(), 'pr_agent': '0.45.0', 'litellm': version})"
RUN python -c "from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler; from pr_agent.tools.pr_reviewer import PRReviewer; assert LiteLLMAIHandler.__module__ == 'pr_agent.algo.ai_handlers.litellm_ai_handler'; assert PRReviewer.__module__ == 'pr_agent.tools.pr_reviewer'; print({'PRReviewer': PRReviewer.__module__, 'LiteLLMAIHandler': LiteLLMAIHandler.__module__})"
RUN test -s /opt/lmdj/pr-agent/LICENSE
ENTRYPOINT ["python", "/opt/lmdj/pr-agent/pr_agent_review.py"]
