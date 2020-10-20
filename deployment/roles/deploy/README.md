# deploy

This role deploys dist2src-update service to Openshift.

## Role Variables

Default variables are set in [defaults/main.yml](defaults/main.yml).
At least `api_key` needs to be re-defined in a yaml file in [vars/](vars).
If you're for example deploying to prod environment, create `vars/prod.yml`,
set `api_key` there and run `DEPLOYMENT=prod make deploy`.
Don't worry, all `vars/*.yml` files are .gitignore-d.
There's also [vars/local.yml](vars/local.yml), which will be used
if you run `DEPLOYMENT=local make deploy`.

## Secrets

You have to create `files/secrets/` yourself.
Normally you'd just symlink existing `secrets/`,
which you get in our internal repo.

The folder should contain the following files:

- Sentry DSN (Data Source Name):
  - `sentry_dsn`
- Certificates needed by centosmsg listener:
  - `centos.cert`
  - `centos-server-ca.cert`
- Pagure API tokens for source-git and dist-git:
  - `src-git-token`
  - `dist-git-token`
- Private and public SSH-keys to be able to push to source-git:
  - `ssh/id_rsa`
  - `ssh/id_rsa.pub`

## License

MIT
