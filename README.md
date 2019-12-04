# music-scheduling-playout-software
Music scheduling and playout software

Software capable of scheduling music and placing into a queue which plays out over system default audio device.

## Prerequisites

python 3.5 or higher

`pip install numpy`

`pip install pillow`

`pip install pyaudio`

`pip install requests`

`pip install tkinter`

some systems I tested also needed `sudo apt-get install python3-pil.imagetk`

Also needed is ffmpeg

Linux users: `pip install tkinter`

Windows users: `https://www.ffmpeg.org/download.html`. Download the binary

## Usage

Scheduling is done through the text file "schedule.txt". The format of this file is as follows:

[entry]

parameter line

list of files/folders/urls (one per line)

[end]

### ------------------

### [entry] - beginning of a scheduled block

### parameter line - single line of semicolon seperated values that dictate how this block will operate.

First parameter - group name. This is used to determine if this block is the same as the currently scheduled block. This will make more sense in a moment. Can be `any` to match all other groups in which case the show top (explained below) will always be added when filling the queue. Can include spaces if necessary.

Second parameter - 3 letter abbreviated day. The day this block is to be used. Can also be 'any' to match all days

Third parameter - time in. The time, in 24-hour format, that that this block starts. Can use `xx` to match any hour/min/sec

Fourth parameter - time out. The time, in 24-hour format, that that this block ends. Can use `xx` to match any hour/min/sec

Fifth parameter - show top. A file path that will play one time if this block's group name differs from the currently playing group name (unless this block's group name is `any`). This can be used to play a show intro or similar if this block is the start of a new show. If set to `none`, this option is not used

All other parameters - queue options. Currently implemented options include: clear, top, and immediate

clear - empties the queue if this block is playing for the first time.

top - places items in this block at the top of the queue instead of at the bottom. 

immediate - attempts to end what is currently playing after queueing this block. 

These queue options can be combined once they are seperated by semicolons

e.g. taco tuesday;tue;12:00:00;13:00:00;none;clear

This will play on Tuesdays between 12pm and 1pm. There is no show intro and the queue will be cleared the first time this block is loaded

e.g. any;any;xx:30:00;xx:30:00;path/to/file.mp3;top

This will play every day at the 30 min mark of every hour. The show top and any listed files/folders/urls will be added to the top of the queue.

### list of files/folders/urls (one per line)

These are loaded into the queue any time the queue length reaches 1 or less and the current time is within the block's time.

A path to a single file will queue that file

Folder paths (ending with / or \ depending on what OS you use) will choose a random file from that folder. Relative or absolute paths are accepted.

Urls play as usual. The queue will continue if the connection is lost for any reason. Currently only shoutcast streams are supported.

### [end] - End of this scheduled block

This format can be repeated any number of times for different scheduled blocks. 

# Class parameters

`no_repeat_time=(num of mins)` - Number of minutes before a file selected from a folder can play again. Defaults to 60 minutes
