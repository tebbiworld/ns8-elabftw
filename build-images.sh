#!/bin/bash

#
# Copyright (C) 2026 tebbi
# SPDX-License-Identifier: GPL-3.0-or-later
#

set -e

images=()
repobase="${REPOBASE:-ghcr.io/tebbiworld}"
reponame="elabftw"

# Runtime images pinned through org.nethserver.images (node pre-pulls them and
# exposes ${ELABIMG_IMAGE} / ${MYSQL_IMAGE} to the units). Official eLabFTW
# image (nginx + php-fpm, s6) and MySQL as recommended by upstream.
elabimg_image="docker.io/elabftw/elabimg:6.0.1"
mysql_image="docker.io/library/mysql:8.4"

runtime_images=(
    "${elabimg_image}"
    "${mysql_image}"
)

container=$(buildah from scratch)

if ! buildah containers --format "{{.ContainerName}}" | grep -q nodebuilder-elabftw; then
    echo "Pulling NodeJS runtime..."
    buildah from --name nodebuilder-elabftw -v "${PWD}:/usr/src:Z" docker.io/library/node:24.16.0-slim
fi

echo "Build static UI files with node..."
buildah run \
    --workingdir=/usr/src/ui \
    --env="NODE_OPTIONS=--openssl-legacy-provider" \
    nodebuilder-elabftw \
    sh -c "yarn install && yarn build"

buildah add "${container}" imageroot /imageroot
buildah add "${container}" ui/dist /ui
# One TCP port: the pod publishes eLabFTW's internal port 8080 on the node
# loopback, fronted by Traefik.
buildah config --entrypoint=/ \
    --label="org.nethserver.authorizations=traefik@node:routeadm" \
    --label="org.nethserver.tcp-ports-demand=1" \
    --label="org.nethserver.rootfull=0" \
    --label="org.nethserver.images=${runtime_images[*]}" \
    "${container}"
buildah commit "${container}" "${repobase}/${reponame}"

images+=("${repobase}/${reponame}")

if [[ -n "${CI}" ]]; then
    printf "images=%s\n" "${images[*],,}" >> "${GITHUB_OUTPUT}"
else
    printf "Publish the images with:\n\n"
    for image in "${images[@],,}"; do printf "  buildah push %s docker://%s:%s\n" "${image}" "${image}" "${IMAGETAG:-latest}" ; done
    printf "\n"
fi
