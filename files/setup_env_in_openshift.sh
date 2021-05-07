#!/usr/bin/bash

set -x

# Generate passwd file based on current uid, needed for git to clone repos
grep -v ^packit /etc/passwd > "${HOME}/passwd"
printf "packit:x:$(id -u):0:Packit:${HOME}:/bin/bash\n" >> "${HOME}/passwd"
export LD_PRELOAD=libnss_wrapper.so
export NSS_WRAPPER_PASSWD="${HOME}/passwd"
export NSS_WRAPPER_GROUP=/etc/group
