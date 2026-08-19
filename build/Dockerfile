# Reference build stage. No application ships with this template, so this file is one
# worked example rather than a build that runs as-is.
#
# The example is Node-shaped on purpose. config/pipeline.yaml is language-neutral where it
# can be (application.path, application.runtime, and the build commands are all empty
# placeholders), but a Dockerfile cannot be written without picking a stack, so this one
# pairs with the javascript-typescript default in languages.codeql. Both are the same
# worked example, and an adopter on another stack changes both together.
#
# To adopt: delete the COPY package.json package-lock.json lines and the npm commands, and
# replace them with your own dependency install and build steps.
#
# Preserve these properties when you do:
#
#   - Multi-stage build, so compilers, package managers, and build caches never reach the
#     runtime image.
#   - Dependencies installed with lifecycle scripts disabled, so package scripts cannot
#     execute during the build. The flag differs per package manager; npm uses
#     --ignore-scripts.
#   - Distroless runtime with no shell and no package manager, which removes the tooling an
#     attacker would use after gaining execution.
#   - A non-root user.
#   - Test files excluded from the image.
#
# Base images are pinned by tag. Pin them by digest before production use:
# docker pull <image> && docker inspect --format '{{index .RepoDigests 0}}' <image>

FROM node:26.7.0-trixie-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM node:26.7.0-trixie-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM gcr.io/distroless/nodejs24-debian13:nonroot
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER nonroot
EXPOSE 3000
CMD ["dist/main.js"]
