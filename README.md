# Converting dist-git to source-git

This should be similar to [How to source-git?], except that it isn't :)

The main difference is that [How to source-git?] starts with the upstream
history and applies the patches from dist-git.

In this case though, the starting point is dist-git itself, so a few things
need to be done differently.

Here are the steps:

_Note:_ things bellow were done on git.centos.org/rpms/rpm.

1. Fetch the sources from the lookaside cache.

   This will create some `tar.*` under `SOURCES`.

2. Unpack the `tar` to `src/rpm`.

3. Now applying the patches (from the `SOURCES` directory) can begin. In order
   to decide which patches to apply, look in the spec-file. Use
   [rebase-helper's `get_applied_patches()`] for this.

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

In order to have the script and it's dependencies installed in an isolated
environment, create and activate a virtual environment:

```
$ virtualenv ~/.virtualenvs/dist-git-to-source-git
$ source ~/.virtualenvs/dist-git-to-source-git/bin/activate
```

Install the script:

```
$ pip install -e .
```

Create a symlink to the script in a directory in your `PATH`:

```
$ ln -s ~/.virtualenvs/dist-git-to-source-git/bin/dist2src ~/bin/dist2src
```

The script is available even after deactivating the virtual environment:

```
$ deactivate
$ dist2src --help
Usage: dist2src [OPTIONS] COMMAND [ARGS]...
.
.
.
```

Alternatively you can install in your users home directory with:

```
$ pip install -u .
```

`dist2src get-archive` calls [`get_sources.sh`] or the script specified in
`DIST2SRC_GET_SOURCES`, so you either need to get and place this script in a
directory in your PATH or use the environment variable to specify the tools to
download the sources from the lookaside cache of the dist-git of your choice.

## The Process

When creating a source-git commit from dist-git, the process will be the
following:

1. Take the content of the lookaside cache from a dist-git commit.

2. Apply the patches from the same commit (more or less the way it's described
   above).

3. Create a source-git commit from whatever the above results in.

Simply put:

    $ cd git.centos.org
    $ dist2src convert rpms/rpm:c8s src/rpm:c8s

Or breaking it down:

    $ cd git.centos.org
    $ dist2src checkout rpms/rpm c8s
    $ dist2src checkout --orphan src/rpm c8s
    $ dist2src get-archive rpms/rpm
    $ dist2src extract-archive rpms/rpm src/rpm
    $ dist2src copy-spec rpms/rpm src/rpm
    $ dist2src add-packit-config src/rpm
    $ dist2src copy-patches rpms/rpm src/rpm
    $ dist2src apply-patches src/rpm

## Using `rpmbuild -bp` to generate source-git repositories

`convert-with-prep` is a slightly different approach than the original
one as instead of parsing the SPEC-file to apply the patches it relies on
`rpmbuild -bp` to run the `%prep` stage from the spec file which results
in a directory containing the unpacked sources (under `./BUILD/*`).

With the following RPM-macro tweaks this directory can be turned into a Git
repository from where the script can pull the history resulting from the
conversion:

- `__scm` is always `git`—this way all `%autosetup` macros will result in a
  Git repository, even the ones which are missing the `-S git[_am]` flag.
- SPEC-files which use `%setup` are modified before the conversion to use
  `%gitsetup` instead. `%gitsetup` is a [custom macro](macros.packit), which
  makes the `%prep` section to be executed similar to how `%autosetup` would
  do: initializes a Git repository and applies the patches [as Git
  commits](packitpatch). Currently it will also create a "various changes"
  commit to capture any modification of the exploded sources which happens
  additionally to applying the patches.

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
    dist2src convert-with-prep rpms/<package>:<branch> source-git/<package>:<pranch>
```

Where the current working directory has the package cloned in an `rpms`
sub-directory and the resulting source-git repo is going to be stored in
`source-git`.

[how to source-git?]: https://packit.dev/docs/source-git/how-to-source-git/
[`get_sources.sh`]: https://wiki.centos.org/Sources#get_sources.sh_script
[rebase-helper's `get_applied_patches()`]: https://github.com/rebase-helper/rebase-helper/blob/e98f4f6b14e2ca2e8cbb8a8fbeb6935e5d0cf289/rebasehelper/specfile.py#L351
