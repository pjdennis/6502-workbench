"""The Lathe compiler's main program.

    lathec SOURCE.lth OUTDIR [IMPORTDIR...]

Compiles one module in one pass: SRC and LEX turn the file into tokens; DECL, STMT and EXPR
parse them; GEN chooses instructions, which FBUF holds until each function ends; OUT writes
the object file OUTDIR/name.lo, and DECL the interface OUTDIR/name.li. Owns the command line
and the order in which the components start.
"""
import decl
import env
import err
import gen
import kernel
import lex
import out
import src
import typetab

C_SLASH = 0x2F
C_UNDERSCORE = 0x5F
SOURCE_ENDING = b".lth"
OBJECT_ENDING = b".lo"


def has_source_ending(stop):
    """True if the text that stops at `stop` ends with `.lth`, in either case."""
    for i in range(0, len(SOURCE_ENDING)):
        if lex.fold(env.mem[stop - len(SOURCE_ENDING) + i]) != SOURCE_ENDING[i]:
            return False
    return True


def module_name(source):
    """The name of the module in the file whose name is at `source`: the file's name without
    its directories and its `.lth`, in lower case. It must be a name the language allows."""
    start = source
    stop = source
    while env.mem[stop] != 0:
        if env.mem[stop] == C_SLASH:
            start = stop + 1
        stop += 1
    if stop - start <= len(SOURCE_ENDING) or not has_source_ending(stop) or not lex.is_letter(env.mem[start]):
        err.fatal(err.E_SOURCE_NAME)
    kernel.name_begin()
    for i in range(start, stop - len(SOURCE_ENDING)):
        ch = env.mem[i]
        if not lex.is_letter(ch) and not lex.is_digit(ch) and ch != C_UNDERSCORE:
            err.fatal(err.E_SOURCE_NAME)
        kernel.name_add(lex.fold(ch))
    return kernel.name_end()


def object_path(directory):
    """Pointer to the file name of the module's object file in a directory."""
    kernel.path_begin()
    kernel.path_add_text(directory)
    kernel.path_add(C_SLASH)
    kernel.path_add_name(kernel.module_name[0])
    for i in range(0, len(OBJECT_ENDING)):
        kernel.path_add(OBJECT_ENDING[i])
    return kernel.path_end()


def init():
    """Start every component, each after the ones it relies on."""
    err.init()
    kernel.init()
    typetab.init()
    src.init()
    lex.init()
    out.init()
    gen.init()
    decl.init()


def main():
    init()
    if env.argc() < 2:
        err.fatal(err.E_USAGE)
    source = kernel.keep_argument(0)
    err.set_file(source)
    output = kernel.keep_argument(1)
    decl.directory_add(output)
    for i in range(2, env.argc()):
        decl.directory_add(kernel.keep_argument(i))
    kernel.module_add(module_name(source))
    if not src.open_file(source):
        err.fatal(err.E_OPEN_SOURCE)
    if not out.open(object_path(output)):
        err.fatal(err.E_CREATE)
    decl.unit()
    out.end_module()
    err.position(0, 0)
    decl.write_interface(output)
    env.exit(0)


if env.is_program(__name__):
    main()
