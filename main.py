import os
import random
import struct
from threading import Thread, Timer
import time
import tkinter as tk
from tkinter import scrolledtext
import subprocess
import mplayer
import numpy as np
from PIL import ImageTk, Image


class MainWindow(tk.Tk):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.title("Play out GUI")
        self.update_delay = 0.1
        self.canvas = tk.Canvas(self, width=700, height=500, bg="#555555")
        self.canvas.pack()
        self.all_decks = []
        self.available_decks = []
        self.valid_exts = [".mp3", ".wav", ".ogg", ".wma", ".flac"]
        self.deckA = self.PlayerDeck(self, "A")
        self.deckB = self.PlayerDeck(self, "B")
        self.deckA.deck_frame.place(x=10, y=10)
        self.deckB.deck_frame.place(x=355, y=10)
        self.queue_window = self.QueueWindow(self)
        self.queue_window.queue_frame.place(x=10, y=140)
        self.log_window = self.LogWindow(self)
        self.log_window.log_frame.place(x=10, y=350)
        self.queue_list = []
        self.sched_name = None
        self.initialize = True

    def load_song(self, path, deck_object=None):
        if deck_object is None:
            deck_object = self.deckA if self.deckA.status == "stopped" else self.deckB
        deck_object.song_type = "stream" if path.startswith("http") else "file"
        print("deck{} LOAD: {}".format(deck_object.deck_id, path))
        self.log_window.update("deck{} LOAD: {}".format(deck_object.deck_id, path))
        deck_object.song_file_path = path
        deck_object.run_command("loadfile", path)
        if deck_object in self.available_decks:
            self.available_decks.remove(deck_object)
        self.queue_window.refresh()
        status_thread = Thread(name="deck"+deck_object.deck_id+" get_status_thread",
                               target=self.get_deck_status_threaded, args=[deck_object])
        status_thread.start()

    @staticmethod
    def get_deck_status_threaded(deck_object):
        timeout = 6
        timer_start = time.time()
        print("deck{} {} => loading".format(deck_object.deck_id, deck_object.status))
        deck_object.status = "loading"
        new_status = "loading"
        while time.time() - timer_start < timeout and deck_object.running is True:
            if deck_object.status != "loading":
                return
            status = deck_object.run_command("get_property", "pause")
            if status is not None:
                if status == "yes":
                    new_status = "paused"
                    break
                elif status == "no":
                    current_path = deck_object.run_command("get_property", "path")
                    if current_path != "(null)":
                        new_status = "playing"
                        break
                    else:
                        new_status = "stopped"
                        break
            time.sleep(0.5)
        if deck_object.status != "loading":
            return
        elif new_status == "loading":
            print("deck{} is stuck. resetting".format(deck_object.deck_id))
            deck_object.status = "stuck"
        elif new_status == "paused":
            print("deck{} is paused".format(deck_object.deck_id))
            deck_object.status = "paused"
        elif new_status == "playing":
            print("deck{} is playing".format(deck_object.deck_id))
            deck_object.status = "playing"
        elif new_status == "stopped":
            print("deck{} is stopped".format(deck_object.deck_id))
            deck_object.status = "stopped"

    def app_loop(self):
        print("app loop started")
        self.log_window.update("app loop started")
        # manage queue
        while self.deckA.running is True and self.deckB.running is True:

            # read schedule and manage queue list
            self.process_schedule()
            if len(self.queue_list) == 0:
                print("QUEUE LIST IS EMPTY. NO DECK MANAGEMENT POSSIBLE")
                time.sleep(2)
                continue

            # manage decks
            self.process_decks()
            time.sleep(0.8)

    def process_schedule(self):
        start_time = time.time()
        total_added = 0
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
                                self.log_window.update("new schedule group: {}".format(details[:4]))
                                print("using queue options = ", entry_options)
                                self.sched_name = entry_name
                                if "clear" in entry_options:
                                    print("queue_list was cleared")
                                    self.queue_list = []
                                if entry_top != "none":
                                    print("added show top:", entry_top)
                                    new_items.append(entry_top)
                                    total_added += 1
                                if "immediate" in entry_options:
                                    for d in self.all_decks:
                                        if d.status == "playing" or d.status == "loading":
                                            d.status = "ending"
                                            # TODO: dont hardcode the 5 sec wait time below
                                            ending_timer = Timer(5 - self.update_delay, self.deck_reset, args=[d])
                                            ending_timer.start()
                                            break
                                    else:
                                        print("could not process 'immediate' option")
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
            print("added {} to queue. took {} sec(s)".format(total_added, round(time.time() - start_time, 3)))
            print("current queue_length", len(self.queue_list))
            self.queue_window.refresh()
            if len(self.available_decks) == 2 and self.initialize is False:
                self.load_song(self.queue_list.pop(0), self.available_decks.pop(0))

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
            self.log_window.update("directory {} not found".format(path))
            return None
        choices = []
        for file in full_list:
            index = file.rfind(".")
            if file[index:] in self.valid_exts:
                choices.append(file)
        if len(choices) > 0:
            return "'" + path + random.choice(choices) + "'"
        else:
            print("no valid files found in {}".format(path))
            self.log_window.update("no valid files found in {}".format(path))
            return None

    def process_decks(self):
        if self.initialize:
            self.initialize = False
            time.sleep(1)
            self.load_song(self.queue_list.pop(0), self.available_decks.pop(0))
            self.queue_window.refresh()
        else:
            for deck_object in self.all_decks:
                file_path = deck_object.run_command("get_property", "path")
                if deck_object.status == "paused":
                    self.deck_reset(deck_object)
                if deck_object.status == "playing":
                    if deck_object in self.available_decks:
                        self.available_decks.remove(deck_object)
                    pos = deck_object.run_command("get_property", "time_pos")
                    pos = float(pos) if pos is not None else None
                    if file_path == "(null)":
                        print("resetting deck{} - no file path".format(deck_object.deck_id))
                        self.deck_reset(deck_object)
                        self.load_song(self.queue_list.pop(0))
                        continue
                    if deck_object.song_type == "file":
                        length = deck_object.run_command("get_property", "length")
                        length = float(length) if length is not None else None
                    else:
                        length = None
                    if pos is not None and length is not None:
                        remaining = length - pos
                        # TODO: dont hardcode the 5 sec wait time below
                        if remaining < 5 and deck_object.status != "ending":
                            print("deck{} {} => ending".format(deck_object.deck_id,  deck_object.status))
                            deck_object.status = "ending"
                            ending_timer = Timer(remaining - self.update_delay, self.deck_reset, args=[deck_object])
                            ending_timer.start()
                    if pos is None and file_path is None:
                        deck_object.status = "stuck"
                if deck_object.status == "ending":
                    for d in self.all_decks:
                        if deck_object.deck_id == d.deck_id:
                            continue
                        elif d.status == "playing" or d.status == "loading" \
                                or d.status == "ending" or d.status == "paused":
                            break
                        else:
                            print("deck{} ending. loading another deck".format(deck_object.deck_id))
                            self.log_window.update("deck{} ending-queue {} decks {}".format(deck_object.deck_id,
                                                                                            len(self.queue_list),
                                                                                            len(self.available_decks)))
                            self.load_song(self.queue_list.pop(0), self.available_decks.pop(0))
                            break
                if deck_object.status == "stuck":
                    self.deck_reset(deck_object)
                    self.load_song(self.queue_list.pop(0), self.available_decks.pop(0))

    @staticmethod
    def deck_reset(deck_object):
        deck_object.run_command("stop")
        deck_object.status = "stopped"
        deck_object.song_type = ""
        deck_object.song_file_path = ""
        deck_object.song_artist = ""
        deck_object.song_title = ""
        deck_object.reset_view(deck_object)
        if deck_object not in deck_object.root.available_decks:
            deck_object.root.available_decks.append(deck_object)
        print("deck{} reset".format(deck_object.deck_id))
        deck_object.root.log_window.update("deck{} reset".format(deck_object.deck_id))

    def close_app(self):
        print("app closing")
        self.log_window.update("app closing")
        self.deckA.running = False
        self.deckB.running = False
        self.deckA.status = "quitting"
        self.deckB.status = "quitting"
        self.deckA.audio_player.quit()
        self.deckB.audio_player.quit()
        time.sleep(1)
        self.quit()

    class PlayerDeck:
        def __init__(self, root, deck_id):
            self.width = 335
            self.height = 120
            self.font = ("times", 11)
            self.buffer_size = 512
            self.song_artist = ""
            self.song_title = ""
            self.song_file_path = ""
            self.song_type = ""
            self.status = "stopped"
            self.running = True
            self.update_delay = root.update_delay
            self.last_time_pos = 0.0
            self.root = root

            # Background Frame
            self.deck_frame = tk.Frame(root, width=self.width, height=self.height, bd=10, relief="ridge")

            # Time Label
            self.time_label_var = tk.StringVar()
            self.time_label_var.set("00:00:00")
            self.time_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                       textvariable=self.time_label_var)
            self.time_label.place(anchor="ne", x=280, y=10, width=60, height=14)

            # Artist Label
            self.artist_label_var = tk.StringVar()
            self.artist_label_var.set(self.song_artist)
            self.artist_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                         textvariable=self.artist_label_var)
            self.artist_label.place(x=5, y=25, width=275, height=14)

            # Title Label
            self.title_label_var = tk.StringVar()
            self.title_label_var.set(self.song_title)
            self.title_label = tk.Label(self.deck_frame, font=self.font, bg="#000000", fg="#FFFFFF",
                                        textvariable=self.title_label_var)
            self.title_label.place(x=5, y=40, width=275, height=14)

            # File Path Label
            self.file_path_label_var = tk.StringVar()
            self.file_path_label_var.set(self.song_file_path)
            self.file_path_label = tk.Label(self.deck_frame, font=self.font, bg="#555555", fg="#FFFFFF",
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

            # MPlayer creation
            self.data_file_path = "/tmp/deck"+deck_id
            deck_arg = "-af export="+self.data_file_path+":"+str(self.buffer_size)
            self.deck_id = deck_id
            mplayer.Player._base_args = ('-slave', '-idle', "-quiet")
            self.audio_player = mplayer.Player(args=deck_arg, stderr=subprocess.PIPE, autospawn=True)
            self.audio_player.stdout.connect(self.out_log)
            self.audio_player.stderr.connect(self.err_log)
            self.run_command = self.audio_player._run_command

            # add deck to deck lists
            root.all_decks.append(self)
            root.available_decks.append(self)
            update_thread = Thread(name="deck"+self.deck_id+" update_view_thread",
                                   target=self.update_view, args=[self], daemon=True)
            update_thread.start()

        def out_log(self, data):
            # print("deck{} LOG: {}".format(self.deck_id, data))
            if self.song_type == "stream":
                if data.startswith("Name"):
                    self.song_artist = data[9:]
                elif data.startswith("ICY Info: "):
                    if data[10:].startswith("StreamArtist"):
                        info = data[10:].split("'")
                        self.song_title = info[1]
                    elif data[10:].startswith("StreamTitle"):
                        info = data[10:].split("'")
                        self.song_title = info[1]
            elif self.song_type == "file":
                data = data.strip()
                if data.startswith("Artist"):
                    self.song_artist = data[8:]
                elif data.startswith("Title"):
                    self.song_title = data[7:]

        def err_log(self, data):
            pass
            # print(data)

        @staticmethod
        def update_view(deck_object):
            try:
                last_update = time.time()
                while deck_object.running is True:
                    if deck_object.status == "playing" or deck_object.status == "ending":
                        vol_level = deck_object.get_volume_level() * 1.5
                        deck_object.vol_image = deck_object.get_volume_image(vol_level)
                        deck_object.volume_display.configure(image=deck_object.vol_image)
                        if time.time() - last_update > 1:
                            last_update = time.time()
                            # update song file path
                            if deck_object.file_path_label_var.get() != deck_object.song_file_path:
                                deck_object.file_path_label_var.set(deck_object.song_file_path)
                            # update time
                            time_string = deck_object.get_time_pos(deck_object.run_command("get_property", "time_pos"))
                            if time_string is not None and time_string != deck_object.time_label_var.get():
                                deck_object.time_label_var.set(time_string)
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
            try:
                with open(self.data_file_path, "rb") as f:
                    data = f.read()
                data = data[16:]
                if len(data) > 2:
                    data = struct.unpack(str(int(len(data)/2))+"h", data)
                    data = abs(max(data))
                    return data
                else:
                    return 0
            except (FileNotFoundError, struct.error):
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
            self.font = ("modern", 11)
            self.root = root
            self.queue_frame = tk.Frame(self.root, width=680, height=200, bd=10, relief="ridge")
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
            self.font = ("modern", 11)
            self.root = root
            self.log_frame = tk.Frame(self.root, width=680, height=140, bd=10, relief="ridge")
            self.log_window = scrolledtext.ScrolledText(self.log_frame, font=self.font, wrap=tk.WORD,
                                                        state="disabled")
            self.log_window.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        def update(self, entry=None):

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
    print("app starting")
    app_window = MainWindow()
    thread = Thread(name="app_loop_thread", target=app_window.app_loop, daemon=True)
    thread.start()
    try:
        app_window.mainloop()
    except (KeyboardInterrupt, SystemExit):
        app_window.close_app()
    else:
        app_window.close_app()
