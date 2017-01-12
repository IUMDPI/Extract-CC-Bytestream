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
