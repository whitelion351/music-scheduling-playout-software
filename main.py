import os
import random
from threading import Thread, Timer
import time
import tkinter as tk
from tkinter import scrolledtext
import subprocess
import requests
import pyaudio
import numpy as np
from PIL import ImageTk, Image


class MainWindow(tk.Tk):
    def __init__(self, no_repeat_time=60):
        super(MainWindow, self).__init__()
        self.title("Lion Music Scheduler")
        self.update_delay = 0.1
        self.canvas = tk.Canvas(self, width=699, height=499, bg="#555555")
        self.canvas.pack()
        self.all_decks = []
        self.available_decks = []
        self.master_volume = 1.0
        self.deckA = self.PlayerDeck(self, "A")
        self.deckB = self.PlayerDeck(self, "B")
        self.deckA.deck_frame.place(x=10, y=10)
        self.deckB.deck_frame.place(x=355, y=10)
        self.font = ("helvetica", 10)
        self.master_volume_var = tk.StringVar()
        self.master_volume_var.set(str(int(self.master_volume*100))+"%")
        self.volume_down_button = tk.Button(self, font=self.font, text="-", command=self.master_volume_down)
        self.volume_down_button.place(x=10, y=135, width=20, height=20)
        self.volume_display_label = tk.Label(self, font=self.font, textvariable=self.master_volume_var)
        self.volume_display_label.place(x=30, y=135, width=40, height=20)
        self.volume_up_button = tk.Button(self, font=self.font, text="+", command=self.master_volume_up)
        self.volume_up_button.place(x=70, y=135, width=20, height=20)
        self.load_next_button = tk.Button(self, font=self.font, text="load next", command=self.load_next_in_queue)
        self.load_next_button.place(x=100, y=135, width=70, height=20)
        self.remove_next_button = tk.Button(self, font=self.font, text="remove next", command=self.remove_next_in_queue)
        self.remove_next_button.place(x=180, y=135, width=90, height=20)
        self.queue_window = self.QueueWindow(self)
        self.queue_window.queue_frame.place(x=10, y=160)
        self.log_window = self.LogWindow(self)
        self.log_window.log_frame.place(x=10, y=350)
        self.queue_list = []
        self.valid_exts = [".mp3", ".wav", ".ogg", ".wma", ".flac"]
        self.played_dict = {}
        self.no_repeat_time = no_repeat_time
        self.sched_name = None
        self.initialize = True

    def master_volume_down(self):
        if self.master_volume > 0.0:
            self.master_volume = round(self.master_volume - 0.05, 2)
            self.master_volume_var.set(str(int(self.master_volume * 100))+"%")
            for d in self.all_decks:
                d.volume = self.master_volume

    def master_volume_up(self):
        if self.master_volume < 1.0:
            self.master_volume = round(self.master_volume + 0.05, 2)
            self.master_volume_var.set(str(int(self.master_volume * 100))+"%")
            for d in self.all_decks:
                d.volume = self.master_volume

    def load_next_in_queue(self):
        for d in self.all_decks:
            if d.status == "playing":
                print("deck{} {} => user ending".format(d.deck_id, d.status))
                d.status = "ending"
                thread = Timer(d.fade_out_time, self.deck_reset, args=[d])
                thread.start()
                break

    def remove_next_in_queue(self):
        if len(self.queue_list) == 0:
            return
        item = self.queue_list.pop(0)
        split_index = item.rfind("/")
        split_index = item.rfind("\\") if split_index == -1 else split_index
        if split_index != -1:
            path = item[:split_index+1]
            file = item[split_index+1:]
            if file.rfind(".") != -1:
                del self.played_dict[path][file]
        self.queue_window.refresh()

    def load_from_queue(self, path, deck_object=None):
        if deck_object is None:
            deck_object = self.deckA if self.deckA.status == "stopped" else self.deckB
        deck_object.song_type = "stream" if path.startswith("http") else "file"
        info_string = "deck{} LOAD: {}".format(deck_object.deck_id, path)
        print(info_string)
        self.log_window.log_window_update(info_string)
        deck_object.song_file_path = path
        if deck_object.song_type == "stream":
            status_thread = Thread(name="deck" + deck_object.deck_id + " load_stream_thread",
                                   target=deck_object.play_stream, args=[path])
            status_thread.start()
        elif deck_object.song_type == "file":
            deck_object.load_audio_file(path)
        if deck_object in self.available_decks:
            self.available_decks.remove(deck_object)
        self.queue_window.refresh()

    def process_schedule(self):
        while self.deckA.running and self.deckB.running:
            process_time = time.time()
            total_added = 0
            do_immediate = False
            with open("schedule.txt", "r") as sched:
                _ = sched.readlines()
                eof = sched.tell()
                sched.seek(0)
                while sched.tell() != eof:
                    line = sched.readline().rstrip("\n")
                    if line.startswith("#") or line.startswith(" "):
                        continue
                    elif line == "[entry]":
                        details = sched.readline().rstrip("\n")
                        details = details.split(sep=";")
                        entry_name, entry_day, entry_in, entry_out, entry_top = details[:5]
                        entry_options = details[5:]
                        if entry_day == time.strftime("%a").lower() or entry_day == "any":
                            entry_in = self.get_secs_from_sched_time(entry_in)
                            entry_out = self.get_secs_from_sched_time(entry_out)
                            current_secs = time.mktime(time.localtime())
                            if entry_in <= current_secs <= entry_out:
                                reading = True
                                new_items = []
                                if entry_name != self.sched_name:
                                    print("new schedule group:", details[:4])
                                    self.log_window.log_window_update("new schedule group: {}".format(details[:4]))
                                    print("using queue options = ", entry_options)
                                    if entry_name != "any" and entry_name != "none":
                                        self.sched_name = entry_name
                                    if "clear" in entry_options:
                                        print("queue_list was cleared")
                                        self.queue_list = []
                                    if entry_top != "none":
                                        print("added show top:", entry_top)
                                        new_items.append(entry_top)
                                        total_added += 1
                                    if "immediate" in entry_options:
                                        do_immediate = True
                                elif len(self.queue_list) > 1:
                                    reading = False
                                while reading is True:
                                    line = sched.readline().rstrip("\n")
                                    if line == "[end]":
                                        reading = False
                                    else:
                                        if line.endswith("/") or line.endswith("\\"):
                                            line = self.choose_from_directory(line)
                                        if line is not None:
                                            new_items.append(line)
                                            total_added += 1
            if total_added > 0:
                if "top" in entry_options:
                    new_items.extend(self.queue_list)
                    self.queue_list = new_items
                else:
                    self.queue_list.extend(new_items)
                print("added {} to queue. queue_length = {}".format(total_added, len(self.queue_list)))
                if do_immediate is True:
                    for d in self.all_decks:
                        if d.status == "playing" or d.status == "loading":
                            print("executing immediate option")
                            d.status = "ending"
                            ending_timer = Timer(d.fade_out_time - self.update_delay, self.deck_reset, args=[d])
                            ending_timer.start()
                            break
                    else:
                        print("could not process 'immediate' option")
                self.queue_window.refresh()
                if len(self.available_decks) >= 2 and self.initialize is False:
                    print("queue is loading a track")
                    self.load_from_queue(self.queue_list.pop(0), self.available_decks.pop(0))
            sleep_time = 1 + (0.2 - (process_time % 1))
            if sleep_time > 0.0:
                time.sleep(sleep_time)
            if int(time.time()) - int(process_time) != 1 and self.initialize is False:
                print("scheduler missed a second ({})".format(int(time.time()) - int(process_time)))

    @staticmethod
    def get_secs_from_sched_time(entry):
        h = entry[:2] if entry[:2] != "xx" else time.strftime("%H")
        m = entry[3:5] if entry[3:5] != "xx" else time.strftime("%M")
        s = entry[6:8] if entry[6:8] != "xx" else time.strftime("%S")
        cur_time = time.localtime()
        year = str(cur_time.tm_year)
        month = str(cur_time.tm_mon)
        day = str(cur_time.tm_mday)
        time_string = "{} {} {} {} {} {}".format(year, month, day, h, m, s)
        time_tup = time.strptime(time_string, "%Y %m %d %H %M %S")
        return time.mktime(time_tup)

    def choose_from_directory(self, path):
        try:
            full_list = os.listdir(path)
        except FileNotFoundError:
            print("directory {} not found".format(path))
            self.log_window.log_window_update("directory {} not found".format(path))
            return None
        if path not in self.played_dict.keys():
            self.played_dict[path] = {}
        choices = []
        for file in full_list:
            index = file.rfind(".")
            if file[index:] in self.valid_exts:
                if file not in self.played_dict[path].keys():
                    choices.append(file)
                elif time.time() > self.played_dict[path][file] + (self.no_repeat_time * 60):
                    del self.played_dict[path][file]
                    choices.append(file)
        if len(choices) > 0:
            choice = random.choice(choices)
            self.played_dict[path][choice] = time.time()
            return path + choice
        else:
            print("no valid files found in {}".format(path))
            self.log_window.log_window_update("no valid files found in {}".format(path))
            return None

    def process_decks(self):
        while self.deckA.running and self.deckB.running:
            if self.initialize:
                if len(self.queue_list) > 0:
                    self.load_from_queue(self.queue_list.pop(0), self.available_decks.pop(0))
                    self.queue_window.refresh()
                    self.initialize = False
                time.sleep(1)
            else:
                process_time = time.time()
                if len(self.queue_list) == 0:
                    print("QUEUE LIST IS EMPTY. NO DECK MANAGEMENT POSSIBLE")
                    time.sleep(2)
                    continue
                for deck_object in self.all_decks:
                    if deck_object.status == "playing":
                        if deck_object in self.available_decks:
                            self.available_decks.remove(deck_object)
                        if deck_object.song_type == "stream":
                            file_path = deck_object.song_file_path
                            if file_path == "":
                                print("resetting deck{} - no file path".format(deck_object.deck_id))
                                self.deck_reset(deck_object)
                                if len(self.queue_list) > 0:
                                    self.load_from_queue(self.queue_list.pop(0))
                                continue
                        elif deck_object.song_type == "file":
                            if deck_object.remaining < deck_object.fade_out_time and deck_object.status != "ending":
                                print("deck{} {} => ending".format(deck_object.deck_id,  deck_object.status))
                                deck_object.status = "ending"
                                ending_timer = Timer(deck_object.remaining - self.update_delay,
                                                     self.deck_reset, args=[deck_object])
                                ending_timer.start()
                    if deck_object.status == "ending":
                        for d in self.all_decks:
                            if deck_object.deck_id == d.deck_id:
                                continue
                            elif d.status == "playing" or d.status == "loading" or d.status == "ending":
                                break
                            else:
                                if len(self.queue_list) > 0:
                                    self.load_from_queue(self.queue_list.pop(0), self.available_decks.pop(0))
                                break
                    if deck_object.status == "stuck":
                        self.deck_reset(deck_object)
                        if len(self.queue_list) > 0:
                            self.load_from_queue(self.queue_list.pop(0), self.available_decks.pop(0))
                sleep_time = 1 + (0.5 - (process_time % 1))
                if sleep_time > 0.0:
                    time.sleep(sleep_time)

    @staticmethod
    def deck_reset(deck_object):
        deck_object.status = "stopped"
        deck_object.song_type = ""
        deck_object.song_file_path = ""
        deck_object.song_artist = ""
        deck_object.song_title = ""
        deck_object.volume = deck_object.root.master_volume
        deck_object.remaining = 999
        deck_object.raw_chunk = bytes(2)
        deck_object.resample = False
        deck_object.reset_view(deck_object)
        if deck_object not in deck_object.root.available_decks:
            deck_object.root.available_decks.append(deck_object)
        print("deck{} reset".format(deck_object.deck_id))

    def run_app(self):
        print("app starting")
        thread = Thread(name="schedule_thread", target=self.process_schedule, daemon=True)
        thread.start()
        time.sleep(1)
        thread = Thread(name="deck_manage_thread", target=self.process_decks, daemon=True)
        thread.start()
        try:
            self.mainloop()
        except (KeyboardInterrupt, SystemExit):
            self.close_app()
        else:
            self.close_app()

    def close_app(self):
        print("app closing")
        self.deckA.running = False
        self.deckB.running = False
        self.deckA.status = "quitting"
        self.deckB.status = "quitting"
        time.sleep(1)
        self.quit()

    class PlayerDeck:
        def __init__(self, root, deck_id):
            self.width = 335
            self.height = 120
            self.font = ("helvetica", 10)
            self.buffer_size = 800
            self.song_artist = ""
            self.song_title = ""
            self.song_file_path = ""
            self.song_type = ""
            self.sample_rate = 44100
            self.channels = 2
            self.duration = 0
            self.remaining = 999
            self.song_start_time = -1
            self.status = "stopped"
            self.running = True
            self.update_delay = root.update_delay
            self.last_time_pos = 0.0
            self.root = root
            self.deck_id = deck_id

            # pyaudio and audioread creation for reading files only
            self.chunk_size = 2048
            self.port_audio = pyaudio.PyAudio()
            self.audio_out = None
            self.create_audio_out_stream()
            self.file_stream = []
            self.raw_chunk = bytes(2)
            self.volume = self.root.master_volume
            self.fade_out_decay = 0.0055
            self.fade_out_time = 5

            # add deck to deck lists
            root.all_decks.append(self)
            root.available_decks.append(self)

            # start file play thread
            thread = Thread(name="deck" + self.deck_id + "_play", target=self.play_file_stream, daemon=True)
            thread.start()

            # Background Frame
            self.deck_frame = tk.Frame(root, width=self.width, height=self.height, bd=10, relief="ridge")

            # Time Label
            self.time_label_var = tk.StringVar()
            self.time_label_var.set("00:00:00")
            self.time_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                       textvariable=self.time_label_var)
            self.time_label.place(x=5, y=10, width=60, height=14)

            # Duration Label
            self.duration_label_var = tk.StringVar()
            self.duration_label_var.set("00:00:00")
            self.duration_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                           textvariable=self.duration_label_var)
            self.duration_label.place(anchor="ne", x=280, y=10, width=60, height=14)

            # Artist Label
            self.artist_label_var = tk.StringVar()
            self.artist_label_var.set(self.song_artist)
            self.artist_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF", anchor="w",
                                         textvariable=self.artist_label_var)
            self.artist_label.place(x=5, y=25, width=275, height=14)

            # Title Label
            self.title_label_var = tk.StringVar()
            self.title_label_var.set(self.song_title)
            self.title_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF", anchor="w",
                                        textvariable=self.title_label_var)
            self.title_label.place(x=5, y=40, width=275, height=14)

            # File Path Label
            self.file_path_label_var = tk.StringVar()
            self.file_path_label_var.set(self.song_file_path)
            self.file_path_label = tk.Label(self.deck_frame, font=self.font, bg="#555555", fg="#FFFFFF", anchor="w",
                                            textvariable=self.file_path_label_var)
            self.file_path_label.place(x=5, y=55, width=275, height=14)

            # volume VU Meter
            self.vol_image = self.create_volume_image()
            self.volume_display = tk.Label(self.deck_frame, image=self.vol_image, anchor="w")
            self.volume_display.place(anchor="center", relx=0.95, rely=0.4, width=10, height=70)

            # Status Label
            self.status_label_var = tk.StringVar()
            self.status_label_var.set(self.status)
            self.status_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                         textvariable=self.status_label_var)
            self.status_label.place(anchor="center", relx=0.9, rely=0.9, width=60, height=12)

            self.next_button = tk.Button(self.deck_frame, font=self.font, text="Next", command=self.next_in_queue)
            self.next_button.place(anchor="center", x=200, y=85, width=50, height=20)

            update_thread = Thread(name="deck"+self.deck_id+" update_view_thread",
                                   target=self.update_view, args=[self], daemon=True)
            update_thread.start()

        def play_stream(self, path):
            self.file_stream = []
            print("deck{} {} => loading".format(self.deck_id, self.status))
            self.status = "loading"

            headers = {"user-agent": "Lion Broadcaster", "Icy-MetaData": "1"}
            resp = requests.get(path, headers=headers, stream=True)
            if resp.status_code != 200:
                resp.close()
                self.root.deck_reset()
                return
            elif "icy-name" in resp.headers.keys():
                self.song_artist = resp.headers["icy-name"]
            metaint_header = "icy-metaint"
            if metaint_header in resp.headers.keys():
                metaint_value = int(resp.headers[metaint_header])
                print("found", metaint_header, ":", metaint_value)
            else:
                print("no metaint_value found in headers")
                metaint_value = 0
            connected = True
            data = resp.iter_content()
            pad_byte = b'\x00'.decode()

            ff_proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-f", "mp3", "-i", "pipe:", "-f", "s16le",
                                        "-ac", "2", "pipe:"],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stdout_thread = Thread(target=self.read_stdout, args=[ff_proc.stdout], daemon=True)
            stderr_thread = Thread(target=self.read_stderr, args=[ff_proc.stderr], daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            stream_output = bytes()
            while connected and self.status != "stopped":
                try:
                    if len(self.file_stream) > self.buffer_size:
                        while len(self.file_stream) > self.buffer_size:
                            time.sleep(0.001)
                            if self.status == "stopped":
                                raise StopIteration
                    for _ in range(metaint_value if metaint_value > 0 else 1):
                        stream_output += next(data)
                        if len(stream_output) == 1024:
                            ff_proc.stdin.write(stream_output)
                            stream_output = bytes()
                    if metaint_value > 0:
                        d = next(data)
                        meta_counter_end = int.from_bytes(d, byteorder="little")
                        meta_counter = 0
                        metadata_bytes = bytes()
                        while meta_counter < meta_counter_end * 16:
                            metadata_bytes += next(data)
                            meta_counter += 1
                        decoded = metadata_bytes.decode()
                        decoded = decoded.rstrip(pad_byte)
                        if decoded != "":
                            song_title = decoded
                            self.song_title = song_title[13:].rstrip("\';")
                except StopIteration:
                    connected = False
                    print("no more data")
            ff_proc.kill()
            resp.close()
            self.status = "stopped" if self.status != "stopped" else self.status
            stdout_thread.join()
            stderr_thread.join()
            print("stream thread closed")

        def read_stdout(self, out):
            while self.status != "stopped":
                self.file_stream.append(out.read(2048))
                if len(self.file_stream) > 800 and self.status == "loading":
                    print("deck{} {} => playing".format(self.deck_id, self.status))
                    self.status = "playing"

        def read_stderr(self, err):
            while self.status != "stopped":
                err.readline().decode().rstrip("\n")

        def load_audio_file(self, path=None):
            if path is None:
                print("you must pass a path to get_file_audio")
                return False
            self.file_stream = []
            print("deck{} {} => loading".format(self.deck_id, self.status))
            self.status = "loading"
            try:
                ff_proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-i", path, "-f", "s16le", "-ar",
                                            str(self.sample_rate), "-ac", str(self.channels), "pipe:"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                done = False
                while done is False:
                    buf = ff_proc.stdout.read(2048)
                    if len(buf) == 0:
                        done = True
                    else:
                        self.file_stream.append(buf)

            except Exception as e:
                print("while trying to load audio file, the following happened...")
                print(e)
                return False
            else:
                self.song_artist = self.get_ffprobe_info(path, "artist")
                self.song_title = self.get_ffprobe_info(path, "title")
                self.duration = float(self.get_ffprobe_info(path, "duration"))
                print("deck{} {} => playing".format(self.deck_id, self.status))
                self.status = "playing"
                return True

        def create_audio_out_stream(self):
            if self.audio_out is not None:
                self.audio_out.close()
            self.audio_out = self.port_audio.open(format=pyaudio.paInt16, channels=self.channels,
                                                  rate=self.sample_rate, output=True,
                                                  frames_per_buffer=self.chunk_size)

        @staticmethod
        def get_ffprobe_info(path=None, tag=None):
            if path is None or tag is None:
                print("your need to pass the path and tag to look for with ffprobe")
                return ""
            if tag == "duration":
                sub_command_string = ["ffprobe", "-v", "error", "-show_entries", "format={}".format(tag),
                                      "-of", "default=nk=1:nw=1", path]
            else:
                sub_command_string = ["ffprobe", "-v", "error", "-show_entries", "format_tags={}".format(tag),
                                      "-of", "default=nk=1:nw=1", path]
            std_out = subprocess.run(sub_command_string, stdout=subprocess.PIPE)
            if len(std_out.stdout) > 0:
                return std_out.stdout.decode().rstrip("\n")
            else:
                return ""

        def play_file_stream(self):
            while self.running is True:
                if self.status == "playing":
                    self.song_start_time = time.time()
                    while len(self.file_stream) > 0 and (self.status == "playing" or self.status == "ending"):
                        if len(self.file_stream) == 0:
                            break
                        self.raw_chunk = self.file_stream.pop(0)
                        processed_chunk = self.raw_chunk

                        # adjust volume is necessary
                        if self.status == "ending":
                            self.volume -= self.fade_out_decay if self.volume - self.fade_out_decay >= 0 else 0
                        if self.volume != 1.0:
                            processed_chunk = np.frombuffer(processed_chunk, dtype=np.int16) * self.volume
                            processed_chunk = np.array(processed_chunk, dtype=np.int16)
                            processed_chunk = processed_chunk.tobytes()
                        # write to pyaudio
                        self.audio_out.write(processed_chunk)
                    self.status = "stopped" if self.status != "stopped" else self.status
                    if self not in self.root.available_decks:
                        self.root.available_decks.append(self)
                else:
                    # write silence if not playing to avoid buffer under run
                    self.audio_out.write(bytes(self.chunk_size))

        def next_in_queue(self):
            if self.status == "playing":
                print("deck{} {} => user ending".format(self.deck_id, self.status))
                self.status = "ending"
                thread = Timer(self.fade_out_time, self.root.deck_reset, args=[self])
                thread.start()

        @staticmethod
        def update_view(deck_object):
            try:
                last_update = time.time()
                last_volume = 0
                while deck_object.running is True:
                    if deck_object.status == "playing" or deck_object.status == "ending":
                        if deck_object.song_type == "stream":
                            vol_level = deck_object.get_volume_level()
                        elif deck_object.song_type == "file":
                            vol_level = np.frombuffer(deck_object.raw_chunk, dtype=np.int16).max()
                        else:
                            vol_level = 0
                        if vol_level < last_volume:
                            vol_level = last_volume - 5000
                        last_volume = vol_level
                        deck_object.vol_image = deck_object.get_volume_image(vol_level)
                        deck_object.volume_display.configure(image=deck_object.vol_image)
                        if time.time() - last_update > 1:
                            last_update = time.time()
                            # update song file path
                            if deck_object.file_path_label_var.get() != deck_object.song_file_path:
                                deck_object.file_path_label_var.set(deck_object.song_file_path)
                            # update current and remaining time and duration
                            time_string = deck_object.get_time_pos(time.time() - deck_object.song_start_time)
                            if time_string is not None and time_string != deck_object.time_label_var.get():
                                deck_object.time_label_var.set(time_string)
                            duration_string = deck_object.get_time_pos(deck_object.duration)
                            if duration_string != deck_object.duration_label_var.get():
                                deck_object.duration_label_var.set(duration_string)
                            deck_object.remaining = (deck_object.song_start_time + deck_object.duration) - time.time()
                            # update song artist
                            if deck_object.artist_label_var.get() != deck_object.song_artist:
                                deck_object.artist_label_var.set(deck_object.song_artist)
                            # update song title
                            if deck_object.title_label_var.get() != deck_object.song_title:
                                deck_object.title_label_var.set(deck_object.song_title)
                            # update deck status
                            if deck_object.status_label_var.get() != deck_object.status:
                                deck_object.status_label_var.set(deck_object.status)
                    else:
                        last_update = time.time()
                    time.sleep(deck_object.update_delay)
            except (RuntimeError, AttributeError) as upd_view_err:
                print(upd_view_err)

        @staticmethod
        def reset_view(deck_object):
            deck_object.time_label_var.set("")
            deck_object.duration_label_var.set("")
            deck_object.file_path_label_var.set("")
            deck_object.artist_label_var.set("")
            deck_object.title_label_var.set("")
            deck_object.vol_image = deck_object.get_volume_image()
            deck_object.volume_display.configure(image=deck_object.vol_image)
            deck_object.status_label_var.set(deck_object.status)

        @staticmethod
        def get_time_pos(time_in=None):
            if time_in is None:
                return None
            secs = int(float(time_in))
            time_string = time.strftime("%H:%M:%S", time.gmtime(secs))
            return time_string

        def get_volume_level(self):
            if len(self.raw_chunk) > 2:
                vol = np.abs(np.frombuffer(self.raw_chunk, dtype=np.int16)).max()
                return vol
            else:
                return 0

        @staticmethod
        def create_volume_image():
            vol_image = np.zeros((10, 2, 3), dtype=np.int8)
            vol_image[-1, :, 1] = 255
            vol_image = Image.fromarray(vol_image, "RGB").resize((10, 70))
            return ImageTk.PhotoImage(vol_image)

        @staticmethod
        def get_volume_image(vol_value=None):
            v_size = 15
            new_image = np.zeros((v_size, 2, 3), dtype=np.int8)
            if vol_value is not None:
                start_index = int((vol_value / 32767) * v_size) * -1
                start_index += v_size
                start_index = abs(start_index)
                start_index = min(start_index, v_size - 1)
            else:
                vol_image = Image.fromarray(new_image, "RGB").resize((10, 70))
                return ImageTk.PhotoImage(vol_image)
            for v in range(start_index, v_size):
                new_image[v, :, 0] = 255 // (v+1)
                new_image[v, :, 1] = ((255 // (v + 1)) * -1) + 255
            vol_image = Image.fromarray(new_image, "RGB").resize((10, 70))
            return ImageTk.PhotoImage(vol_image)

    class QueueWindow:
        def __init__(self, root):
            self.font = ("helvetica", 10)
            self.root = root
            self.queue_frame = tk.Frame(self.root, width=680, height=180, bd=10, relief="ridge")
            self.queue_window = scrolledtext.ScrolledText(self.queue_frame, font=self.font, wrap=tk.WORD,
                                                          state="disabled")
            self.queue_window.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        def refresh(self):
            self.queue_window.configure(state="normal")
            self.queue_window.delete(0.0, tk.END)
            for path in self.root.queue_list:
                self.queue_window.insert(tk.END, path + "\n")
            self.queue_window.configure(state="disabled")
            self.queue_window.see(0.0)

    class LogWindow:
        def __init__(self, root):
            self.max_log_length = 500
            self.font = ("helvetica", 10)
            self.root = root
            self.log_frame = tk.Frame(self.root, width=680, height=140, bd=10, relief="ridge")
            self.log_window = scrolledtext.ScrolledText(self.log_frame, font=self.font, wrap=tk.WORD, state="disabled")
            self.log_window.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        def log_window_update(self, entry=None):

            if entry is None:
                return
            self.log_window.configure(state="normal")
            self.log_window.insert(tk.END, entry + "\n")
            log_text_raw = self.log_window.get(0.0, tk.END)
            log_text = log_text_raw.split("\n")
            if len(log_text) > self.max_log_length + 2:
                self.log_window.delete(0.0, 2.0)
            self.log_window.configure(state="disabled")
            self.log_window.see(tk.END)


if __name__ == "__main__":
    app_window = MainWindow()
    app_window.run_app()
