## Deployment for dist2src-update service

See [roles/deploy/README.md](roles/deploy/README.md) for instructions, short version:

- create (or symlink) [roles/deploy/files/secrets/](roles/deploy/files/secrets)
- define `api_key` in [roles/deploy/vars/main.yml](roles/deploy/vars/main.yml) (.gitignore-d) and run `make deploy`
- OR define `api_key` in [roles/deploy/vars/local.yml](roles/deploy/vars/local.yml) and run `DEPLOYMENT=local make deploy`
