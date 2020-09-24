# deploy

This role deploys dist2src-update service to Openshift.

## Role Variables

Variables are set in [defaults/main.yml](defaults/main.yml) and at least `api_key`
needs to be redefined in [vars/main.yml](vars/main.yml).
See also [vars/main_template.yml](vars/main_template.yml).

## Secrets

You have to create `files/secrets/` yourself.
Normally you'd just symlink existing `secrets/`,
which you get in our internal repo.

The folder should contain the following files:

- Sentry DSN (Data Source Name):
  - `sentry_dsn`

## License

MIT
