#!/usr/bin/env python3.6

from PIL import Image
from multiprocessing import Pool
import sys
import math
import argparse
import os


def decodeFrame(filename, line, DEBUG):
    """
    Take a frame image and extract the line 21 CC bytes

    Parameters
    ----------
    filename : The frame image filename
    line : The line (in the image) where the CC data appears
    DEBUG : turn on debugging

    Returns
    -------
    Two bytes of decoded data, or a pair of nulls if the frame doesn't
    contain valid CC.

    Notes
    -----
    FCC 73.699 figure 17 shows the format of the data

    The spec uses percentages of an H clock which is pretty useless for
    a software implementation...but they helpfully list how long it takes
    for each of the parts are in the signal.  That's actually really good,
    because we can do some magic and if we can find the width of one piece,
    we should be able to shift and scale to find all of the other pieces.

    Every line consists of these parts:
    * 7 Cycles of 0.503MHz ("run-in").  
    * Some dead space
    * A Start bit
    * 16 bits of data, as two 7-bit + parity ASCII characters

    Most measurements are from the midpoint of a rise or fall.  I'll denote
    those as "mid". 

    The Line 21 data takes a total of 51.268uS from zero before the start of 
    the run-in and the zero of the last bit of data.  This is the only
    measurement that uses zero-to-zero measurements.  

    The run-in takes 12.910uS from mid-to-mid which is 25.1% of the width.
    At this point in the narrative, we don't know what the start point would
    be.  

    The dead space takes 3.972uS mid-to-mid which is 7.7% of the width and it
    starts immediately after end of the run-in.

    The start bit takes 1.986uS mid-to-mid which is 3.8% of the width and it
    starts immediately after the dead space.

    The 8 data bits are 8 * 1.986uS = 31.776uS mid-to-mid which is 61.9% of
    the width and starts immediately after the start bit.

    Since we have all of the lengths mid-to-mid, the total signal length comes
    out to 98.5% of the width.  So 1.5% of the total width of the data is a 
    rising edge of the run-in and the rising- or falling-edge of the last bit
    of data.

    There are still two things we're missing:  the starting point of the 
    data line (the shift) and its width (the scale).

    The shift should be easy:  the first value over 50% on the run-in is the 
    beginning of our data parts.

    The scale can also be determined by the run-in:  there should be 7
    groups of waveform parts that are > 50% followed by a bunch of low
    signal.  Since the run-in is a fixed size, we should be able to determine
    the total size from it.

    After that, it's just a matter of reading the bits.
    
    """
    original = Image.open(filename)
    luma = original.convert(mode = "L")
    width, heigh = luma.size
    line21 = luma.crop((0, line, width, line + 1))
    pixels = line21.load()

    if DEBUG:
        print(f"File: {filename}, Line: {line}, Dimensions: {line21.width}x{line21.height}",
              file = sys.stderr)
              
    
    # find the maximum value and convert the image to a list of values
    values = []
    maxluma = 0
    for x in range(width):
        cpixel = pixels[x, 0]
        if cpixel > maxluma: maxluma = cpixel
        values.append(cpixel)

    # if maxluma is less than 32 (1/8 brightness), then it's just a black 
    # line, so there can't be data
    if maxluma < 32:
        return (0, 0)
        
    # convert the values into 0 & 1 based on whether or not the signal
    # is above or below the 25 IRE mark.
    #  BUT, use a hysteresis for values in the middle 10% to avoid issues
    #  with a wobbly signal.
    lastVal = 0
    for x in range(len(values)):
        v = math.floor(100 * (values[x] / maxluma))
        if 45 <= v <= 55:
            values[x] = lastVal
        else:
            values[x] = 1 if v > 50 else 0
        lastVal = values[x]

    # find the leading edge of the run-in
    startRunIn = 0
    for x in range(len(values)):
        if values[x] == 1:
            startRunIn = x
            break
        
    # if that start position is > 5% of the whole run, then it is too
    # late to be a CC frame.  Just send back a pair of NUL bytes
    if startRunIn > width * 0.05:
        return (0, 0)

    if DEBUG:
        print(f"First 1 at position {startRunIn} < {width * 0.05}.  maxluma = {maxluma}",
              file = sys.stderr)

    # now find the length of the run-in.  It should be 13 value changes
    # since the wave crosses the center point a total of 14 times and
    # startRunIn is at the first crossing.
    lastVal = 1
    count = 0;
    stopRunIn = 0
    for x in range(startRunIn, len(values)):
        if values[x] != lastVal:
            lastVal = values[x]
            count = count + 1
            if count == 13:
                stopRunIn = x
                break
    if DEBUG:
        print(f"Run-in stop: {stopRunIn} ({0.2 * width}, {0.3 * width})",
              file = sys.stderr)
            
    # if we didn't find 13 more transitions, it's not a valid CC frame
    if stopRunIn == 0:
        return (0, 0)

    # if the run-in (which is 25.1% of the data) was less than 20% of the
    # whole data set OR it was more than 30% of the data set, then it was
    # the wrong size (or not actually the run in at all) and the CC is
    # invalid.
    if stopRunIn < (0.2 * width) or stopRunIn > (0.3 * width):        
        return (0, 0)

    # Now that we know the length of the run-in, and we know it's 25.1% of
    # the data, then we know the length of the data and that should give us
    # everything we need to decode the frame.
    runInLength = stopRunIn - startRunIn
    dataSpan = runInLength / 0.251

    # now we can tell how wide a bit is.  
    bitWidth = math.ceil(dataSpan * 0.038)

    # we can also determine when the bits start.  We just have to look for
    # the first 1 bit after the stopRunIn and add 1 bit width to it.  The
    # dead zone and start bit will have negative offets in getBit, but the
    # rest should be in a natural position.
    bitStart = stopRunIn
    while values[bitStart] == 0 and bitStart < width - 1:
        bitStart = bitStart + 1
    bitStart = bitStart + bitWidth
        
    if DEBUG:
        print(f"Run-in length: {runInLength}, Data span: {dataSpan}, bit width: {bitWidth}",
              file =sys.stderr)


    def getBit(bit):
        """
        Sample a given bit within the data area.  If the number is
        negative, it will be the start bit (-1) or either of the two
        dead bits (-2 or -3).  If the value is out of range of the data,
        then -1 will be returned.
        """
        offset = int(bitStart + (bit * bitWidth) + (bitWidth / 2))
        # if we're out of range, return a sentinel.
        if offset > (len(values) - 1) or offset < 0:
            return -1
        if DEBUG:
            print(f"bit: {bit}, offset: {offset} ", end='', file = sys.stderr)
            for x in range(math.floor(bitWidth)):
                o = int(math.floor(bitStart + (bit * bitWidth) + x))
                if o == offset:
                    print(f">>{values[o]}<<", end='', flush=True,
                          file =sys.stderr)
                else:
                    print(values[o], end='', flush=True, file = sys.stderr)
            print(file = sys.stderr)
        return values[offset]


    try:
        data = []    
        # One last sanity check:  the there's two low bits (the dead space)
        # and a start bit.  we should have 0, 0, 1 for those bits.  
        sanity = (getBit(-3), getBit(-2), getBit(-1))
        if DEBUG:
            print(f"Sanity: {sanity}", file = sys.stderr)
        if (0, 0, 1) != sanity:
            raise ValueError(f"Start bit sanity check failed on {filename} -- got {sanity} rather than (0, 0, 1)")

        for base in (0, 8):
            byte = 0
            parity = 0
            for b in range(0, 7):
                v = getBit(base + b)
                if v == -1:
                    # bit location is out of range
                    raise ValueError(f"Computed location for bit {base + b} in file {filename} is out of range")
                if v:
                    byte = byte + (1 << b)
                    parity = parity + 1
                    
            # Odd parity, so parity count + the parity bit should be an
            # odd number.  If not, it's invalid.
            if (getBit(base + 7) + parity) & 1 != 1:
                raise ValueError(f"Parity check in file {filename} for byte starting at bit {base} failed.")

            if DEBUG:
                print(f"Final Byte Value: {byte}", file = sys.stderr)
            data.append(byte)
        return data
    except ValueError as e:
        if DEBUG:
            pass
        else:
            print(f"Value Exception: {e}", file = sys.stderr)
            return (0, 0)


def getByteStream(images, line, threads = None, DEBUG = 0):
    """
    Multithreaded bytestream decode for all of the given images.  A byte
    array of the raw data is returned.
    """
    pool = Pool(threads)
    iterArgs = []
    for i in images:
        iterArgs.append([i, line, DEBUG])
    results = pool.starmap(decodeFrame, iterArgs)
    if DEBUG:
        print(results, file = sys.stderr)
    bytes = bytearray()
    for r in results:
        for b in r: bytes.append(b)
    return bytes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Extract CC data from frame images")
    parser.add_argument("--threads",
                        default = None,
                        dest = 'threads',
                        type = int,
                        help = "Number of CPUs to use")
    parser.add_argument("--debug",
                        action = "store_true",
                        default = False,
                        help = "Turn on debugging")
    parser.add_argument("--output",
                        type = argparse.FileType('w'),
                        dest = "output",
                        default = sys.stdout,
                        help = "Bitstream output file (defaults to stdout)")
    parser.add_argument("ccline",
                        type = int,
                        help = "Frame line containing CC data")
    parser.add_argument("file-or-dir",
                        nargs = '+',
                        help = "Frame image files or directories")
    args = vars(parser.parse_args(sys.argv[1:]))
    files = []
    for f in args["file-or-dir"]:
        if os.path.isfile(f):
            files.append(f)
        elif os.path.isdir(f):
            for i in os.listdir(f):
                file = os.path.join(f, i)
                if os.path.isfile(file):
                    files.append(file)
            files.sort()
        else:
            print(f"Not a file or directory: {f}")
            sys.exit(1)
    bytes = getByteStream(files, args["ccline"], args["threads"], args["debug"])

    print(bytes.decode('ascii'), file = args["output"])


