from __future__ import print_function
from ctypes import c_uint32, c_float, c_char, BigEndianStructure
import io
import logging

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

def zebraio(f):
    """Yields physical record blocks from a Zebra file `f`."""
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

def iter_logical_records(f):
    zebra = zebraio(f)

    buf = bytearray()
    while True:
        if len(buf) < 2:
            # extend buffer with next physical record
            try:
                chunk = next(zebra)
            except StopIteration:
                break

            buf.extend(chunk)

        if buf[:4] == '\x00'*4:
            # one word padding block
            logging.debug('one-word padding')
            buf = buf[4:]
            continue

        cw = Control.from_buffer(buf[:8])

        while len(buf) < cw.size*4 + 10:
            # extend buffer with next physical record
            logging.debug("EXTENDING")
            try:
                chunk = next(zebra)
            except StopIteration:
                break

            buf.extend(chunk)

        if cw.type in (2,3,4):
            # normal record
            pass
        elif cw.type in (5,):
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

        #logging.debug('pilot.size_header = %#x', pilot.size_header)
        #logging.debug('pilot.check = %#x', pilot.check)
        #logging.debug('pilot.version = %#x', pilot.version)
        #logging.debug('pilot.process = %#x', pilot.process)
        #logging.debug('pilot.reserve = %#x', pilot.reserve)
        #logging.debug('pilot.size_seg    = %#x', pilot.size_seg)
        #logging.debug('pilot.size_rel    = %#x', pilot.size_rel)
        #logging.debug('pilot.size_text   = %#x', pilot.size_text)
        #logging.debug('pilot.size_bank   = %#x', pilot.size_text)
        #logging.debug('control.size      = %#x', cw.size)

        size = (cw.size-10)*4
        record = buf[48:48+size]
        assert size == len(record)

        skip_to = pilot.size_header + pilot.size_seg + pilot.size_rel + pilot.size_text
        record = record[skip_to*4:]

        yield record
        buf = buf[48+size:]

@profile
def iter_banks(record):
    bytes = io.BytesIO(record)
    while bytes.tell() < len(record):
        #ioc = IOControl.from_buffer(record[:4])
        ioc = IOControl.from_buffer_copy(bytes.read(4))#from_file(bytes)

        #logging.debug('io.size = %#x', ioc.size)
        #logging.debug('io.char = %#x', ioc.char)

        bytes.seek((ioc.size-12)*4,1)
        bank = Bank.from_buffer_copy(bytes.read(36))
        #bank = Bank.from_buffer(record[4+(ioc.size-12)*4:4+(ioc.size-12)*4+9*4])

        logging.debug('bank.data = %#x', bank.data)
        logging.debug('bank.name = %s', bank.name)
        logging.debug('bank.id = %#x', bank.id)
        logging.debug('bank.links = %#x', bank.links)
        logging.debug('bank.status = %#x', bank.status)
        logging.debug('bank.data = %#x', bank.data)
        data = bytes.read(bank.data*4)
        #data = record[4+ioc.size*4-12:4+ioc.size*4-12+bank.data*4]
        assert len(data) == bank.data*4
        yield bank, data
        #record = record[4+ioc.size*4-12+bank.data*4:]

def parse(f):
    for lr in iter_logical_records(f):
        for bank, data in iter_banks(lr):
            yield bank

if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', help='increase verbosity', action='store_true')
    parser.add_argument('filename')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    with io.open(args.filename,'rb') as f:
        for i, bank in enumerate(parse(f)):
            if i % 10000 == 0:
                print('%i' % i, file=sys.stderr)
            #print(bank.name)
