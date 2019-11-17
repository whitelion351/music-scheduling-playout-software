# music-scheduling-playout-software
Music scheduling and playout software

Software capable of scheduling music and placing into a queue which plays out over system default audio device.

## prerequisites

`sudo apt-get install mplayer`

`pip install numpy`

`pip install pillow`

Scheduling is configured through the text file "schedule.txt". The format of this file is as follows:

[entry]

parameter line

list of files/folders/urls (one per line)

[end]

### ------------------

### [entry] - beginning of a scheduled block

### parameter line - single line of semicolon seperated values that dictate how this block will operate.

First parameter - group name. This is used to determine if this block is the same as the currently scheduled block. This will make more sense in a moment.

Second parameter - 3 letter abbreviated day. The day this block is to be used. Can also be 'any' to match all days

Third parameter - time in. The time, in 24-hour format, that that this block starts.

Fourth parameter - time out. The time, in 24-hour format, that that this block ends.

Fifth parameter - show top. A file path that will play one time if this block's group name differs from the currently playing group name. This can be used to play a show intro or similar if this block is the start of a new show.

All other parameters - queue options. options include clear, top, and immediate

clear - empties the queue if this block is playing for the first time.

top - places items in this block at the top of the queue instead of at the bottom. 

immediate - attempts to end what is currently playing after queueing this block. 

These queue options can be combined once they are seperated by semicolons

### list of files/folders/urls (one per line)

path to a single file will queue that file

folder paths (ending with / or \ depending on what OS you use) will choose a random file from the folder

urls play as usual once they do not timeout while connecting. The queue will continue if the connection is lost for any reason.

### [end] - End of this scheduled block
