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
    def __init__(self, no_repeat_time=180):
        super(MainWindow, self).__init__()
        self.title("Lion Music Scheduler 2.0")
        self.update_delay = 0.1
        self.canvas = tk.Canvas(self, width=799, height=549, bg="#555555")
        self.canvas.pack()
        self.resizable(width=False, height=False)
        self.all_decks = []
        self.available_decks = []
        self.master_volume = 1.0
        self.chunk_size = 4096
        self.deckA = self.PlayerDeck(self, "A")
        self.deckB = self.PlayerDeck(self, "B")
        self.deckA.deck_frame.place(x=10, y=10)
        self.deckB.deck_frame.place(x=405, y=10)
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
        self.encoder1_options = self.select_encoder(1)
        self.encoder1_status_label = tk.Button(self, font=self.font, text="Stream1", command=self.encoder1_options)
        self.encoder1_status_label.place(x=600, y=135, width=60, height=20)
        self.encoder1_indicator = tk.Label(self, bg="#000000")
        self.encoder1_indicator.place(x=665, y=135, width=20, height=20)
        self.encoder2_options = self.select_encoder(2)
        self.encoder2_status_label = tk.Button(self, font=self.font, text="Stream2", command=self.encoder2_options)
        self.encoder2_status_label.place(x=690, y=135, width=60, height=20)
        self.encoder2_indicator = tk.Label(self, bg="#000000")
        self.encoder2_indicator.place(x=755, y=135, width=20, height=20)
        self.encoder_indicators = {"enc1": self.encoder1_indicator, "enc2": self.encoder2_indicator}
        self.encoder_buffer = {"A": [], "B": []}
        self.encoder_threads = {}
        self.queue_window = self.QueueWindow(self)
        self.queue_window.queue_frame.place(x=10, y=160)
        self.log_window = self.LogWindow(self)
        self.log_window.log_frame.place(x=10, y=390)
        self.encoder_options_window = self.EncoderWindow(self)
        self.encoder_options_window.encoder_frame.place(anchor="center", relx=0.5, rely=0.5)
        self.queue_list = []
        self.valid_exts = [".mp3", ".wav", ".ogg", ".wma", ".flac"]
        self.ignored_exts = [".jpg", ".JPG", ".txt", ".url", ".ini"]
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
                try:
                    del self.played_dict[path][file]
                except KeyError:
                    print(item, "not found in played_dict")
        self.queue_window.refresh()

    def select_encoder(self, enc):
        def open_encoder_options():
            if not self.encoder_options_window.is_visible:
                self.encoder_options_window.open_options(enc)
        return open_encoder_options

    def load_from_queue(self, path, deck_object=None):
        self.queue_window.refresh()
        if deck_object is None:
            deck_object = self.deckA if self.deckA.status == "stopped" else self.deckB
        deck_object.song_type = "stream" if path.startswith("http") else "file"
        info_string = "deck{}: {}".format(deck_object.deck_id, path)
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

    def process_schedule(self):
        while self.deckA.running and self.deckB.running:
            process_time = time.time()
            total_added = 0
            do_immediate = False
            current_group = []
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
                                    self.log_window.log_window_update("new schedule group: {}".format(details[:4]))
                                    current_group = details[:4]
                                    if entry_name != "any" and entry_name != "none":
                                        self.sched_name = entry_name
                                    if "clear" in entry_options:
                                        self.queue_list = []
                                    if entry_top != "none":
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
                if do_immediate is True:
                    for d in self.all_decks:
                        if d.status == "playing" or d.status == "loading":
                            d.status = "ending"
                            ending_timer = Timer(d.fade_out_time - self.update_delay, self.deck_reset, args=[d])
                            ending_timer.start()
                            break
                    else:
                        print("could not process 'immediate' option for", current_group)
                self.queue_window.refresh()
                if len(self.available_decks) >= 2 and self.initialize is False:
                    print("queue used auto recover because no decks were playing")
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
            elif file[index:] not in self.ignored_exts:
                print(file, "does not have a recognised extension")
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
                    time.sleep(2)
                    continue
                for deck_object in self.all_decks:
                    if deck_object.status == "playing" or deck_object.status == "loading":
                        if deck_object in self.available_decks:
                            self.available_decks.remove(deck_object)
                        if deck_object.song_type == "stream":
                            file_path = deck_object.song_file_path
                            if file_path == "":
                                print("resetting deck{} - no file path".format(deck_object.deck_id))
                                deck_object.status = "ending"
                                ending_timer = Timer(2, self.deck_reset, args=[deck_object])
                                ending_timer.start()
                        elif deck_object.song_type == "file":
                            if deck_object.remaining < deck_object.fade_out_time and deck_object.status != "ending":
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
                                if len(self.queue_list) > 0 and len(self.available_decks) > 0:
                                    self.load_from_queue(self.queue_list.pop(0), self.available_decks.pop(0))
                                break
                    if deck_object.status == "stopped" and deck_object not in self.available_decks:
                        self.available_decks.append(deck_object)
                sleep_time = 1 + (0.5 - (process_time % 1))
                if sleep_time > 0.0:
                    time.sleep(sleep_time)

    def deck_reset(self, deck_object):
        deck_object.status = "stopped"
        if deck_object not in self.available_decks:
            self.available_decks.append(deck_object)
        deck_object.song_type = ""
        deck_object.song_file_path = ""
        deck_object.song_artist = ""
        deck_object.song_title = ""
        deck_object.volume = self.master_volume
        deck_object.duration = 0
        deck_object.remaining = 9999
        deck_object.raw_chunk = bytes(deck_object.chunk_size)
        deck_object.reset_view()

    def process_encoders(self):
        feed_thread = Thread(name="encoder_feed_thread", target=self.feeder_thread, daemon=True)
        feed_thread.start()
        last_title_a = ""
        last_title_b = ""
        while self.deckA.running or self.deckB.running:
            time.sleep(5)
            for key in self.encoder_options_window.encoder_dict:
                if self.encoder_options_window.encoder_dict[key]["enabled"] == 1:
                    if key in self.encoder_threads:
                        if self.encoder_threads[key].poll() is None:
                            self.encoder_indicators[key].configure(bg="#00FF00")
                            if self.deckA.status == "playing" and self.deckA.song_title != last_title_a:
                                last_title_a = self.deckA.song_title
                                info = {"artist": self.deckA.song_artist, "title": self.deckA.song_title}
                                self.send_metadata(key, info)
                            elif self.deckB.status == "playing" and self.deckB.song_title != last_title_b:
                                last_title_b = self.deckB.song_title
                                info = {"artist": self.deckB.song_artist, "title": self.deckB.song_title}
                                self.send_metadata(key, info)
                        else:
                            print("Stream{} lost connection".format(key[-1]))
                            self.encoder_threads[key].kill()
                            del self.encoder_threads[key]
                            self.encoder_indicators[key].configure(bg="#FF0000")
                    else:
                        self.encoder_indicators[key].configure(bg="#FFFF00")
                        user_pass = self.encoder_options_window.encoder_dict[key]["user:pass"]
                        url = self.encoder_options_window.encoder_dict[key]["url"]
                        port = self.encoder_options_window.encoder_dict[key]["port"]
                        brate = self.encoder_options_window.encoder_dict[key]["bitrate"]
                        chls = self.encoder_options_window.encoder_dict[key]["channels"]
                        chls = "1" if chls == "mono" else "2"
                        mount = self.encoder_options_window.encoder_dict[key]["mount"]
                        end_point = "icecast://{}@{}:{}/{}".format(user_pass, url, port, mount)
                        enc_proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-f", "s16le", "-ac", "2", "-i", "pipe:",
                                                     "-f", "mp3", "-ar", "44100", "-ab", brate, "-ac", chls, end_point],
                                                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                        enc_proc.stdin.write(bytes(self.chunk_size * 100))
                        self.encoder_threads[key] = enc_proc
                else:
                    if key in self.encoder_threads:
                        self.encoder_threads[key].kill()
                        del self.encoder_threads[key]
                    self.encoder_indicators[key].configure(bg="#000000")

    def send_metadata(self, key, info):
        data = info["artist"] + " - " + info["title"]
        data = data.replace("&", "%26")
        this_dict = self.encoder_options_window.encoder_dict[key]
        url1 = "http://{}@{}:{}".format(this_dict["user:pass"], this_dict["url"], this_dict["port"])
        url2 = "/admin/metadata?mount=/{}&mode=updinfo&song=".format(this_dict["mount"])
        url2 += data
        url = url1 + url2
        requests.get(url)

    def feeder_thread(self):
        while self.deckA.running or self.deckB.running:
            length_a = len(self.encoder_buffer["A"])
            length_b = len(self.encoder_buffer["B"])
            if (length_a == 0 and length_b == 0) or self.encoder_threads == {}:
                time.sleep(1)
                continue
            elif length_a == 0 or length_b == 0:
                loops = max(length_a, length_b)
            else:
                loops = min(length_a, length_b)
            if length_a == 0:
                buffer_a = [bytes(self.chunk_size) for _ in range(loops)]
            else:
                buffer_a = [self.encoder_buffer["A"].pop(0) for _ in range(loops)]
            if length_b == 0:
                buffer_b = [bytes(self.chunk_size) for _ in range(loops)]
            else:
                buffer_b = [self.encoder_buffer["B"].pop(0) for _ in range(loops)]
            for _ in range(loops):
                chunk1 = np.frombuffer(buffer_a.pop(0), dtype=np.int16)
                if len(chunk1) < self.chunk_size // 2:
                    chunk1 = np.append(chunk1, [0 for _ in range((self.chunk_size // 2) - len(chunk1))])
                chunk2 = np.frombuffer(buffer_b.pop(0), dtype=np.int16)
                if len(chunk2) < self.chunk_size // 2:
                    chunk2 = np.append(chunk2, [0 for _ in range((self.chunk_size // 2) - len(chunk2))])
                result = np.add(chunk1, chunk2, dtype=np.int32)
                result = np.array(np.clip(result, -32768, 32767)).astype(np.int16)
                result = result.tobytes()
                for enc in self.encoder_threads:
                    enc_proc = self.encoder_threads[enc]
                    if enc_proc.poll() is None:
                        try:
                            enc_proc.stdin.write(result)
                        except BrokenPipeError:
                            print("waiting for", enc)
                            time.sleep(1)
            time.sleep(0.5)

    def run_app(self):
        print("app starting")
        thread = Thread(name="schedule_thread", target=self.process_schedule, daemon=True)
        thread.start()
        print("schedule thread started")
        thread = Thread(name="deck_manage_thread", target=self.process_decks, daemon=True)
        thread.start()
        print("deck management thread started")
        thread = Thread(name="encoder_manage_thread", target=self.process_encoders, daemon=True)
        thread.start()
        print("encoder management thread started")
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
            self.width = 385
            self.height = 120
            self.font = ("helvetica", 10)
            self.stream_input_buffer_size = 1024
            self.song_artist = ""
            self.song_title = ""
            self.song_file_path = ""
            self.song_type = ""
            self.sample_rate = 44100
            self.channels = 2
            self.duration = 0
            self.remaining = 9999
            self.song_start_time = -1
            self.status = "stopped"
            self.running = True
            self.update_delay = root.update_delay
            self.root = root
            self.deck_id = deck_id

            # pyaudio and audioread creation for reading files only
            self.chunk_size = root.chunk_size
            self.port_audio = pyaudio.PyAudio()
            self.audio_out = None
            self.create_audio_out_stream()
            self.file_stream = []
            self.raw_chunk = bytes(self.chunk_size)
            self.volume = self.root.master_volume
            self.fade_out_decay = 0.0045
            self.fade_out_time = 6

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

            # Remaining Label
            self.remaining_label_var = tk.StringVar()
            self.remaining_label_var.set("00:00:00")
            self.remaining_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                            textvariable=self.remaining_label_var)
            self.remaining_label.place(anchor="ne", x=200, y=10, width=60, height=14)

            # Duration Label
            self.duration_label_var = tk.StringVar()
            self.duration_label_var.set("00:00:00")
            self.duration_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                           textvariable=self.duration_label_var)
            self.duration_label.place(anchor="ne", x=325, y=10, width=60, height=14)

            # Artist Label
            self.artist_label_var = tk.StringVar()
            self.artist_label_var.set(self.song_artist)
            self.artist_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF", anchor="w",
                                         textvariable=self.artist_label_var)
            self.artist_label.place(x=5, y=25, width=320, height=14)

            # Title Label
            self.title_label_var = tk.StringVar()
            self.title_label_var.set(self.song_title)
            self.title_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF", anchor="w",
                                        textvariable=self.title_label_var)
            self.title_label.place(x=5, y=40, width=320, height=14)

            # File Path Label
            self.file_path_label_var = tk.StringVar()
            self.file_path_label_var.set(self.song_file_path)
            self.file_path_label = tk.Label(self.deck_frame, font=self.font, bg="#555555", fg="#FFFFFF", anchor="w",
                                            textvariable=self.file_path_label_var)
            self.file_path_label.place(x=5, y=55, width=320, height=14)

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

            # Next Button
            self.next_button = tk.Button(self.deck_frame, font=self.font, text="Next", command=self.next_in_queue)
            self.next_button.place(anchor="center", x=250, y=85, width=50, height=20)

            update_thread = Thread(name="deck"+self.deck_id+" update_view_thread",
                                   target=self.update_view, args=[self], daemon=True)
            update_thread.start()

        def play_stream(self, path):
            self.file_stream = []
            self.status = "loading"

            headers = {"user-agent": "Lion Broadcaster 2.0", "Icy-MetaData": "1"}
            try:
                resp = requests.get(path, headers=headers, stream=True)
            except requests.exceptions.ConnectionError:
                print("Could not connect to", path)
                self.root.deck_reset(self)
                return
            if resp.status_code != 200:
                print("server returned", resp.status_code)
                resp.close()
                self.root.deck_reset(self)
                return
            elif "icy-name" in resp.headers.keys():
                self.song_artist = resp.headers["icy-name"]
            metaint_header = "icy-metaint"
            if metaint_header in resp.headers.keys():
                metaint_value = int(resp.headers[metaint_header])
            else:
                metaint_value = 0
            self.duration = 0
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
                    while len(self.file_stream) > self.stream_input_buffer_size:
                        time.sleep(0.005)
                        if self.status == "stopped":
                            raise StopIteration
                    for _ in range(metaint_value if metaint_value > 0 else 1):
                        stream_output += next(data)
                        if len(stream_output) == self.stream_input_buffer_size:
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
                    if self.status == "playing":
                        print("deck{} lost connection to {}".format(self.deck_id, path))
                        self.song_file_path = ""
            ff_proc.kill()
            resp.close()
            stdout_thread.join()
            stderr_thread.join()

        def read_stdout(self, out):
            while self.status != "stopped":
                self.file_stream.append(out.read(self.chunk_size))
                if len(self.file_stream) > self.stream_input_buffer_size and self.status == "loading":
                    self.status = "playing"

        def read_stderr(self, err):
            while self.status != "stopped":
                err.readline().decode().rstrip("\n")

        def load_audio_file(self, path=None):
            if path is None:
                return False
            self.file_stream = []
            self.status = "loading"
            try:
                self.song_artist = self.get_ffprobe_info(path, "artist")
                self.song_title = self.get_ffprobe_info(path, "title")
                self.duration = float(self.get_ffprobe_info(path, "duration"))
                ff_proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-i", path, "-f", "s16le", "-ar",
                                            str(self.sample_rate), "-ac", str(self.channels), "pipe:"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                timer = Timer(5, self.process_killer, args=[ff_proc, path])
                timer.start()
                done = False
                loaded_chunks = 0
                while done is False:
                    buf = ff_proc.stdout.read(self.chunk_size)
                    if len(buf) == 0:
                        done = True
                    else:
                        self.file_stream.append(buf)
                        loaded_chunks += 1
                        if self.status == "loading" and loaded_chunks > 25:
                            self.status = "playing"
                timer.cancel()
                adj_time = ((loaded_chunks * self.chunk_size) / self.sample_rate) / 4

            except Exception as e:
                print("while trying to load audio file, the following happened...")
                print(e)
                self.status = "stopped"
                return False
            else:
                if int(adj_time) < int(self.duration):
                    print("{} - length ({}) differs from metadata ({})".format(path, int(adj_time), int(self.duration)))
                    self.duration = adj_time
                return True

        @staticmethod
        def process_killer(proc, path):
            print(path, "took too long to load")
            proc.kill()

        def create_audio_out_stream(self):
            if self.audio_out is not None:
                self.audio_out.close()
            self.audio_out = self.port_audio.open(format=pyaudio.paInt16, channels=self.channels,
                                                  rate=self.sample_rate, output=True,
                                                  frames_per_buffer=self.chunk_size)

        @staticmethod
        def get_ffprobe_info(path=None, tag=None):
            if path is None or tag is None:
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
                        processed_chunk = self.file_stream.pop(0)
                        if len(processed_chunk) == 0:
                            print("deck{} audio chunk size was 0".format(self.deck_id))
                            processed_chunk = bytes(self.chunk_size)
                        # adjust volume is necessary
                        if self.status == "ending":
                            self.volume -= self.fade_out_decay if self.volume - self.fade_out_decay >= 0 else 0
                        if self.volume != 1.0:
                            processed_chunk = np.frombuffer(processed_chunk, dtype=np.int16) * self.volume
                            processed_chunk = np.array(processed_chunk, dtype=np.int16)
                            processed_chunk = processed_chunk.tobytes()
                        # write to pyaudio
                        self.raw_chunk = processed_chunk
                        self.audio_out.write(processed_chunk)
                        try:
                            if len(self.root.encoder_threads) != 0:
                                self.root.encoder_buffer[self.deck_id].append(processed_chunk)
                        except AttributeError:
                            print("encoder buffer {} not found when writing data".format(self.deck_id))
                else:
                    # write silence if not playing to avoid buffer under run
                    self.raw_chunk = bytes(self.chunk_size)
                    self.audio_out.write(self.raw_chunk)

        def next_in_queue(self):
            if self.status == "playing":
                self.status = "ending"
                thread = Timer(self.fade_out_time, self.root.deck_reset, args=[self])
                thread.start()

        @staticmethod
        def update_view(deck_obj):
            try:
                last_update = time.time()
                last_volume = 0
                while deck_obj.running is True:
                    if deck_obj.status == "playing" or deck_obj.status == "ending":
                        if len(deck_obj.raw_chunk) == 0:
                            vol_level = 0
                        else:
                            vol_level = np.frombuffer(deck_obj.raw_chunk, dtype=np.int16).max()
                        if vol_level < last_volume:
                            vol_level = last_volume - 2000
                        last_volume = vol_level
                        deck_obj.vol_image = deck_obj.get_volume_image(vol_level)
                        deck_obj.volume_display.configure(image=deck_obj.vol_image)
                        if time.time() - last_update > 1:
                            last_update = time.time()
                            # update song file path
                            if deck_obj.file_path_label_var.get() != deck_obj.song_file_path:
                                deck_obj.file_path_label_var.set(deck_obj.song_file_path)
                            # update current and remaining time and duration
                            time_string = deck_obj.get_time_pos(time.time() - deck_obj.song_start_time)
                            if deck_obj.status != "stopped" and time_string != deck_obj.time_label_var.get():
                                deck_obj.time_label_var.set(time_string)
                            duration_string = deck_obj.get_time_pos(deck_obj.duration)
                            if deck_obj.status != "stopped" and duration_string != deck_obj.duration_label_var.get():
                                deck_obj.duration_label_var.set(duration_string)
                            if deck_obj.song_type == "file":
                                deck_obj.remaining = (deck_obj.song_start_time + deck_obj.duration) - time.time() + 1
                                remaining_string = deck_obj.get_time_pos(deck_obj.remaining)
                                if remaining_string != deck_obj.remaining_label_var.get():
                                    deck_obj.remaining_label_var.set(remaining_string)
                            # update song artist
                            if deck_obj.artist_label_var.get() != deck_obj.song_artist:
                                deck_obj.artist_label_var.set(deck_obj.song_artist)
                            # update song title
                            if deck_obj.title_label_var.get() != deck_obj.song_title:
                                deck_obj.title_label_var.set(deck_obj.song_title)
                            # update deck status
                            if deck_obj.status_label_var.get() != deck_obj.status:
                                deck_obj.status_label_var.set(deck_obj.status)
                    else:
                        last_update = time.time()
                    time.sleep(deck_obj.update_delay)
            except (RuntimeError, AttributeError) as upd_view_err:
                print(upd_view_err)

        def reset_view(self):
            self.time_label_var.set("")
            self.remaining_label_var.set("")
            self.duration_label_var.set("")
            self.file_path_label_var.set("")
            self.artist_label_var.set("")
            self.title_label_var.set("")
            self.vol_image = self.get_volume_image()
            self.volume_display.configure(image=self.vol_image)
            self.status_label_var.set(self.status)

        @staticmethod
        def get_time_pos(time_in=None):
            if time_in is None:
                return None
            secs = int(float(time_in))
            time_string = time.strftime("%H:%M:%S", time.gmtime(secs))
            return time_string

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

    class EncoderWindow:
        def __init__(self, root):
            self.font = ("helvetica", 10)
            self.root = root
            try:
                self.encoder_dict = {}
                with open("encoders.cfg") as file:
                    entries = file.readlines()
                    for i, entry in enumerate(entries):
                        entry = entry.strip("\n")
                        result = entry.split(sep="::")
                        enc_id = "enc"+str(i+1)
                        self.encoder_dict[enc_id] = {"enabled": int(result[0]), "user:pass": result[1],
                                                     "url": result[2], "port": result[3], "bitrate": result[4],
                                                     "channels": result[5], "mount": result[6]}
            except (FileNotFoundError, IOError):
                self.encoder_dict = {"enc1": {"enabled": 0, "user:pass": "user:pass",
                                              "url": "127.0.0.1", "port": "8000", "bitrate": "64k",
                                              "channels": "stereo", "mount": "stream"},
                                     "enc2": {"enabled": 0, "user:pass": "user:pass",
                                              "url": "127.0.0.1", "port": "9000", "bitrate": "64k",
                                              "channels": "stereo", "mount": "stream"},
                                     }
            self.selected_encoder = "enc1"
            self.encoder_enable_var = tk.IntVar()
            self.encoder_user_var = tk.StringVar()
            self.encoder_url_var = tk.StringVar()
            self.encoder_port_var = tk.StringVar()
            self.encoder_mount_var = tk.StringVar()
            self.encoder_frame = tk.Frame(self.root, width=300, height=300, bd=10, relief="ridge")
            self.encoder_frame.lower()
            self.is_visible = False
            self.encoder_enable_label = tk.Label(self.encoder_frame, font=self.font, text="Enabled")
            self.encoder_enable_label.place(x=10, y=15)
            self.encoder_enabled = tk.Checkbutton(self.encoder_frame, font=self.font, variable=self.encoder_enable_var)
            self.encoder_enabled.place(x=100, y=15)
            self.encoder_user_label = tk.Label(self.encoder_frame, font=self.font, text="User:Pass")
            self.encoder_user_label.place(x=10, y=55)
            self.encoder_user_input = tk.Entry(self.encoder_frame, font=self.font, textvariable=self.encoder_user_var)
            self.encoder_user_input.place(x=100, y=55, width=150)
            self.encoder_url_label = tk.Label(self.encoder_frame, font=self.font, text="Server URL")
            self.encoder_url_label.place(x=10, y=95)
            self.encoder_url_input = tk.Entry(self.encoder_frame, font=self.font, textvariable=self.encoder_url_var)
            self.encoder_url_input.place(x=100, y=95, width=150)
            self.encoder_port_label = tk.Label(self.encoder_frame, font=self.font, text="Server Port")
            self.encoder_port_label.place(x=10, y=135)
            self.encoder_port_input = tk.Entry(self.encoder_frame, font=self.font, textvariable=self.encoder_port_var)
            self.encoder_port_input.place(x=100, y=135, width=50)
            self.encoder_bitrate_label = tk.Label(self.encoder_frame, font=self.font, text="Bitrate")
            self.encoder_bitrate_label.place(x=10, y=175)
            self.bitrate_options = ["32k", "64k", "96k", "128k", "192k", "320k"]
            self.encoder_bitrate = tk.StringVar()
            self.encoder_bitrate.set(self.bitrate_options[0])
            self.encoder_bitrate_list = tk.OptionMenu(self.encoder_frame, self.encoder_bitrate, *self.bitrate_options)
            self.encoder_bitrate_list.place(x=65, y=170, width=65)
            self.encoder_channels_label = tk.Label(self.encoder_frame, font=self.font, text="Channels")
            self.encoder_channels_label.place(x=135, y=175)
            self.channel_options = ["mono", "stereo"]
            self.encoder_channels = tk.StringVar()
            self.encoder_channels.set(self.channel_options[0])
            self.encoder_channels_list = tk.OptionMenu(self.encoder_frame, self.encoder_channels, *self.channel_options)
            self.encoder_channels_list.place(x=200, y=170, width=75)
            self.encoder_mount_label = tk.Label(self.encoder_frame, font=self.font, text="Mount Point")
            self.encoder_mount_label.place(x=10, y=210)
            self.encoder_mount_input = tk.Entry(self.encoder_frame, font=self.font, textvariable=self.encoder_mount_var)
            self.encoder_mount_input.place(x=100, y=210, width=150)
            self.encoder_button = tk.Button(self.encoder_frame, font=self.font, text="OK", command=self.close_options)
            self.encoder_button.place(anchor="center", relx=0.5, y=260)

        def open_options(self, enc):
            self.encoder_frame.lift()
            self.is_visible = True
            enc_id = "enc1" if enc == 1 else "enc2"
            self.selected_encoder = enc_id
            self.encoder_enable_var.set(self.encoder_dict[enc_id]["enabled"])
            self.encoder_user_var.set(self.encoder_dict[enc_id]["user:pass"])
            self.encoder_url_var.set(self.encoder_dict[enc_id]["url"])
            self.encoder_port_var.set(self.encoder_dict[enc_id]["port"])
            self.encoder_bitrate.set(self.encoder_dict[enc_id]["bitrate"])
            self.encoder_channels.set(self.encoder_dict[enc_id]["channels"])
            self.encoder_mount_var.set(self.encoder_dict[enc_id]["mount"])

        def close_options(self):
            self.encoder_frame.lower()
            self.is_visible = False
            self.encoder_dict[self.selected_encoder]["enabled"] = self.encoder_enable_var.get()
            self.encoder_dict[self.selected_encoder]["user:pass"] = self.encoder_user_var.get()
            self.encoder_dict[self.selected_encoder]["url"] = self.encoder_url_var.get()
            self.encoder_dict[self.selected_encoder]["port"] = self.encoder_port_var.get()
            self.encoder_dict[self.selected_encoder]["bitrate"] = self.encoder_bitrate.get()
            self.encoder_dict[self.selected_encoder]["channels"] = self.encoder_channels.get()
            self.encoder_dict[self.selected_encoder]["mount"] = self.encoder_mount_var.get()
            self.save_options()

        def save_options(self):
            with open("encoders.cfg", "w") as file:
                for key in self.encoder_dict:
                    entry = self.encoder_dict[key]
                    file.write("{}::{}::{}::{}::{}::{}::{}\n".format(entry["enabled"], entry["user:pass"], entry["url"],
                                                                     entry["port"], entry["bitrate"], entry["channels"],
                                                                     entry["mount"]))

    class QueueWindow:
        def __init__(self, root):
            self.font = ("helvetica", 10)
            self.root = root
            self.queue_frame = tk.Frame(self.root, width=780, height=220, bd=10, relief="ridge")
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
            self.max_log_length = 200
            self.font = ("helvetica", 10)
            self.root = root
            self.log_frame = tk.Frame(self.root, width=780, height=150, bd=10, relief="ridge")
            self.log_window = scrolledtext.ScrolledText(self.log_frame, font=self.font, wrap=tk.WORD, state="disabled")
            self.log_window.place(x=0, y=0, relwidth=1.0, relheight=1.0)
            self.log_window_update("BEGIN LOGGING")

        def log_window_update(self, entry=None):

            if entry is None:
                return
            self.log_window.configure(state="normal")
            log_text_raw = self.log_window.get(0.0, tk.END)
            log_text = log_text_raw.split("\n")
            self.log_window.insert(tk.END, entry + "\n")
            if len(log_text) > self.max_log_length + 2:
                self.log_window.delete(0.0, 2.0)
            self.log_window.configure(state="disabled")
            self.log_window.see(tk.END)


if __name__ == "__main__":
    app_window = MainWindow()
    app_window.run_app()
