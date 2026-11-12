# Standalone Linux executable (web app, with the simulated DSP as `sim`), built for the Docker
# host's platform (or --platform linux/arm64 with QEMU). Debian bookworm keeps an older glibc
# baseline.
#   docker buildx build --platform linux/amd64 --build-arg NAME=tracks-dsp-controller-linux-amd64 \
#     -f packaging/exe.Dockerfile -o dist .
FROM python:3.12-bookworm AS build
RUN pip install --no-cache-dir uv==0.13.0
WORKDIR /src
COPY . .
ARG NAME=tracks-dsp-controller
ENV UV_PROJECT_ENVIRONMENT=/tmp/venv
RUN packaging/build_exe.sh "$NAME" && for exe in dist/*; do "./$exe" --version && "./$exe" sim --version; done

FROM scratch
COPY --from=build /src/dist/ /
