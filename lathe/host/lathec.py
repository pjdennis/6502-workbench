"""The Lathe compiler's main program.

    lathec [-c6502|-c65c02] [-dNAME[=NUMBER]]... SOURCE.lth OUTDIR [IMPORTDIR...]

Compiles one module in one pass: SRC and LEX turn the file into tokens; DECL, STMT and EXPR
parse them; GEN chooses instructions, which FBUF holds until each function ends; OUT writes
the object file OUTDIR/name.lo, and DECL the interface OUTDIR/name.li. Owns the command line
and the order in which the components start. The options set the CPU the module is for and
predeclare constants for `#if` (README.md, "Command lines").
"""
import decl
import env
import err
import expr
import gen
import kernel
import lex
import out
import src
import typetab

C_0 = 0x30
C_SLASH = 0x2F
C_EQUALS = 0x3D
C_UNDERSCORE = 0x5F
C_MINUS = 0x2D
C_C = 0x63
C_D = 0x64
SOURCE_ENDING = b".lth"
OBJECT_ENDING = b".lo"
CPU_6502 = b"6502"
CPU_65C02 = b"65c02"
CPU_NAME = b"cpu_65c02"         # the bool constant the CPU option sets


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


def is_text(place, text):
    """True if the zero-terminated text at `place` is `text`, in either case."""
    for i in range(0, len(text)):
        if lex.fold(env.mem[place + i]) != text[i]:
            return False
    return env.mem[place + len(text)] == 0


def cpu_option(place):
    """The CPU named by the text after `-c`: 0 for 6502, 1 for 65C02."""
    if is_text(place, CPU_6502):
        return 0
    if not is_text(place, CPU_65C02):
        err.fatal(err.E_USAGE)
    return 1


def constant(name, t, value):
    """Predeclare the constant `name`: it can be used everywhere, `#if` included."""
    s = kernel.sym_add(kernel.SCOPE_PREDECLARED, name, kernel.K_CONST)
    kernel.sym_type[s] = t
    kernel.sym_value[s] = value


def decimal(place):
    """The number written in decimal at `place`, to the end of the text."""
    n = 0
    if env.mem[place] == 0:
        err.fatal(err.E_USAGE)
    while env.mem[place] != 0:
        digit = env.mem[place] - C_0
        if not lex.is_digit(env.mem[place]) or n > (0xFFFF - digit) // 10:
            err.fatal(err.E_USAGE)
        n = n * 10 + digit
        place += 1
    return n


def define(place):
    """The text after `-d`: NAME, which predeclares the bool constant NAME as true, or
    NAME=NUMBER, which predeclares it as that number, of no type yet."""
    kernel.name_begin()
    if not lex.is_letter(env.mem[place]):
        err.fatal(err.E_USAGE)
    while env.mem[place] != 0 and env.mem[place] != C_EQUALS:
        ch = env.mem[place]
        if not lex.is_letter(ch) and not lex.is_digit(ch) and ch != C_UNDERSCORE:
            err.fatal(err.E_USAGE)
        kernel.name_add(lex.fold(ch))
        place += 1
    name = kernel.name_end()
    if kernel.name_token(name) != 0:
        err.fatal(err.E_USAGE)              # a keyword
    if env.mem[place] == 0:
        constant(name, typetab.BOOL_TYPE, 1)
    else:
        constant(name, typetab.NUMBER_TYPE, decimal(place + 1))


def option(place):
    """One option, the text at `place`: -c6502, -c65c02, -dNAME or -dNAME=NUMBER."""
    if env.mem[place + 1] == C_C:
        gen.cpu = cpu_option(place + 2)
    elif env.mem[place + 1] == C_D:
        define(place + 2)
    else:
        err.fatal(err.E_USAGE)


def init():
    """Start every component, each after the ones it relies on."""
    err.init()
    kernel.init()
    typetab.init()
    src.init()
    lex.init()
    out.init()
    gen.init()
    expr.init()
    decl.init()


def main():
    init()
    n = 0
    while True:
        if n == env.argc():
            err.fatal(err.E_USAGE)
        source = kernel.keep_argument(n)
        n += 1
        if env.mem[source] != C_MINUS:
            break
        option(source)
    kernel.name_begin()
    for i in range(0, len(CPU_NAME)):
        kernel.name_add(CPU_NAME[i])
    constant(kernel.name_end(), typetab.BOOL_TYPE, gen.cpu)
    if n == env.argc():
        err.fatal(err.E_USAGE)
    err.set_file(source)
    output = kernel.keep_argument(n)
    decl.directory_add(output)
    for i in range(n + 1, env.argc()):
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
