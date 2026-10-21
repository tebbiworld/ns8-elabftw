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
# exposes ${ELABIMG_IMAGE} / ${MYSQL_IMAGE} to the units). eLabFTW image
# (nginx + php-fpm, s6) and MySQL as recommended by upstream.
elabimg_upstream="docker.io/elabftw/elabimg:6.0.1"
mysql_image="docker.io/library/mysql:8.4.10"
# The official elabimg is rebuilt with eLabFTW releases only, so it keeps a
# vulnerable PHP for weeks (6.0.1 to 6.0.8 run PHP 8.4.25/8.4.26, affected by
# CVE-2026-109618/109619). The module runs an image derived from it with the
# PHP packages of its Alpine release upgraded to the pinned version.
php_version="8.4.27"
elabimg_image="${repobase,,}/elabimg:${elabimg_upstream##*:}-php${php_version}"

# Runtime images built here and still to be published (CI output below)
runtime_images=()

# A published tag is never rebuilt (the module label of released versions
# points to it); BUILD_ELABIMG=1 forces a local build.
if [[ -n "${BUILD_ELABIMG}" ]] || ! skopeo inspect --raw "docker://${elabimg_image}" >/dev/null 2>&1; then
    echo "Build ${elabimg_image}..."
    podman build --pull=newer \
        --build-arg="ELABIMG_UPSTREAM=${elabimg_upstream}" \
        --label="org.opencontainers.image.source=https://github.com/tebbiworld/ns8-elabftw" \
        --label="org.opencontainers.image.description=eLabFTW ${elabimg_upstream##*:} (elabimg) on PHP ${php_version}" \
        --label="org.opencontainers.image.version=${elabimg_upstream##*:}-php${php_version}" \
        -t "${elabimg_image}" elabimg
    built_php=$(podman run --rm --entrypoint php "${elabimg_image}" -r 'echo PHP_VERSION;')
    built_fpm=$(podman run --rm --entrypoint php-fpm84 "${elabimg_image}" -v | sed -n '1s/^PHP \([0-9.]*\) .*/\1/p')
    if [[ "${built_php}" != "${php_version}" || "${built_fpm}" != "${php_version}" ]]; then
        echo "elabimg runs PHP ${built_php} (php-fpm ${built_fpm}), expected ${php_version}" >&2
        exit 1
    fi
    echo "elabimg runs PHP ${built_php}"
    runtime_images+=("${elabimg_image}")
fi

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
# The bulk-data volumes can be placed on an additional disk at install time.
buildah config --entrypoint=/ \
    --label="org.nethserver.authorizations=traefik@node:routeadm" \
    --label="org.nethserver.tcp-ports-demand=1" \
    --label="org.nethserver.rootfull=0" \
    --label="org.nethserver.images=${elabimg_image} ${mysql_image}" \
    --label="org.nethserver.volumes=elabftw-uploads elabftw-exports" \
    "${container}"
buildah commit "${container}" "${repobase}/${reponame}"

images+=("${repobase}/${reponame}")

if [[ -n "${CI}" ]]; then
    printf "images=%s\n" "${images[*],,}" >> "${GITHUB_OUTPUT}"
    # runtime images are published under exactly their pinned tag
    printf "runtime_images=%s\n" "${runtime_images[*]}" >> "${GITHUB_OUTPUT}"
else
    printf "Publish the images with:\n\n"
    for image in "${runtime_images[@]}"; do printf "  buildah push %s docker://%s\n" "${image}" "${image}" ; done
    for image in "${images[@],,}"; do printf "  buildah push %s docker://%s:%s\n" "${image}" "${image}" "${IMAGETAG:-latest}" ; done
    printf "\n"
fi
