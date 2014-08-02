from __future__ import print_function
from ctypes import c_uint32, c_float, c_char, BigEndianStructure
import io

class FTX(BigEndianStructure):
    _fields_ = [('method',  c_uint32),
                ('retcode', c_uint32)]

class SteeringBlock(BigEndianStructure):
    _fields_ = [('stamp',                c_uint32*4),
                ('emergency_stop_block', c_uint32, 1),
                ('end_of_run',           c_uint32, 1),
                ('start_of_run',         c_uint32, 1),
                ('padding',              c_uint32, 5),
                ('size',                 c_uint32, 24),
                ('count',                c_uint32),
                ('skip',                 c_uint32),
                ('fast_blocks',          c_uint32)]

class Control(BigEndianStructure):
    _fields_ = [('size', c_uint32),
                ('type', c_uint32)]

class Pilot(BigEndianStructure):
    _fields_ = [('check',       c_float),
                ('version',     c_uint32),
                ('process',     c_uint32),
                ('reserve',     c_uint32),
                ('size_text',   c_uint32),
                ('size_seg',    c_uint32),
                ('size_rel',    c_uint32),
                ('size_bank',   c_uint32),
                ('entry_link',  c_uint32),
                ('size_header', c_uint32)]

class Bank(BigEndianStructure):
    _fields_ = [('next',   c_uint32),
                ('up',     c_uint32),
                ('origin', c_uint32),
                ('id',     c_uint32),
                ('name',   c_char*4),
                ('links',  c_uint32),
                ('slinks', c_uint32),
                ('data',   c_uint32),
                ('status', c_uint32)]

class IOControl(BigEndianStructure):
    _fields_ = [('char', c_uint32, 16),
                ('size', c_uint32, 16)]

def _iter_prec(f):
    """
    Yields physical record blocks from a Zebra file `f`.

    If you get lost or the current block is corrupted,
    you can tell the generator to skip to the next physical
    record and ignore the bytes left over from the last by
    sending True, i.e.:
    
        prec_iter = _iter_prec(f)
        block = next(prec_iter)
        block = next(prec_iter)
        # get lost
        block = prec_iter.send(True)
        # back on track
    """
    skip = False
    while f.read(1):
        f.seek(-1,1)

        sb = SteeringBlock.from_buffer_copy(f.read(32))

        # size of steering block
        # see calculation on page 121 of ZEBRA guide
        size = (sb.size*(sb.fast_blocks + 1)-8)*4
        physical_record = f.read(size)
        assert len(physical_record) == size

        skip_to = sb.skip - 8

        if skip:
            skip = yield physical_record[skip_to*4:]
        else:
            skip = yield physical_record

def _iter_lrec(f):
    """Yields logical record blocks as bytearrays from a Zebra file `f`."""
    prec_iter = _iter_prec(f)

    buf = bytearray()
    while True:
        if len(buf) >= 4 and buf[:4] == b'\x00'*4:
            # one word padding block
            buf = buf[4:]
            continue

        if len(buf) < 8:
            # extend buffer with next physical record
            try:
                chunk = next(prec_iter)
            except StopIteration:
                break

            buf.extend(chunk)

        cw = Control.from_buffer(buf[:8])

        while len(buf) < cw.size*4 + 8:
            # extend buffer with next physical record
            try:
                chunk = next(prec_iter)
            except StopIteration:
                break

            buf.extend(chunk)

        if cw.type in (2,3,4):
            # normal record
            pass
        elif cw.type in (5,6):
            # padding record
            if cw.size >= 1:
                buf = buf[8+(cw.size-1)*4:]
            else:
                raise IOError('padding record with %i bytes' % cw.size)
            continue
        elif cw.type == 1:
            # start-of-run record
            buf = buf[8+cw.size*4:]
            continue
        else:
            raise ValueError('Unknown record type %i' % cw.type)

        pilot = Pilot.from_buffer(buf[8:48])

        size = (cw.size-10)*4
        rec = buf[48:48+size]
        assert size == len(rec)

        skip_to = pilot.size_header + pilot.size_seg + pilot.size_rel + pilot.size_text
        rec = rec[skip_to*4:]

        yield rec
        buf = buf[48+size:]

def _iter_banks(rec):
    """Yields (bank, data) from a logical record."""
    bytes = io.BytesIO(rec)
    while bytes.tell() < len(rec):
        ioc = IOControl.from_buffer_copy(bytes.read(4))

        bytes.seek((ioc.size-12)*4,1)
        bank = Bank.from_buffer_copy(bytes.read(36))

        data = bytes.read(bank.data*4)
        assert len(data) == bank.data*4
        yield bank, data

if __name__ == '__main__':
    import sys
    import argparse
    import re

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', help='increase verbosity', action='store_true')
    parser.add_argument('filename')
    args = parser.parse_args()

    with io.open(args.filename,'rb') as f:
        for rec in _iter_lrec(f):
            for bank, data in _iter_banks(rec):
                #if re.match('FT[A-Z]\s',bank.name):
                #    ftx = FTX.from_buffer_copy(data)
                #    print('ftx.retcode = ', ftx.retcode)
                #    print('ftx.method  = ', ftx.method)
                #    print(bank.name)
                print(bank.name)
                if 'PMT' in bank.name:
                    print(bank.name)
