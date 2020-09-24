# deploy

This role deploys dist2src-update service to Openshift.

## Role Variables

Default variables are set in [defaults/main.yml](defaults/main.yml).
At least `api_key` needs to be re-defined in a yaml file in [vars/](vars/).
There's for example [vars/local.yml](vars/local.yml) which will be used if you set
`DEPLOYMENT=local` environment variable.
If you don't specify `DEPLOYMENT`, [vars/main.yml](vars/main.yml) (which is .gitignore-d)
will be used by default.

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

## License

MIT
