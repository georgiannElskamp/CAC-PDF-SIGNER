"""Adapt pinned pcsc-lite sources for an unprivileged, per-operation socket."""

import re
import sys
from pathlib import Path


def patch(root):
    header = root / "src/pcscd.h.in"
    text = header.read_text()
    start = text.index("#define PCSCLITE_IPC_DIR")
    end = text.index("\n", text.index("#define PCSCLITE_CSOCK_NAME", start))
    text = text[:start] + r'''
#include <stdlib.h>
#include <stdio.h>
#include <limits.h>

static inline const char *cac_ipc_dir(void)
{
    const char *directory = getenv("CAC_PCSC_DIR");
    if (!directory || directory[0] != '/')
    {
        fprintf(stderr, "CAC_PCSC_DIR must name a private absolute directory\n");
        exit(EXIT_FAILURE);
    }
    return directory;
}
static inline const char *cac_socket_path(void)
{
    static char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/pcscd.comm", cac_ipc_dir()) >= (int)sizeof(path))
        exit(EXIT_FAILURE);
    return path;
}
static inline const char *cac_pid_path(void)
{
    static char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/pcscd.pid", cac_ipc_dir()) >= (int)sizeof(path))
        exit(EXIT_FAILURE);
    return path;
}
#define PCSCLITE_IPC_DIR cac_ipc_dir()
#define PCSCLITE_RUN_PID cac_pid_path()
/* The client uses PCSCLITE_CSOCK_NAME from its environment first. */
#ifdef PCSCLITE_STATIC_DRIVER
#define PCSCLITE_CSOCK_NAME cac_socket_path()
#else
#define PCSCLITE_CSOCK_NAME "/run/pcscd/pcscd.comm"
#endif
''' + text[end:]
    # The daemon and its utilities need dynamic names; the client keeps its
    # normal default when connecting to an existing system reader service.
    text = text.replace("#ifdef PCSCLITE_STATIC_DRIVER", "#ifdef CAC_PRIVATE_DAEMON")
    header.write_text(text)
    for filename in ("pcscdaemon.c", "utils.c", "winscard_msg_srv.c"):
        path = root / "src" / filename
        content = path.read_text()
        content = re.sub(r'"([^"\n]*)"\s+PCSCLITE_(?:IPC_DIR|RUN_PID|CSOCK_NAME)\s+"([^"\n]*)"',
                         lambda m: '"' + m[1] + "private reader path" + m[2] + '"', content)
        content = content.replace('"cleaning " PCSCLITE_IPC_DIR', '"cleaning private reader directory"')
        content = content.replace("#include \"pcscd.h\"", "#define CAC_PRIVATE_DAEMON\n#include \"pcscd.h\"")
        content = content.replace("S_IROTH | S_IXOTH | S_IRGRP | S_IXGRP | S_IRWXU", "S_IRWXU")
        content = content.replace("S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH", "S_IRUSR | S_IWUSR")
        content = content.replace("S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH", "S_IRUSR | S_IWUSR")
        path.write_text(content)


if __name__ == "__main__":
    patch(Path(sys.argv[1]))
