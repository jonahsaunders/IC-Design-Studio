#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
FILE *tmpfile(void) {
 const char *dir=getenv("TMPDIR"); if(!dir){errno=EINVAL;return NULL;}
 char *name=NULL; if(asprintf(&name,"%s/ngspice-XXXXXX",dir)<0)return NULL;
 int fd=mkstemp(name); if(fd<0){free(name);return NULL;}
 unlink(name);free(name);FILE *f=fdopen(fd,"w+b");if(!f)close(fd);return f;
}
FILE *tmpfile64(void) {return tmpfile();}
