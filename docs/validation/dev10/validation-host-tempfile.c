/* Validation-host adapter: keep C temporary files in the writable workspace. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
FILE *tmpfile(void) {
    const char *root = getenv("TMPDIR");
    if (!root) return NULL;
    char *path = malloc(strlen(root) + 32);
    if (!path) return NULL;
    sprintf(path, "%s/ngspice-XXXXXX", root);
    int fd = mkstemp(path);
    if (fd >= 0) unlink(path);
    free(path);
    return fd < 0 ? NULL : fdopen(fd, "w+b");
}
FILE *tmpfile64(void) { return tmpfile(); }
