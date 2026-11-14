"""STMT: statements and control flow.

Owns the parsing of a function's body. So far a statement is a call or `return`; each of the
other statements of docs/language.md gets a function here, chosen in statement() by its
first token.
"""
import err
import expr
import gen
import lex


def is_assignment(token):
    """True for the tokens that make a statement starting with a name an assignment."""
    return token == lex.T_COMMA or (token >= lex.T_ASSIGN and token <= lex.T_SHR_ASSIGN)


def starts_later_statement(token):
    """True for the first token of a statement, or of a local declaration, not done yet."""
    if token == lex.T_IF or token == lex.T_WHILE or token == lex.T_LOOP or token == lex.T_FOR:
        return True
    if token == lex.T_CASE or token == lex.T_CRITICAL or token == lex.T_ASM:
        return True
    if token == lex.T_BREAK or token == lex.T_CONTINUE:
        return True
    return token == lex.T_VAR or token == lex.T_STATIC


def name_statement():
    """designator ( assignOp expression | "," designator "=" call | arguments ): the token
    after the designator says which."""
    expr.designator()
    if gen.op_kind[gen.depth - 1] == gen.O_FUNC:
        if lex.tok != lex.T_LPAREN:
            err.fatal(err.E_LPAREN_EXPECTED)
        expr.call()
    elif lex.tok == lex.T_LPAREN:
        err.fatal(err.E_NOT_FUNC)
    elif is_assignment(lex.tok):
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_SYNTAX)


def return_statement():
    """"return" [ expression [ "," expression ] ]. Functions have no results yet."""
    lex.next()
    if lex.tok != lex.T_NL:
        err.fatal(err.E_UNSUPPORTED)
    gen.ret()


def statement():
    if lex.tok == lex.T_NAME:
        name_statement()
    elif lex.tok == lex.T_RETURN:
        return_statement()
    elif starts_later_statement(lex.tok):
        err.fatal(err.E_UNSUPPORTED)
    else:
        err.fatal(err.E_STMT_EXPECTED)
    lex.expect(lex.T_NL, err.E_NL_EXPECTED)


def body():
    """body = { varDecl | statement }. Stops at the token that ends the body, which is for
    the caller to check."""
    while lex.tok != lex.T_END and lex.tok != lex.T_EOF:
        statement()
