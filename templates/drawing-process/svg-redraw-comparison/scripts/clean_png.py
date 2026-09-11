#!/usr/bin/env python3
"""Losslessly recompress PNG image data and remove optional metadata chunks."""
import argparse
import hashlib
from pathlib import Path
import struct
import zlib

SIGNATURE=b'\x89PNG\r\n\x1a\n'


def parse(data):
    if not data.startswith(SIGNATURE):raise ValueError('Expected PNG input')
    pos=8;chunks=[]
    while pos<len(data):
        if pos+12>len(data):raise ValueError('Truncated PNG')
        size=struct.unpack_from('>I',data,pos)[0];kind=data[pos+4:pos+8];end=pos+12+size
        if end>len(data):raise ValueError('Truncated PNG chunk')
        body=data[pos+8:end-4];crc=struct.unpack_from('>I',data,end-4)[0]
        if zlib.crc32(kind+body)&0xffffffff!=crc:raise ValueError('PNG checksum mismatch')
        chunks.append((kind,body));pos=end
        if kind==b'IEND':
            if pos!=len(data):raise ValueError('Trailing PNG data')
            break
    if not chunks or chunks[0][0]!=b'IHDR' or chunks[-1][0]!=b'IEND':raise ValueError('Invalid PNG structure')
    if any(k in {b'acTL',b'fcTL',b'fdAT'} for k,_ in chunks):raise ValueError('Animated PNG is not supported')
    return chunks


def chunk(kind,body):
    return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)


def clean(data):
    chunks=parse(data)
    image=zlib.decompress(b''.join(v for k,v in chunks if k==b'IDAT'))
    out=SIGNATURE;written=False
    for kind,body in chunks:
        if kind==b'IDAT':
            if not written:out+=chunk(kind,zlib.compress(image,9));written=True
        elif kind in {b'IHDR',b'PLTE',b'tRNS',b'IEND'}:out+=chunk(kind,body)
    decoded=zlib.decompress(b''.join(v for k,v in parse(out) if k==b'IDAT'))
    if decoded!=image:raise ValueError('Image data changed')
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=a.input.read_bytes();out=clean(raw)
    with a.output.open('xb') as f:f.write(out)
    print('Image data unchanged; output SHA-256:',hashlib.sha256(out).hexdigest())

if __name__=='__main__':main()
