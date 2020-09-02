# Converting dist-git to source-git

This should be similar to [How to source-git?], except that it isn't :)

The main difference is that [How to source-git?] starts with the upstream
history and applies the patches from dist-git.

In this case though, the starting point is dist-git itself, so a few things
need to be done differently.

_Note:_ things bellow were done on git.centos.org/rpms/rpm.

## Intermezzo: what should happen to all the patches?

Here is what we could do with all the patches:

- Patches which are used in the spec file and are applied to the sources will
  be deleted, a.k.a they wont show up in the source-git tree.

- Patches which are used in the spec file and cannot be applied - this is
  where tooling should err out, as something bad happened in dist-git.

- Patches which are not used in the spec file will end up being in the
  source-git tree under `centos-packaging/SOURCES/`. Maintainers might want to
  clean this up in the future. Or these might be other kinds of files stored
  for yet unknown reasons.

### For the future

Are there any expectations for how the history of a source-git repo will
evolve?

What should happen when sources in dist-git are updated? Currently we will
recreate the source-git branch.

What should happen when the spec file or the patches in dist-git are updated?

## Usage

You should always run this tool in the provided container (CentOS 8) to get the
correct environment - RPM macros. See down below how to do it.

`dist2src get-archive` calls [`get_sources.sh`] or the script specified in
`DIST2SRC_GET_SOURCES`, so you either need to get and place this script in a
directory in your PATH or use the environment variable to specify the tools to
download the sources from the lookaside cache of the dist-git of your choice.

## The Process

When creating a source-git commit from dist-git, the process will be the
following:

1. Take the content of the lookaside cache from a dist-git commit.

2. Run `rpmbuild -bp` to unpack the archive and apply patches.

3. Copy spec file, other sources and rebase patches on top.

Simply put:

    $ cd git.centos.org
    $ dist2src convert rpms/rpm:c8s src/rpm:c8s

## Using `rpmbuild -bp` to generate source-git repositories

The core way of the conversion process is running `rpmbuild -bp` to execute the
`%prep` stage from the spec file which results in a directory containing the
unpacked sources (under `<dist-git>/BUILD/*`).

With the following RPM-macro tweaks this directory can be turned into a Git
repository from where the script can pull the history resulting from the
conversion:

- We override all `scm_setup` and `scm_apply` macros so they create a git repo
  from the archive and commit every patch applied.
- SPEC-files which use `%setup` are modified before the conversion to use
  `%autosetup -N` instead. This means the tool initializes a Git repository and
  applies the patches [as Git commits](packitpatch). Currently it will also
  create a "Changes after running %prep" commit to capture any modification of
  the exploded sources which happens additionally to applying the patches.

## Converting in a CentOS environment

In order to correctly evaluate the macros up to the `%prep` section, the right
target environment has to be used. This is achieved by running the conversion
script in a container, built to match the target environment. By default this
is CentOS 8.

This is currently working only if converting with `convert-with-prep`.

To build the image, run:

```
$ podman build \
    [--build-arg base_image=centos:8] \
    [--build-arg package_manager="yum -y"]  \
    -t dist2src .
```

The build arguments are optional, the defaults being `centos:8` and `yum -y`.

To run the conversion:

```
podman run --rm -v $PWD:/workdir:z \
    dist2src dist2src convert-with-prep rpms/<package>:<branch> source-git/<package>:<branch>
```

Where the current working directory has the package cloned in an `rpms`
sub-directory and the resulting source-git repo is going to be stored in
`source-git`.

[how to source-git?]: https://packit.dev/docs/source-git/how-to-source-git/
[`get_sources.sh`]: https://wiki.centos.org/Sources#get_sources.sh_script
[rebase-helper's `get_applied_patches()`]: https://github.com/rebase-helper/rebase-helper/blob/e98f4f6b14e2ca2e8cbb8a8fbeb6935e5d0cf289/rebasehelper/specfile.py#L351

## Tests

**The test suite works only with root podman, so please make sure to run it
with `CONTAINER_ENGINE='sudo podman'`.** (the reason is the way how UIDs are
mapped when running rootless)

You can find functional tests which convert real dist-git packages. They
require setup in your environment:

- Build an image with the dist2src inside (`make build`) -- you can override
  container engine of your choice with env var `CONTAINER_ENGINE`.
- Have mock installed and set up -- last step of the testing is to build the
  generated SRPM from a source-git repo using
  `mock --rebuild -r centos-stream-x86_64`).

Once prereqs are met, you can run the tests like this:

```
$ pytest-3 tests/test_convert.py::test_conversions
```

It's also possible to invoke a single case (package), the example below also
shows how to change the container engine (don't forget to build the image first
`CONTAINER_ENGINE='sudo podman' make build`):

```
$ CONTAINER_ENGINE='sudo podman' pytest-3 'tests/test_convert.py::test_conversions[rpm-c8s]'
===================================== test session starts =====================================
platform linux -- Python 3.8.5, pytest-4.6.11, py-1.8.2, pluggy-0.13.1 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/tt/g/packit-service/dist-git-to-source-git
plugins: betamax-0.8.1, celery-4.3.0, cov-2.10.0
collected 6 items

tests/test_convert.py::test_conversions[rpm-c8s] PASSED                                 [ 16%]

================================== 1 passed in 21.39 seconds ==================================
```
