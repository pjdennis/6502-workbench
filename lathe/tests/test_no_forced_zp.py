"""Compiled code must never force a variable into zero page by its choice of instruction.

lathe/docs/codegen.md, "Never forcing zero page": only a `zp` declaration or a pointer dereference
makes a variable "must be in zero page". STX v,Y and STY v,X have no absolute form, so emitting
them on an ordinary variable would take the choice away from the linker. The compiler may use
them only on a variable that is already class 0.

This reads the recorded snapshot output. Cases named asm_* are exempt: there the programmer wrote
the instruction (lathe/docs/language.md, "Inline assembly").
"""
import glob
import os
import re
import unittest

SNAP = os.path.join(os.path.dirname(__file__), 'cases', 'snap')
ZP_ONLY = re.compile(r'^\s*(STX\s+[^;]*,\s*Y|STY\s+[^;]*,\s*X)\b', re.IGNORECASE)
# lo2asm's comments: ';   slot 0 p: size 2, class 0 (zp), ...' and '; variable m.v: size 2, class 0 (zp), ...'
CLASS_0 = re.compile(r'^;\s+(?:slot \d+|variable) (\S+): size \d+, class 0\b')


def zp_only_uses(text):
    """Lines of assembler text that use an instruction with only a zero page form."""
    return [line.strip() for line in text.splitlines() if ZP_ONLY.match(line)]


def class_0_names(text):
    """Last name component of every slot and variable the text declares as class 0."""
    names = set()
    for line in text.splitlines():
        m = CLASS_0.match(line)
        if m:
            names.add(m.group(1).split('.')[-1])
    return names


def operand_name(line):
    """Last name component of an instruction's operand label: m__f__v+1,Y -> v."""
    return re.split(r'[\s,+]+', line.strip())[1].split('__')[-1]


class RuleTest(unittest.TestCase):
    def test_class_0_slots_and_variables_are_recognised(self):
        text = (';   slot 0 p: size 2, class 0 (zp), param, weight 3\n'
                ';   slot 1 n: size 1, class 1 (either), param, weight 3\n'
                '; variable m.cursor: size 2, class 0 (zp), weight 9\n')
        self.assertEqual(class_0_names(text), {'p', 'cursor'})
        self.assertEqual(operand_name('    STX m__f__p+1,Y'), 'p')

    def test_the_pattern_finds_the_two_forms_and_nothing_else(self):
        text = ('    STX m__f__v,Y\n    sty m__f__w , x\n    STX m__f__v\n'
                '    STA m__f__v,Y\n    STY m__f__v\n    LDX m__f__v,Y\n')
        self.assertEqual(zp_only_uses(text), ['STX m__f__v,Y', 'sty m__f__w , x'])


class SnapshotTest(unittest.TestCase):
    def test_compiled_code_uses_no_zero_page_only_instruction_on_an_ordinary_variable(self):
        found = []
        for path in sorted(glob.glob(os.path.join(SNAP, '*.expected.asm'))):
            name = os.path.basename(path)
            if name.startswith('asm_'):
                continue
            with open(path) as f:
                text = f.read()
            for line in zp_only_uses(text):
                if operand_name(line) not in class_0_names(text):
                    found.append(f'{name}: {line}')
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
