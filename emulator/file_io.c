/* File and directory handles behind the nmos-default file ports (open/read/write/close, directory listing as text). */
#include "file_io.h"

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <dirent.h>
#include <limits.h>

// Defined in emulator.c - needed for error handling during extraction
// (a callback interface would remove this dependency)
extern void restore_terminal(void);
extern void emulation_exit(int code);

FILE* files[FILE_IO_MAX_HANDLES];
DirState *dir_state[FILE_IO_MAX_HANDLES];

void files_init(FILE* input_file) {
    files[0] = input_file;
    for (size_t x = 1; x != FILE_IO_MAX_HANDLES; x++) {
        files[x] = NULL;
    }
    for (size_t x = 0; x != FILE_IO_MAX_HANDLES; x++) {
        dir_state[x] = NULL;
    }
}

uint8_t file_open_with_mode(const char* name, const char* mode) {
    uint8_t x;
    for (x = 1; x != FILE_IO_MAX_HANDLES; x++) {
        if (files[x] == NULL && dir_state[x] == NULL) {
            FILE* file = fopen(name, mode);
            if (!file) {
                return 0;
            }
	    files[x] = file;
	    return x + 1;
        }
    }
    restore_terminal();
    fprintf(stderr, "could not open file: %s: too many files open\n", name);
    emulation_exit(1);
    return 0; // unreachable
}

uint8_t file_open(const char* name) {
    return file_open_with_mode(name, "rb");
}

uint8_t file_open_for_write(const char* name) {
    return file_open_with_mode(name, "wb");
}

static int dir_filter(const struct dirent *entry) {
    return entry->d_name[0] != '.';
}

uint8_t dir_open(const char* name) {
    uint8_t slot = 0;
    for (uint8_t x = 1; x != FILE_IO_MAX_HANDLES; x++) {
        if (files[x] == NULL && dir_state[x] == NULL) {
            slot = x; break;
        }
    }
    if (slot == 0) {
        restore_terminal();
        fprintf(stderr, "could not open directory: %s: too many handles open\n", name);
        emulation_exit(1);
    }

    struct dirent **namelist;
    int n = scandir(name, &namelist, dir_filter, alphasort);
    if (n < 0) return 0;

    size_t total = 0;
    for (int i = 0; i < n; i++)
        total += 1 + strlen(namelist[i]->d_name) + 1;

    char *buf = malloc(total ? total : 1);
    size_t pos = 0;
    for (int i = 0; i < n; i++) {
        uint8_t meta = 0;
        int is_dir = 0;
        char fullpath[PATH_MAX];
        snprintf(fullpath, sizeof(fullpath), "%s/%s", name, namelist[i]->d_name);
        struct stat st;
        int have_stat = (stat(fullpath, &st) == 0);

        if (namelist[i]->d_type == DT_DIR) {
            is_dir = 1;
        } else if (namelist[i]->d_type == DT_UNKNOWN) {
            if (have_stat && S_ISDIR(st.st_mode))
                is_dir = 1;
        }
        if (is_dir) meta |= 0x01;

        if (!is_dir) {
            /* Mark "readonly" by inspecting the file's mode bits rather
             * than calling access(W_OK). Under root the access() check
             * unconditionally reports writeable (root overrides mode
             * bits), which makes this metadata wrong in any container/CI
             * environment that runs as root. The mode bits themselves
             * are the canonical "is this file marked readonly" signal,
             * matching what `ls -l` and `chmod -w` operate on. */
            if (have_stat &&
                (st.st_mode & (S_IWUSR | S_IWGRP | S_IWOTH)) == 0)
                meta |= 0x02;
        }

        buf[pos++] = meta;
        size_t namelen = strlen(namelist[i]->d_name);
        memcpy(buf + pos, namelist[i]->d_name, namelen + 1);
        pos += namelen + 1;
        free(namelist[i]);
    }
    free(namelist);

    DirState *ds = malloc(sizeof(DirState));
    ds->buffer = buf;
    ds->buf_size = pos;
    ds->buf_pos = 0;
    dir_state[slot] = ds;
    return slot + 1;
}

FILE* file_handle(uint8_t file) {
    if (file == 0 || files[file - 1] == NULL) {
        restore_terminal();
        fprintf(stderr, "file %i is not open\n", (int) file);
	emulation_exit(1);
    }
    return files[file - 1];
}

void file_close(uint8_t file) {
    if (file <= 1) {
        restore_terminal();
        fprintf(stderr, "Cannot close standard file %i\n", (int) file);
        emulation_exit(1);
    }
    if (dir_state[file - 1] != NULL) {
        DirState *ds = dir_state[file - 1];
        free(ds->buffer);
        free(ds);
        dir_state[file - 1] = NULL;
        return;
    }
    fclose(file_handle(file));
    files[file - 1] = NULL;
}

int file_read(uint8_t file) {
    return fgetc(file_handle(file));
}

int file_write(uint8_t file, uint8_t value) {
    return fputc(value, file_handle(file));
}

int files_destroy(void) {
    int unclosed_count = 0;
    for (size_t x = 1; x != FILE_IO_MAX_HANDLES; x++) {
        if (files[x] != NULL) {
	    fprintf(stderr, "File %i was not closed\n", (int) (x + 1));
            fclose(files[x]);
	    files[x] = NULL;
            unclosed_count++;
        }
        if (dir_state[x] != NULL) {
            fprintf(stderr, "File %i was not closed\n", (int) (x + 1));
            free(dir_state[x]->buffer);
            free(dir_state[x]);
            dir_state[x] = NULL;
            unclosed_count++;
        }
    }
    return unclosed_count;
}
