#!/usr/bin/env python3
"""A stand-in linker for build.py (build.LINKER) that measures what a program needs of main RAM
when it does not fit yet: it runs the host linker (lathe/host/link.py) in this process with the
same arguments, but a bank that is over as the linker judges it is not an error (link error 45
is noted and the link goes on), so that the map shows every fixed function, stub and variable
where it would be. test_bbc_rom128.py's ADFS account uses it, with the code and data ranges made
large enough (adfs_measure_env): the code from PAGE, the variables in a range of their own.

    LK_MAINRAM_OUT=FILE python3 lathe/tests/lk_mainram.py ENV MAIN IMAGE MAP OBJECTS...

FILE gets a line `bank over N` for each bank that was over (its index from 0).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'host'))

import env  # noqa: E402
import lk_err  # noqa: E402


def main(args):
    env.start(args)
    muted = [False]
    notes = []
    real = {name: getattr(lk_err, name) for name in ('begin', 'put', 'put_number', 'put_word', 'over',
                                                      'colon', 'comma', 'arrow', 'finish')}

    def begin(n):
        if n == lk_err.E_BANK_FULL:
            muted[0] = True
            return
        real['begin'](n)

    def over(amount, wrapped):
        if muted[0]:
            notes.append(amount)
            return
        real['over'](amount, wrapped)

    def finish():
        if muted[0]:
            muted[0] = False
            return
        real['finish']()

    def quiet(name):
        def f(*a):
            if not muted[0]:
                real[name](*a)
        return f

    lk_err.begin, lk_err.over, lk_err.finish = begin, over, finish
    for name in ('put', 'put_number', 'put_word', 'colon', 'comma', 'arrow'):
        setattr(lk_err, name, quiet(name))
    import link
    status = 0
    try:
        link.main()
    except SystemExit as e:
        status = e.code or 0
    with open(os.environ['LK_MAINRAM_OUT'], 'a') as fh:
        for n in notes:
            fh.write(f'bank over {n}\n')
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
