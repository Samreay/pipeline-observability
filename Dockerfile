FROM python:3.12-slim AS builder

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y git curl gcc libpq-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_PROJECT_ENVIRONMENT=/usr/local/ \
    UV_PYTHON=/usr/local/bin/python \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1


WORKDIR /workspace
ARG PACKAGE

# Install third party dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
      uv sync --all-extras --frozen --no-install-workspace --no-dev --package $PACKAGE

# Now copy in our code and install local packages
COPY projects /workspace/projects
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
      uv sync --all-extras --frozen --no-dev --package $PACKAGE

RUN chmod +x /workspace/projects/$PACKAGE/src/$PACKAGE/start.sh
WORKDIR /workspace/projects/$PACKAGE/src/$PACKAGE
CMD [ "./start.sh" ]