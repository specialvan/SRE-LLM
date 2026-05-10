# Multi-stage Dockerfile for the gan-matchmaking SRE decision server.
#
# Stage 1 installs the package into a dedicated virtualenv so the runtime
# image stays slim. Stage 2 copies the venv only — no build toolchain in
# the final image.
#
# Build:
#     docker build -t gan-matchmaking:latest .
# Run:
#     docker run --rm -p 8080:8080 \
#         -v $(pwd)/state:/state \
#         -e GAN_STATE_DB=/state/state.sqlite \
#         gan-matchmaking:latest
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

COPY gan_matchmaking ./gan_matchmaking
COPY README.md ./
RUN /opt/venv/bin/pip install --no-deps .

# -----------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GAN_HOST=0.0.0.0 \
    GAN_PORT=8080 \
    GAN_STATE_DB=/state/state.sqlite \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system gan \
    && useradd --system --gid gan --home /app gan \
    && mkdir -p /state \
    && chown -R gan:gan /state

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=gan:gan examples/sample_context.json /app/sample_context.json

USER gan
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=2s --start-period=5s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:${GAN_PORT}/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "gan_matchmaking.service"]
