/* Mach-O entry point for Spektrafilm.app.
 * LaunchServices wants a real executable in Contents/MacOS. This stub
 * execs Contents/Resources/launch.sh so the rest of startup stays a script.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <mach-o/dyld.h>

int main(int argc, char **argv) {
    char raw[PATH_MAX];
    uint32_t size = (uint32_t)sizeof(raw);
    if (_NSGetExecutablePath(raw, &size) != 0) {
        fprintf(stderr, "spektrafilm: executable path is too long\n");
        return 1;
    }

    char resolved[PATH_MAX];
    if (realpath(raw, resolved) == NULL) {
        perror("spektrafilm");
        return 1;
    }

    char *slash = strrchr(resolved, '/');
    if (slash != NULL) {
        *slash = '\0';
    }

    char script[PATH_MAX];
    int written = snprintf(script, sizeof(script), "%s/../Resources/launch.sh", resolved);
    if (written < 0 || written >= (int)sizeof(script)) {
        fprintf(stderr, "spektrafilm: launch script path is too long\n");
        return 1;
    }

    char script_resolved[PATH_MAX];
    if (realpath(script, script_resolved) == NULL) {
        fprintf(stderr, "spektrafilm: missing launch script (%s)\n", script);
        return 1;
    }

    char **args = calloc((size_t)argc + 2, sizeof(char *));
    if (args == NULL) {
        fprintf(stderr, "spektrafilm: out of memory\n");
        return 1;
    }
    args[0] = "/bin/bash";
    args[1] = script_resolved;
    for (int i = 1; i < argc; i++) {
        args[i + 1] = argv[i];
    }
    args[argc + 1] = NULL;

    execv("/bin/bash", args);
    perror("spektrafilm");
    return 127;
}
