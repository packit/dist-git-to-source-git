# Deployment for dist2src-update service

See [roles/deploy/README.md](roles/deploy/README.md) for instructions, short version:

- create (or symlink) `roles/deploy/files/secrets/{myenvironment}`
- define `api_key` in `roles/deploy/vars/{myenvironment}.yml`
- run `DEPLOYMENT={myenvironment} make deploy`

Where `{myenvironment}` might be for example 'prod' or 'local'.

# Container images

All container images are pulled from [quay.io/packit](https://quay.io/organization/packit).

The following images are synced from Docker Hub to the namespace above, using
`skopeo`. Make sure to `podman login` to quay.io first.

[weaveworks/prom-aggregation-gateway](https://hub.docker.com/r/weaveworks/prom-aggregation-gateway):

    skopeo sync --src docker --dest docker docker.io/weaveworks/prom-aggregation-gateway:latest quay.io/packit

[nginxinc/nginx-unprivileged](https://hub.docker.com/r/nginxinc/nginx-unprivileged):

    skopeo sync --src docker --dest docker docker.io/nginxinc/nginx-unprivileged:latest quay.io/packit
