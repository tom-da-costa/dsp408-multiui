# Windows executables (web app + tracks-dsp-sim) cross-built with Wine.
#   docker buildx build --build-arg NAME=tracks-dsp-controller-windows-amd64 \
#     -f packaging/windows.Dockerfile -o dist .
FROM tobix/pywine:3.12 AS build
WORKDIR /src
COPY . .
ARG NAME=tracks-dsp-controller-windows-amd64
RUN packaging/build_windows_wine.sh "$NAME"

FROM scratch
COPY --from=build /src/dist/ /
