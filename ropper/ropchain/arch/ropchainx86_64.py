# coding=utf-8
# Copyright 2018 Sascha Schirra
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" A ND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from ropper.gadget import Category, Gadget
from ropper.common.error import *
from ropper.common.utils import *
from ropper.rop import Ropper
from ropper.arch import x86_64
from ropper.ropchain.ropchain import *
from ropper.loaders.loader import Type
from ropper.loaders.elf import ELF
from ropper.loaders.pe import PE
from ropper.loaders.raw import Raw
from ropper.loaders.mach_o import MachO
from re import match
import itertools
import math
import sys

if sys.version_info.major == 2:
    range = xrange

class RopChainX86_64(RopChain):

    MAX_QUALI = 7

    def _printHeader(self):
        toReturn = ''
        toReturn += ('#!/usr/bin/env python\n')
        toReturn += ('# Generated by ropper ropchain generator #\n')
        toReturn += ('from struct import pack\n')
        toReturn += ('\n')
        toReturn += ('p = lambda x : pack(\'Q\', x)\n')

        toReturn += ('\n')

        return toReturn

    def _printRebase(self):
        toReturn = ''

        for binary,section in self._usedBinaries:
            imageBase = Gadget.IMAGE_BASES[binary]
            toReturn += ('IMAGE_BASE_%d = %s # %s\n' % (self._usedBinaries.index((binary, section)),toHex(imageBase ,8), binary))
            toReturn += ('rebase_%d = lambda x : p(x + IMAGE_BASE_%d)\n\n'% (self._usedBinaries.index((binary, section)),self._usedBinaries.index((binary, section))))
        return toReturn

    @classmethod
    def name(cls):
        return ''

    @classmethod
    def availableGenerators(cls):
        return [RopChainSystemX86_64, RopChainMprotectX86_64]

    @classmethod
    def archs(self):
        return [x86_64]

    def _createDependenceChain(self, gadgets):
        """
        gadgets - list with tuples

        tuple contains:
        - method to create chaingadget
        - list with arguments
        - dict with named arguments
        - list with registers which are not allowed to override in the gadget
        """
        failed = []
        cur_len = 0
        cur_chain = ''
        counter = 0

        max_perm = math.factorial(len(gadgets))
        for x in itertools.permutations(gadgets):
            counter += 1
            self._printMessage('[*] Try permuation %d / %d' % (counter, max_perm))
            found = False
            for y in failed:

                if x[:len(y)] == y:
                    found = True
                    break
            if found:
                continue
            try:
                fail = []
                chain2 = ''
                dontModify = []
                badRegs = []
                c = 0
                for idx in range(len(x)):
                    g = x[idx]
                    if idx != 0:
                        badRegs.extend(x[idx-1][3])

                    dontModify.extend(g[3])
                    fail.append(g)
                    chain2 += g[0](*g[1], badRegs=badRegs, dontModify=dontModify,**g[2])[0]


                cur_chain += chain2
                break

            except RopChainError as e:
                pass
            if len(fail) > cur_len:
                cur_len = len(fail)
                cur_chain = '# Filled registers: '
                for fa in fail[:-1]:

                    cur_chain += (fa[2]['reg']) + ', '
                cur_chain += '\n'
                cur_chain += chain2

            failed.append(tuple(fail))
        else:
            self._printMessage('')
            self._printMessage('Cannot create chain which fills all registers')
        self._printMessage('')
        return cur_chain

    def _isModifiedOrDereferencedAccess(self, gadget, dontModify):

        regs = []
        for line in gadget.lines[1:]:
            line = line[1]
            if '[' in line:
                return True
            if dontModify:
                m = match('[a-z]+ (e?[abcds][ixlh]),?.*', line)
                if m and m.group(1) in dontModify:
                    return True

        return False



    def _paddingNeededFor(self, gadget):
        regs = []
        for idx in range(1,len(gadget.lines)):
            line = gadget.lines[idx][1]
            matched = match('^pop (...)$', line)
            if matched:
                regs.append(matched.group(1))
        return regs


    def _printRopInstruction(self, gadget, padding=True, value=None):
        toReturn = ('rop += rebase_%d(%s) # %s\n' % (self._usedBinaries.index((gadget.fileName, gadget.section)),toHex(gadget.lines[0][0],8), gadget.simpleString()))

        value_first = False

        if padding:
            regs = self._paddingNeededFor(gadget)

            if len(regs) > 0:
                dst = gadget.category[2]['dst']
                search = '^pop (%s)$' % dst
                first_line = gadget.lines[0][1]
                if match(search, first_line):
                    value_first = True

            padding_str = ''
            for i in range(len(regs)):
                padding_str +=self._printPaddingInstruction()

            if value_first:
                toReturn += value
                toReturn += padding_str
            else:
                toReturn += padding_str
                if value:
                    toReturn += value

        return toReturn

    def _printAddString(self, string):
        return ('rop += \'%s\'\n' % string)

    def _printRebasedAddress(self, addr, comment='', idx=0):
        return ('rop += rebase_%d(%s)\n' % (idx,addr))

    def _printPaddingInstruction(self, addr='0xdeadbeefdeadbeef'):
        return ('rop += p(%s)\n' % addr)

    def _containsZeroByte(self, addr):
        return self.containsBadbytes(addr,8)

    def _createZeroByteFillerForSub(self, number):
        start = 0x0101010101010101
        for i in range(start, 0x0202020202020202):
            if not self._containsZeroByte(i) and not self._containsZeroByte(i+number):
                return i

    def _createZeroByteFillerForAdd(self, number):
        start = 0x0101010101010101
        for i in range(start, 0x0202020202020202):
            if not self._containsZeroByte(i) and not self._containsZeroByte(number-i):
                return i

    def _find(self, category, reg=None, srcdst='dst', badDst=[], badSrc=None, dontModify=None, srcEqDst=False, switchRegs=False ):
        quali = 1

        if reg and reg[0] != 'r':
            return
        while quali < RopChainSystemX86_64.MAX_QUALI:
            for binary in self._binaries:
                for gadget in self._gadgets[binary]:

                    if gadget.category[0] == category and gadget.category[1] == quali:

                        if badSrc and (gadget.category[2]['src'] in badSrc \
                                       or gadget.affected_regs.intersection(badSrc)):
                            continue
                        if badDst and (gadget.category[2]['dst'] in badDst \
                                       or gadget.affected_regs.intersection(badDst)):
                            continue
                        if not gadget.lines[len(gadget.lines)-1][1].strip().endswith('ret') or 'esp' in gadget.simpleString() or 'rsp' in gadget.simpleString():
                            continue
                        if srcEqDst and (not (gadget.category[2]['dst'] == gadget.category[2]['src'])):
                            continue
                        elif not srcEqDst and 'src' in gadget.category[2] and (gadget.category[2]['dst'] == gadget.category[2]['src']):
                            continue
                        if self._isModifiedOrDereferencedAccess(gadget, dontModify):
                            continue
                        if reg:
                            if gadget.category[2][srcdst] == reg:
                                self._updateUsedBinaries(gadget)
                                return gadget
                            elif switchRegs:
                                other = 'src' if srcdst == 'dst' else 'dst'
                                if gadget.category[2][other] == reg:
                                    self._updateUsedBinaries(gadget)
                                    return gadget
                        else:
                            self._updateUsedBinaries(gadget)
                            return gadget

            quali += 1


    def _createWriteStringWhere(self, what, where, reg=None, dontModify=[], idx=0):
        badRegs = []
        badDst = []
        while True:
            popReg = self._find(Category.LOAD_REG, reg=reg, badDst=badRegs, dontModify=dontModify)
            if not popReg:
                raise RopChainError('Cannot build writewhatwhere gadget!')
            write4 = self._find(Category.WRITE_MEM, reg=popReg.category[2]['dst'],  badDst=
            badDst, srcdst='src')
            if not write4:
                badRegs.append(popReg.category[2]['dst'])
                continue
            else:
                popReg2 = self._find(Category.LOAD_REG, reg=write4.category[2]['dst'], dontModify=[popReg.category[2]['dst']]+dontModify)
                if not popReg2:
                    badDst.append(write4.category[2]['dst'])
                    continue
                else:
                    break;

        if len(what) % 8 > 0:
            what += ' ' * (8 - len(what) % 8)
        toReturn = ''
        for index in range(0,len(what),8):
            part = what[index:index+8]

            toReturn += self._printRopInstruction(popReg,False)
            toReturn += self._printAddString(part)
            regs = self._paddingNeededFor(popReg)
            for i in range(len(regs)):
                toReturn +=self._printPaddingInstruction()
            toReturn += self._printRopInstruction(popReg2, False)

            toReturn += self._printRebasedAddress(toHex(where+index,8), idx=idx)
            regs = self._paddingNeededFor(popReg2)
            for i in range(len(regs)):
                toReturn +=self._printPaddingInstruction()
            toReturn += self._printRopInstruction(write4)
        return (toReturn,popReg.category[2]['dst'], popReg2.category[2]['dst'])


    def _createWriteRegValueWhere(self, what, where, dontModify=[], idx=0):
        badRegs = []
        badDst = []
        while True:


            write4 = self._find(Category.WRITE_MEM, reg=what,  badDst=badDst, dontModify=dontModify, srcdst='src')
            if not write4:
                raise RopChainError('Cannot build writeregvaluewhere gadget!')
            else:
                popReg2 = self._find(Category.LOAD_REG, reg=write4.category[2]['dst'], dontModify=[what]+dontModify)
                if not popReg2:
                    badDst.append(write4.category[2]['dst'])
                    continue
                else:
                    break;

        toReturn = self._printRopInstruction(popReg2, False)
        toReturn += self._printRebasedAddress(toHex(where,8), idx=idx)
        regs = self._paddingNeededFor(popReg2)
        for i in range(len(regs)):
            toReturn +=self._printPaddingInstruction()
        toReturn += self._printRopInstruction(write4)

        return (toReturn,what, popReg2.category[2]['dst'])

    def _createLoadRegValueFrom(self, what, from_reg, dontModify=[], idx=0):
        try:
            return self._createLoadRegValueFromMov(what, from_reg, dontModify, idx)
        except RopChainError:
            return self._createLoadRegValueFromXchg(what, from_reg, dontModify, idx)

    def _createLoadRegValueFromMov(self, what, from_reg, dontModify=[], idx=0):
        badRegs = []
        badDst = []
        while True:


            load4 = self._find(Category.LOAD_MEM, reg=what,  badDst=badDst, dontModify=dontModify, srcdst='dst')
            if not load4:
                raise RopChainError('Cannot build loadwhere gadget!')
            else:
                popReg2 = self._find(Category.LOAD_REG, reg=load4.category[2]['src'], dontModify=[what,load4.category[2]['src']]+dontModify)
                if not popReg2:
                    badDst.append(load4.category[2]['src'])
                    continue
                else:
                    break;

        toReturn = self._printRopInstruction(popReg2, False)
        toReturn += self._printRebasedAddress(toHex(from_re,8), idx=idx)
        regs = self._paddingNeededFor(popReg2)
        for i in range(len(regs)):
            toReturn +=self._printPaddingInstruction()
        toReturn += self._printRopInstruction(load4)

        return (toReturn,what, popReg2.category[2]['dst'])

    def _createLoadRegValueFromXchg(self, what, from_reg, dontModify=[], idx=0):
        badRegs = []
        badDst = []
        while True:


            load4 = self._find(Category.XCHG_REG, reg=what,  badDst=badDst, dontModify=dontModify, srcdst='src')
            if not load4:
                raise RopChainError('Cannot build loadwhere gadget!')
            else:
                mov = self._find(Category.LOAD_MEM, reg=load4.category[2]['dst'],  badDst=badDst, dontModify=[load4.category[2]['dst']]+dontModify, srcdst='dst')
                if not mov:
                    badDst.append(load4.category[2]['dst'])
                    continue

                popReg2 = self._find(Category.LOAD_REG, reg=mov.category[2]['src'], dontModify=[what,load4.category[2]['src']]+dontModify)
                if not popReg2:
                    badDst.append(load4.category[2]['src'])
                    continue
                else:
                    break;



        toReturn = self._printRopInstruction(popReg2, False)
        toReturn += self._printRebasedAddress(toHex(from_reg,8), idx=idx)
        regs = self._paddingNeededFor(popReg2)
        for i in range(len(regs)):
            toReturn +=self._printPaddingInstruction()

        toReturn += self._printRopInstruction(mov)

        toReturn += self._printRopInstruction(load4)

        return (toReturn,what, popReg2.category[2]['dst'])

    def _createNumberSubtract(self, number, reg=None, badRegs=None, dontModify=None):
        if not badRegs:
            badRegs=[]
        while True:
            sub = self._find(Category.SUB_REG, reg=reg, badDst=badRegs, badSrc=badRegs, dontModify=dontModify)
            if not sub:
                raise RopChainError('Cannot build number with subtract gadget for reg %s!' % reg)
            popSrc = self._find(Category.LOAD_REG, reg=sub.category[2]['src'], dontModify=dontModify)
            if not popSrc:
                badRegs.append=[sub.category[2]['src']]
                continue
            popDst = self._find(Category.LOAD_REG, reg=sub.category[2]['dst'], dontModify=[sub.category[2]['src']]+dontModify)
            if not popDst:
                badRegs.append=[sub.category[2]['dst']]
                continue
            else:
                break;

        filler = self._createZeroByteFillerForSub(number)

        toReturn = self._printRopInstruction(popSrc, False)
        toReturn += self._printPaddingInstruction(toHex(filler,8))
        regs = self._paddingNeededFor(popSrc)
        for i in range(len(regs)):
            toReturn += self._printPaddingInstruction()
        toReturn += self._printRopInstruction(popDst, False)
        toReturn += self._printPaddingInstruction(toHex(filler+number,8))
        regs = self._paddingNeededFor(popDst)
        for i in range(len(regs)):
            toReturn += self._printPaddingInstruction()
        toReturn += self._printRopInstruction(sub)
        return (toReturn, popDst.category[2]['dst'],popSrc.category[2]['dst'])

    def _createNumberAddition(self, number, reg=None, badRegs=None, dontModify=None):
        if not badRegs:
            badRegs=[]
        while True:
            sub = self._find(Category.ADD_REG, reg=reg, badDst=badRegs, badSrc=badRegs, dontModify=dontModify)
            if not sub:
                raise RopChainError('Cannot build number with addition gadget for reg %s!' % reg)
            popSrc = self._find(Category.LOAD_REG, reg=sub.category[2]['src'], dontModify=dontModify)
            if not popSrc:
                badRegs.append=[sub.category[2]['src']]
                continue
            popDst = self._find(Category.LOAD_REG, reg=sub.category[2]['dst'], dontModify=[sub.category[2]['src']]+dontModify)
            if not popDst:
                badRegs.append(sub.category[2]['dst'])
                continue
            else:
                break;

        filler = self._createZeroByteFillerForAdd(number)

        toReturn = self._printRopInstruction(popSrc, False)
        toReturn += self._printPaddingInstruction(toHex(filler,8))
        regs = self._paddingNeededFor(popSrc)
        for i in range(len(regs)):
            toReturn += self._printPaddingInstruction()
        toReturn += self._printRopInstruction(popDst, False)
        toReturn += self._printPaddingInstruction(toHex(number - filler,8))
        regs = self._paddingNeededFor(popDst)
        for i in range(len(regs)):
            toReturn += self._printPaddingInstruction()
        toReturn += self._printRopInstruction(sub)

        return (toReturn, popDst.category[2]['dst'],popSrc.category[2]['dst'])

    def _createNumberPop(self, number, reg=None, badRegs=None, dontModify=None):
        if self._containsZeroByte(0xffffffff):
            raise RopChainError("Cannot write value with pop -1 and inc gadgets, because there are badbytes in the negated number")
        while True:
            popReg = self._find(Category.LOAD_REG, reg=reg, badDst=badRegs,dontModify=dontModify)
            if not popReg:
                raise RopChainError('Cannot build number with xor gadget!')
            incReg = self._find(Category.INC_REG, reg=popReg.category[2]['dst'], dontModify=dontModify)
            if not incReg:
                if not badRegs:
                    badRegs = []
                badRegs.append(popReg.category[2]['dst'])
            else:
                break

        value = self._printPaddingInstruction(toHex(0xffffffff,8))
        toReturn = self._printRopInstruction(popReg, value=value)
        for i in range(number+1):
            toReturn += self._printRopInstruction(incReg)

        return (toReturn ,popReg.category[2]['dst'],)


    def _createNumberXOR(self, number, reg=None, badRegs=None, dontModify=None):
        while True:
            clearReg = self._find(Category.CLEAR_REG, reg=reg, badDst=badRegs, badSrc=badRegs,dontModify=dontModify, srcEqDst=True)
            if not clearReg:
                raise RopChainError('Cannot build number with xor gadget!')
            if number > 0:
                incReg = self._find(Category.INC_REG, reg=clearReg.category[2]['src'], dontModify=dontModify)
                if not incReg:
                    if not badRegs:
                        badRegs = []
                    badRegs.append(clearReg.category[2]['src'])
                else:
                    break
            else:
                break

        toReturn = self._printRopInstruction(clearReg)
        for i in range(number):
            toReturn += self._printRopInstruction(incReg)

        return (toReturn, clearReg.category[2]['dst'],)

    def _createNumberXchg(self, number, reg=None, badRegs=None, dontModify=None):
        xchg = self._find(Category.XCHG_REG, reg=reg, badDst=badRegs, dontModify=dontModify)
        if not xchg:
            raise RopChainError('Cannot build number gadget with xchg!')

        other = xchg.category[2]['src'] if xchg.category[2]['dst'] else xchg.category[2]['dst']

        toReturn = self._createNumber(number, other, badRegs, dontModify)[0]

        toReturn += self._printRopInstruction(xchg)
        return (toReturn, reg, other)

    def _createNumberNeg(self, number, reg=None, badRegs=None, dontModify=None):
        if number == 0:
            raise RopChainError('Cannot build number gadget with neg if number is 0!')
        if self._containsZeroByte((~number)+1):
            raise RopChainError("Cannot use neg gadget, because there are badbytes in the negated number")
        neg = self._find(Category.NEG_REG, reg=reg, badDst=badRegs, dontModify=dontModify)
        if not neg:
            raise RopChainError('Cannot build number gadget with neg!')

        pop = self._find(Category.LOAD_REG, reg=reg, badDst=badRegs, dontModify=dontModify)
        if not pop:
            raise RopChainError('Cannot build number gadget with neg!')

        value = self._printPaddingInstruction(toHex((~number)+1, 8)) # two's complement
        toReturn = self._printRopInstruction(pop, value=value)
        toReturn += self._printRopInstruction(neg)
        return (toReturn, reg,)

    def _createNumber(self, number, reg=None, badRegs=None, dontModify=None, xchg=True):
        try:
            if self.containsBadbytes(number):
                try:
                    return self._createNumberNeg(number, reg, badRegs,dontModify)
                except RopChainError as e:

                    if number < 50:
                        try:
                            return self._createNumberXOR(number, reg, badRegs,dontModify)
                        except RopChainError:
                            try:
                                return self._createNumberPop(number, reg, badRegs,dontModify)
                            except RopChainError:
                                try:
                                    return self._createNumberSubtract(number, reg, badRegs,dontModify)
                                except RopChainError:
                                    return self._createNumberAddition(number, reg, badRegs,dontModify)

                    else :
                        try:
                            return self._createNumberSubtract(number, reg, badRegs,dontModify)
                        except RopChainError:
                            return self._createNumberAddition(number, reg, badRegs,dontModify)
            else:
                popReg =self._find(Category.LOAD_REG, reg=reg, badDst=badRegs,dontModify=dontModify)
                if not popReg:
                    raise RopChainError('Cannot build number gadget!')
                value = self._printPaddingInstruction(toHex(number,8))
                toReturn = self._printRopInstruction(popReg, value=value)
                return (toReturn , popReg.category[2]['dst'])
        except RopChainError:
            return self._createNumberXchg(number, reg, badRegs, dontModify)

    def _createAddress(self, address, reg=None, badRegs=None, dontModify=None):
        popReg = self._find(Category.LOAD_REG, reg=reg, badDst=badRegs,dontModify=dontModify)
        if not popReg:
            raise RopChainError('Cannot build address gadget!')

        toReturn = ''

        toReturn += self._printRopInstruction(popReg,False)
        toReturn += self._printRebasedAddress(toHex(address, 8), idx=self._usedBinaries.index((popReg.fileName, popReg.section)))
        regs = self._paddingNeededFor(popReg)
        for i in range(len(regs)):
            toReturn +=self._printPaddingInstruction()

        return (toReturn,popReg.category[2]['dst'])

    def _createSyscall(self, reg=None, badRegs=None, dontModify=None):
        syscall = self._find(Category.SYSCALL, reg=None, badDst=None, dontModify=dontModify)
        if not syscall:
            raise RopChainError('Cannot build syscall gadget!')

        toReturn = ''

        toReturn += self._printRopInstruction(syscall)

        return (toReturn,)

    def _createOpcode(self, opcode):
        gadget = self._searchOpcode(opcode)
        if gadget:
            return self._printRopInstruction(gadget)


    def _searchOpcode(self, opcode):
        r = Ropper()
        gadgets = []
        for section in self._binaries[0].executableSections:
            vaddr = section.virtualAddress
            gadgets.extend(r.searchOpcode(self._binaries[0],opcode=opcode,disass=True))

        if len(gadgets) > 0:
            return gadgets[0]
        else:
            raise RopChainError('Cannot create gadget for opcode: %s' % opcode)

    def create(self):
        pass


class RopChainSystemX86_64(RopChainX86_64):

    @classmethod
    def usableTypes(self):
        return (ELF, Raw)

    @classmethod
    def name(cls):
        return 'execve'

    def _createCommand(self, what, where, reg=None, dontModify=[], idx=0):
        if len(what) % 8 > 0:
            what = '/' * (8 - len(what) % 8) + what
        return self._createWriteStringWhere(what,where, idx=idx)

    def create(self, options):
        cmd = options.get('cmd')
        address = options.get('address')
        if not cmd:
            cmd = '/bin/sh'
        if len(cmd.split(' ')) > 1:
            raise RopChainError('No argument support for execve commands')

        self._printMessage('ROPchain Generator for syscall execve:\n')
        self._printMessage('\nwrite command into data section\nrax 0xb\nrdi address to cmd\nrsi address to null\nrdx address to null\n')
        chain = self._printHeader()
        gadgets = []
        can_create_command = False
        chain_tmp = '\n'
        if address is None:
            section = self._binaries[0].getSection('.data')

            length = math.ceil(float(len(cmd))/8) * 8
            nulladdress = section.offset+length
            try:
                cmdaddress = section.offset
                chain_tmp += self._createCommand(cmd,cmdaddress)[0]
                can_create_command = True

            except RopChainError as e:
                self._printMessage('Cannot create gadget: writewhatwhere')
                self._printMessage('Use 0x4141414141414141 as command address. Please replace that value.')
                cmdaddress = 0x4141414141414141
            if can_create_command:
                badregs = []
                tmpx = ''
                while True:

                    ret = self._createNumber(0x0, badRegs=badregs)
                    tmpx = ret[0]
                    try:
                        tmpx += self._createWriteRegValueWhere(ret[1], nulladdress)[0]
                        break
                    except BaseException as e:
                        #raise e
                        badregs.append(ret[1])

                chain_tmp += tmpx
                gadgets.append((self._createAddress, [cmdaddress],{'reg':'rdi'},['rdi','edi', 'di']))
                gadgets.append((self._createAddress, [nulladdress],{'reg':'rsi'},['rsi','esi', 'si']))
                gadgets.append((self._createAddress, [nulladdress],{'reg':'rdx'},['rdx','edx', 'dx', 'dl', 'dh']))
                gadgets.append((self._createNumber, [59],{'reg':'rax'},['rax','eax', 'ax', 'al', 'ah']))
        if address is not None and not can_create_command:
            if type(address) is str:
                cmdaddress = int(address, 16)
            nulladdress = options.get('nulladdress')
            if nulladdress is None:
                self._printMessage('No address to a null bytes was given, 0x4242424242424242 is used instead.')
                self._printMessage('Please replace that value.')
                nulladdress = 0x4242424242424242
            elif type(nulladdress) is str:
                nulladdress = int(nulladdress,16)

            gadgets.append((self._createNumber, [cmdaddress],{'reg':'rdi'},['rdi','edi', 'di']))
            gadgets.append((self._createNumber, [nulladdress],{'reg':'rsi'},['rsi','esi', 'si']))
            gadgets.append((self._createNumber, [nulladdress],{'reg':'rdx'},['rdx','edx', 'dx', 'dl', 'dh']))
            gadgets.append((self._createNumber, [59],{'reg':'rax'},['rax','eax', 'ax', 'al', 'ah']))

        self._printMessage('Try to create chain which fills registers without delete content of previous filled registers')
        chain_tmp += self._createDependenceChain(gadgets)

        try:
            self._printMessage('Look for syscall gadget')
            chain_tmp += self._createSyscall()[0]
            self._printMessage('syscall gadget found')

        except RopChainError:
            try:
                self._printMessage('No syscall gadget found!')
                self._printMessage('Look for syscall opcode')

                chain_tmp += self._createOpcode('0f05')
                self._printMessage('syscall opcode found')

            except RopChainError:
                chain_tmp += '# INSERT SYSCALL GADGET HERE\n'
                self._printMessage('syscall opcode not found')


        chain += self._printRebase()
        chain += 'rop = \'\'\n'

        chain += chain_tmp
        chain += 'print rop'
        return chain


class RopChainMprotectX86_64(RopChainX86_64):
    """
    Builds a ropchain for mprotect syscall
    rax 0x7b
    rdi address
    rsi size
    rdx 0x7 -> RWE
    """

    @classmethod
    def usableTypes(self):
        return (ELF, Raw)

    @classmethod
    def name(cls):
        return 'mprotect'

    def _createJmp(self, reg=['rsp']):
        r = Ropper()
        gadgets = []
        for section in self._binaries[0].executableSections:
            vaddr = section.virtualAddress
            gadgets.extend(r.searchJmpReg(self._binaries[0],reg))



        if len(gadgets) > 0:
            if (gadgets[0].fileName, gadgets[0].section) not in self._usedBinaries:
                self._usedBinaries.append((gadgets[0].fileName, gadgets[0].section))
            return self._printRopInstruction(gadgets[0])
        else:
            return None

    def __extract(self, param):
        if not match('0x[0-9a-fA-F]{1,16},0x[0-9a-fA-F]+', param) or not match('0x[0-9a-fA-F]{1,16},[0-9]+', param):
            raise RopChainError('Parameter have to have the following format: <hexnumber>,<hexnumber> or <hexnumber>,<number>')

        split = param.split(',')
        if isHex(split[1]):
            return (int(split[0], 16), int(split[1], 16))
        else:
            return (int(split[0], 16), int(split[1], 10))


    def create(self, options={}):
        address = options.get('address')
        size = options.get('size')
        if not address:
            raise RopChainError('Missing parameter: address')
        if not size:
            raise RopChainError('Missing parameter: size')

        if not match('0x[0-9a-fA-F]{1,8}', address):
            raise RopChainError('Parameter address have to have the following format: <hexnumber>')

        if not match('0x[0-9a-fA-F]+', size):
            raise RopChainError('Parameter size have to have the following format: <hexnumber>')

        address = int(address, 16)
        size = int(size, 16)

        self._printMessage('ROPchain Generator for syscall mprotect:\n')
        self._printMessage('rax 0xa\nrdi address\nrsi size\nrdx 0x7 -> RWE\n')

        chain = self._printHeader()

        chain += 'shellcode = \'\\xcc\'*100\n\n'

        gadgets = []
        gadgets.append((self._createNumber, [address],{'reg':'rdi'},['rdi','edi', 'di']))
        gadgets.append((self._createNumber, [size],{'reg':'rsi'},['rsi','esi', 'si']))
        gadgets.append((self._createNumber, [0x7],{'reg':'rdx'},['rdx','edx', 'dx', 'dl', 'dh']))
        gadgets.append((self._createNumber, [0xa],{'reg':'rax'},['rax','eax', 'ax', 'al', 'ah']))

        self._printMessage('Try to create chain which fills registers without delete content of previous filled registers')
        chain_tmp = ''
        chain_tmp += self._createDependenceChain(gadgets)
        try:
            self._printMessage('Look for syscall gadget')
            chain_tmp += self._createSyscall()[0]
            self._printMessage('syscall gadget found')
        except RopChainError:
            chain_tmp += '\n# ADD HERE SYSCALL GADGET\n\n'
            self._printMessage('No syscall gadget found!')

        self._printMessage('Look for jmp esp')
        jmp_esp = self._createJmp()
        if jmp_esp:
            self._printMessage('jmp esp found')
            chain_tmp += jmp_esp
        else:
            self._printMessage('no jmp esp found')
            chain_tmp += '\n# ADD HERE JMP ESP\n\n'

        chain += self._printRebase()
        chain += '\nrop = \'\'\n'
        chain += chain_tmp
        chain += 'rop += shellcode\n\n'
        chain += 'print(rop)\n'

        return chain
