# Extract-CC-Bytestream
Extract a closed-caption bytstream from video frames

Produces:
  * tarball of the extracted frame lines
  * the raw bytes (two per frame) of the data
  * a webvtt caption file

Tunables:
* $FFMPEG = the location of ffmpeg binary
* $ CCEXTRACT = the location of the ccextract binary
* $CCBASE = the starting line of the pgm for extraction
* $CCLINE = the PGM line to use for CC data (real=$CCBASE + $CCLINE)
* $CCHEIGHT = the height of the PGM file to make
* $FRAMERATE = the video frame rate
* $BITWIDTH = ~27 pixels per data bit.
* $DEBUG = when set, more output is created, including images with pink spots where the actual samples were made

# decode_cc.py

Extract a closed-caption bytestream from video frame files

This is a re-think of the perl code.  It should be a little more generalizable.
It was mostly so I can learn Python, so it's probably not idomatic.
In any case...

  usage: decode_cc.py [-h] [--threads THREADS] [--debug] [--output OUTPUT]
                      ccline file-or-dir [file-or-dir ...]

  Extract CC data from frame images

  positional arguments:
    ccline             Frame line containing CC data
    file-or-dir        Frame image files or directories

  optional arguments:
    -h, --help         show this help message and exit
    --threads THREADS  Number of CPUs to use
    --debug            Turn on debugging
    --output OUTPUT    Bitstream output file (defaults to stdout)


Unlike the perl version, this one requires that you extract the images via
your tool of choice (ffmpeg, for example) before processing, and it doesn't do
anything with the extracted bytestream except produce it.  Normally, you'd run
that through something like ccextractor or the like.

The Python version will automatically derive the bit size from the data stream
and it will adjust the luma of the image to try to get the best data.
