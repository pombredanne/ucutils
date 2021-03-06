#!/usr/bin/env python
import ast
import cmd
import operator

import unicorn
import capstone

import ucutils


# simple evaluator for mathematics
# via: https://stackoverflow.com/a/9558001/87207
OPS = {ast.Add: operator.add,
       ast.Sub: operator.sub,
       ast.Mult: operator.mul,
       ast.Div: operator.truediv,
       ast.Pow: operator.pow,
       ast.BitXor: operator.xor,
       ast.USub: operator.neg}


def _eval_expr(node):
    if isinstance(node, ast.Num):  # <number>
        return node.n
    elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
        return OPS[type(node.op)](_eval_expr(node.left), _eval_expr(node.right))
    elif isinstance(node, ast.UnaryOp):  # <operator> <operand> e.g., -1
        return OPS[type(node.op)](_eval_expr(node.operand))
    else:
        raise TypeError(node)


def eval_expr(expr):
    '''
    evaluate a mathematical expression string.
    should be safe from injection.

    example::

        >>> eval_expr('2^6')
        4
        >>> eval_expr('2**6')
        64
        >>> eval_expr('1 + 2*3**(4^5) / (6 + -7)')
        -5.0

    Args:
      expr (str): the expression to evaulate

    Returns:
      number
    '''
    return _eval_expr(ast.parse(expr, mode='eval').body)


class UnicornCli(cmd.Cmd):
    # here are the general purpose registers a user is probably interested in.
    # order here is important, since we use the contents to replace values before evaluation.
    GPREGS = [
        'RAX', 'RBP', 'RBX', 'RCX', 'RDI', 'RDX', 'RIP', 'RSI', 'RSP',
        'EAX', 'EBP', 'EBX', 'ECX', 'EDI', 'EDX', 'EIP', 'ESI', 'ESP',
        'AH', 'AL', 'AX', 'BH', 'BL', 'BPL', 'BP', 'BX', 'CH', 'CL',
        'CS', 'CX', 'DH', 'DIL', 'DI', 'DL', 'DS', 'DX',
        'R8B', 'R9B', 'R10B', 'R11B', 'R12B', 'R13B', 'R14B', 'R15B',
        'R8D', 'R9D', 'R10D', 'R11D', 'R12D', 'R13D', 'R14D', 'R15D',
        'R8W', 'R9W', 'R10W', 'R11W', 'R12W', 'R13W', 'R14W', 'R15W',
        'R8',  'R9',  'R10',  'R11',  'R12',  'R13',  'R14',  'R15',
    ]

    X64GPREGS = [
        'RAX', 'RBP', 'RBX', 'RCX', 'RDI', 'RDX', 'RIP', 'RSI', 'RSP',
        'R8',  'R9',  'R10',  'R11',  'R12',  'R13',  'R14',  'R15',
    ]

    def __init__(self, emu):
        super().__init__()
        self.emu = emu

    @property
    def prompt(self):
        return '0x%08x> ' % (self.emu.pc)

    def do_exit(self, line):
        return True

    def do_quit(self, line):
        return True

    def do_EOF(self, line):
        return True

    def do_reg(self, line):
        for reg in self.X64GPREGS:
            print('%s: 0x%08x' % (reg, getattr(self.emu, reg.lower())))

    def parse_addr(self, line):
        if not line:
            return self.emu.rip
        elif line in self.emu.arch.REGS:
            return getattr(self.emu, line)
        elif '+' in line or '-' in line or '*' in line:
            for reg in self.GPREGS:
                line = line.replace(reg, hex(getattr(self.emu, reg.lower())))
                line = line.replace(reg.lower(), hex(getattr(self.emu, reg.lower())))
            return eval_expr(line)
        else:
            return int(line, 0x10)

    def do_dc(self, line):
        addr = self.parse_addr(line)
        try:
            print(ucutils.mem_hexdump(self.emu, addr, 0x100))
        except unicorn.UcError:
            print('invalid memory')

    def do_dq(self, line):
        addr = self.parse_addr(line)
        for i in range(0x10):
            try:
                q = ucutils.parse_uint64(self.emu, addr + (i * 8))
            except unicorn.UcError:
                print('invalid memory')
                break
            print('0x%08x: 0x%x' % (addr + (i * 8), q))

    def do_u(self, line):
        if ' ' in line:
            addr_line, _, count_line = line.partition(' ')
            addr = self.parse_addr(addr_line)
            count = int(line, 0x10)
        else:
            addr = self.parse_addr(line)
            count = 1

        dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        try:
            for op in dis.disasm(self.emu.mem_read(addr, 0x10 * count), addr):
                print("0x%x:\t%s\t%s" % (op.address, op.mnemonic, op.op_str))
        except unicorn.UcError:
            print('invalid memory')

    def do_t(self, line):
        self.emu.stepi()

    def do_g(self, line):
        addr = self.parse_addr(line)
        try:
            self.emu.go(addr)
        except unicorn.UcError as e:
            print('error: %s' % (e))

    def do_sym(self, line):
        addr = self.parse_addr(line)
        print('0x%08x: %s' % (addr, self.emu.symbols.get(addr, '????')))
