import speech_recognition as sr
import pyttsx3
import time
import random
import os
import re
import ctypes
import threading
import webbrowser
import requests
import pyautogui
import pyperclip
import pygetwindow as gw
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime

try:
    import pywhatkit
except Exception as e:
    pywhatkit = None
    print("pywhatkit not available:", e)

try:
    import wikipedia
except Exception as e:
    wikipedia = None
    print("wikipedia not available:", e)

try:
    import psutil
except Exception as e:
    psutil = None
    print("psutil not available (run: py -3.12 -m pip install psutil):", e)

# ---------- SETTINGS ----------
MODEL = "llama3.2:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"
MAX_HISTORY = 10
BASE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Aeishtrone")
SCREENSHOT_DIR = BASE_DIR
LOG_FILE = os.path.join(BASE_DIR, "activity_log.txt")
TRACK_EVERY = 30        # seconds between activity snapshots
TRACKING = True         # set False to stop activity tracking
LANG = "en-IN"

# WhatsApp contacts: add name -> number WITH country code, like the examples below
CONTACTS = {
    # "mom": "+97798XXXXXXXX",
    # "friend": "+97798XXXXXXXX",
}

TUTOR_PROMPT = (
    "You are AMOX-1, a friendly English speaking partner. "
    "Your creator is Angel, a student from Nepal. Never say any other person or company made you. "
    "Replies are spoken aloud: 1 to 3 short simple sentences, plain text, no lists, markdown or emojis. "
    "The user's words come from speech recognition, so some words may be wrong. "
    "If a sentence makes no sense, say: Sorry, can you say that again? "
    "Only correct real grammar mistakes, like this: Nice try! You can say, corrected sentence. "
    "If the sentence is correct, do not correct it, just answer. "
    "Always reply in English only. "
    "You cannot open apps or websites yourself, never say you opened something. "
    "You have no long term memory, never promise to remember. "
    "If you do not know something, say so honestly."
)

MASTER_PROMPT = (
    "You are AMOX-1, a smart, warm, all-in-one personal voice assistant who talks like a kind friend. "
    "Your creator is Angel, a student from Nepal. Never say any other person or company made you. "
    "Answer any topic: studies, coding, general knowledge, advice, chat. "
    "Always reply in simple English only, never in Hindi or Devanagari script. "
    "Replies are spoken aloud: 1 to 4 short sentences, plain text, no lists, markdown or emojis. "
    "The user's words come from speech recognition, so some words may be wrong. "
    "If a sentence makes no sense, ask her to say it again. "
    "You cannot open apps or websites yourself, never say you opened something. "
    "You have no long term memory, never promise to remember. "
    "If you do not know something, say so honestly."
)

recognizer = sr.Recognizer()
history = []
mode = "master"

jokes = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "Why did the computer go to the doctor? It caught a virus.",
    "I told my laptop a joke. It did not laugh, it just froze.",
]

# Devanagari spellings speech recognition may produce -> English command words
HINDI_WORDS = {
    "ओपन": "open", "ओपेन": "open", "खोलो": "open", "खोल": "open",
    "यूट्यूब": "youtube", "युटुब": "youtube", "यूटूब": "youtube", "यूटयूब": "youtube", "यूटुब": "youtube",
    "प्ले": "play", "चलाओ": "play", "चला": "play",
    "सर्च": "search", "नोट": "note", "नोट्स": "note", "नोटबुक": "notepad", "नोटपैड": "notepad",
    "क्रोम": "chrome", "स्टॉप": "stop", "बंद": "stop",
    "मास्टर": "master", "ट्यूटर": "tutor", "मोड": "mode",
    "टाइम": "time", "समय": "time", "डेट": "date", "जोक": "joke",
    "स्क्रीनशॉट": "screenshot", "शॉट": "screenshot", "स्क्रीन": "screen",
    "वॉल्यूम": "volume", "अप": "up", "डाउन": "down", "म्यूट": "mute", "लॉक": "lock",
    "कैलकुलेटर": "calculator", "व्हाट्सएप": "whatsapp", "इंस्टाग्राम": "instagram",
    "जीमेल": "gmail", "टेक": "take", "मेक": "make", "ए": "a",
    "सॉन्ग": "song", "गाना": "song", "गाने": "song",
}


def normalize(text):
    return " ".join(HINDI_WORDS.get(w, w) for w in text.split())


# ---------- VOICE OUTPUT ----------
def has_hindi(text):
    return sum(1 for ch in text if "\u0900" <= ch <= "\u097F") > len(text) * 0.3


def speak(text):
    print("AMOX-1:", text)
    if has_hindi(text):
        return
    try:
        engine = pyttsx3.init("sapi5")
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", voices[0].id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        del engine
        time.sleep(0.8)
    except Exception as error:
        print("SPEECH ERROR:", repr(error))


# ---------- VOICE INPUT ----------
def calibrate():
    try:
        with sr.Microphone(device_index=1) as source:
            print("Calibrating microphone, please stay quiet...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
    except OSError as error:
        print("Microphone error:", error)


def listen():
    try:
        with sr.Microphone(device_index=1) as source:
            print("\nListening... (" + mode + " mode)")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=12)
        text = recognizer.recognize_google(audio, language=LANG)
        print("You said:", text)
        return normalize(text.lower().strip())
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        print("AMOX-1: Sorry, I could not understand.")
        return ""
    except sr.RequestError as error:
        print("Speech recognition error:", error)
        return ""
    except OSError as error:
        print("Microphone error:", error)
        return ""


# ---------- AI BRAIN (OFFLINE) ----------
def clean_for_speech(text):
    text = re.sub(r"[*#_`>~\n]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ask_ai(user_text):
    history.append({"role": "user", "content": user_text})
    prompt = TUTOR_PROMPT if mode == "tutor" else MASTER_PROMPT
    messages = [{"role": "system", "content": prompt}] + history[-MAX_HISTORY:]
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 160},
    }
    try:
        reply = requests.post(OLLAMA_URL, json=payload, timeout=180)
        reply.raise_for_status()
        answer = clean_for_speech(reply.json()["message"]["content"])
        history.append({"role": "assistant", "content": answer})
        return answer
    except requests.exceptions.ConnectionError:
        history.pop()
        return "Sorry creator, Ollama is not running. Please open Ollama and try again."
    except Exception as error:
        history.pop()
        print("AI ERROR:", repr(error))
        return "Sorry creator, I could not think of an answer. Please try again."


# ---------- INTERNET KNOWLEDGE ----------
WIKI_STARTS = ("who is ", "who was ", "what is ", "what are ", "tell me about ", "wikipedia ")


def try_wiki(command):
    """Short 'who is / what is' questions are answered from Wikipedia. Returns None if not applicable."""
    if wikipedia is None or mode != "master":
        return None
    for start in WIKI_STARTS:
        if command.startswith(start):
            topic = re.sub(r"^(the|a|an)\s+", "", command[len(start):].strip())
            words = topic.split()
            if not (0 < len(words) <= 4) or {"you", "your", "me", "my"} & set(words):
                return None
            summary = None
            try:
                summary = wikipedia.summary(topic, sentences=2, auto_suggest=False)
            except Exception:
                try:
                    hits = wikipedia.search(topic, results=1)
                    if hits:
                        summary = wikipedia.summary(hits[0], sentences=2, auto_suggest=False)
                except Exception:
                    summary = None
            if summary:
                return clean_for_speech(re.sub(r"\([^)]*\)", "", summary))
            return None
    return None


def read_news():
    try:
        r = requests.get("https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en", timeout=10)
        root = ET.fromstring(r.content)
        titles = [t.text.rsplit(" - ", 1)[0] for t in root.findall(".//item/title")[:5]]
        if titles:
            return "Here are the top news headlines. " + ". ".join(titles)
    except Exception as error:
        print("NEWS ERROR:", repr(error))
    return "Sorry, I could not get the news. Please check your internet."


# ---------- ACTIVITY TRACKING ----------
def tracker():
    while True:
        try:
            if TRACKING:
                win = gw.getActiveWindow()
                title = win.title.strip() if win and win.title else ""
                if title:
                    with open(LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "|" + title.replace("|", " ") + "\n")
        except Exception:
            pass
        time.sleep(TRACK_EVERY)


def uptime_hours():
    kernel = ctypes.windll.kernel32
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    return kernel.GetTickCount64() / 3600000


def today_report():
    today = datetime.now().strftime("%Y-%m-%d")
    counts = {}
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith(today) and "|" in line:
                    title = line.strip().split("|", 1)[1]
                    app = title.split(" - ")[-1].strip() or title
                    counts[app] = counts.get(app, 0) + 1
    except FileNotFoundError:
        pass
    up = "Your laptop has been on for %.1f hours since the last restart. " % uptime_hours()
    if not counts:
        return up + "I have not recorded any activity yet today."
    top = sorted(counts.items(), key=lambda x: -x[1])[:4]
    parts = [app + ", " + str(max(1, round(n * TRACK_EVERY / 60))) + " minutes" for app, n in top]
    total = sum(counts.values()) * TRACK_EVERY / 3600
    return up + "I tracked %.1f hours of activity today. Most used: " % total + "; ".join(parts) + "."


# ---------- LAPTOP HEALTH ----------
def health_check():
    if psutil is None:
        return "Please install psutil first, then I can check your laptop."
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("C:\\").percent
        msg = "CPU is at %d percent, memory is at %d percent, and your C drive is %d percent full. " % (cpu, ram, disk)
        tips = []
        if ram > 85:
            usage = {}
            for p in psutil.process_iter(["name", "memory_percent"]):
                name = p.info.get("name") or "unknown"
                usage[name] = usage.get(name, 0) + (p.info.get("memory_percent") or 0)
            heavy = [n for n, _ in sorted(usage.items(), key=lambda x: -x[1])[:3]]
            tips.append("Memory is high. Close some apps. The heaviest are " + ", ".join(heavy) + ".")
        if cpu > 85:
            tips.append("The CPU is very busy. Close heavy apps or wait for it to finish.")
        if disk > 90:
            tips.append("Your C drive is almost full. Delete unused files or move them to D drive.")
        battery = psutil.sensors_battery()
        if battery is not None:
            msg += "Battery is %d percent. " % battery.percent
            if battery.percent < 20 and not battery.power_plugged:
                tips.append("Battery is low. Please plug in your charger.")
        if not tips:
            tips.append("Everything looks fine.")
        return msg + " ".join(tips)
    except Exception as error:
        print("HEALTH ERROR:", repr(error))
        return "Sorry, I could not check the laptop."


# ---------- COMPUTER CONTROL ----------
SITES = {
    "youtube": "https://www.youtube.com",
    "chrome": "https://www.google.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "chatgpt": "https://chat.openai.com",
}

APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "vs code": "code",
    "code": "code",
}


def play_song(song):
    speak("Playing " + song)
    if pywhatkit:
        try:
            pywhatkit.playonyt(song)   # opens the first matching video directly
            return
        except Exception as error:
            print("pywhatkit error:", repr(error))
    webbrowser.open("https://www.youtube.com/results?search_query=" + quote(song))


def focus_youtube():
    """Brings the YouTube window to the front. Returns True if YouTube is active."""
    try:
        win = gw.getActiveWindow()
        if win and "youtube" in win.title.lower():
            return True
        for w in gw.getAllWindows():
            if "youtube" in w.title.lower():
                try:
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                except Exception:
                    pass
                time.sleep(0.7)
                win = gw.getActiveWindow()
                return bool(win and "youtube" in win.title.lower())
    except Exception as error:
        print("FOCUS ERROR:", repr(error))
    return False


def youtube_key(action, key=None, hotkey=None, done=""):
    if not focus_youtube():
        speak("I could not find a YouTube window. Say play and a song name first.")
        return
    if hotkey:
        pyautogui.hotkey(*hotkey)
    else:
        pyautogui.press(key)
    if done:
        speak(done)


def write_note(text):
    with open(os.path.join(BASE_DIR, "notes.txt"), "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%d %B %Y %I:%M %p") + " - " + text + "\n")
    os.system("start notepad")
    time.sleep(2)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


def take_screenshot():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_DIR, "screenshot_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".png")
    pyautogui.screenshot(path)
    return path


def describe_windows():
    try:
        active = gw.getActiveWindow()
        active_title = active.title if active else "nothing"
        titles = [t for t in gw.getAllTitles() if t.strip()]
        print("OPEN WINDOWS:", titles)
        return "You are on " + active_title + ". " + str(len(titles)) + " windows are open."
    except Exception as error:
        print("WINDOW ERROR:", repr(error))
        return "Sorry, I could not read the windows."


def send_whatsapp():
    if pywhatkit is None:
        speak("WhatsApp sending is not available because pywhatkit is missing.")
        return
    if not CONTACTS:
        speak("Your contacts list is empty. Add names and numbers in the CONTACTS part of the code.")
        return
    speak("Who should I message?")
    who = listen()
    number = None
    for name, num in CONTACTS.items():
        if name in who:
            number = num
            break
    if not number:
        speak("I could not find that contact.")
        return
    speak("What is the message?")
    msg = listen()
    if not msg:
        speak("I did not hear any message.")
        return
    speak("I will send: " + msg + ". Say yes to send.")
    answer = listen().split()
    if "yes" in answer or "send" in answer:
        speak("Sending now. Please do not touch the keyboard or mouse.")
        try:
            pywhatkit.sendwhatmsg_instantly(number, msg, 20, True, 3)
            speak("Done. Please check WhatsApp to confirm.")
        except Exception as error:
            print("WHATSAPP ERROR:", repr(error))
            speak("Sorry, I could not send the message.")
    else:
        speak("Okay, cancelled.")


def handle_command(command):
    """Returns True if command was handled, False if it should go to the AI."""
    words = command.split()
    if len(words) > 8:
        return False

    # --- volume ---
    if "volume" in words or "mute" in words:
        if "mute" in words:
            pyautogui.press("volumemute")
            speak("Muted")
        elif "up" in words:
            for _ in range(5):
                pyautogui.press("volumeup")
            speak("Volume up")
        elif "down" in words:
            for _ in range(5):
                pyautogui.press("volumedown")
            speak("Volume down")
        else:
            return False
        return True

    # --- YouTube controls ---
    if "pause" in words or "resume" in words:
        youtube_key("pause", key="k", done="")
        return True

    if ("next" in words and ("video" in words or "song" in words or "tutorial" in words)) or "skip" in words:
        youtube_key("next", hotkey=("shift", "n"), done="Next video")
        return True

    if "forward" in words:
        youtube_key("forward", key="l", done="")
        return True

    if "rewind" in words:
        youtube_key("rewind", key="j", done="")
        return True

    if "fullscreen" in words or ("full" in words and "screen" in words):
        youtube_key("fullscreen", key="f", done="")
        return True

    if "close" in words and ("video" in words or "youtube" in words or "tab" in words or "song" in words):
        youtube_key("close", hotkey=("ctrl", "w"), done="Closed")
        return True

    # --- laptop info ---
    if "screenshot" in words:
        speak("Screenshot saved")
        print("Saved at:", take_screenshot())
        return True

    if "lock" in words and ("laptop" in words or "computer" in words or "screen" in words or len(words) <= 2):
        speak("Locking")
        ctypes.windll.user32.LockWorkStation()
        return True

    if "report" in words or ("what" in words and "did" in words and "today" in words):
        speak(today_report())
        return True

    if "health" in words or ("check" in words and ("laptop" in words or "system" in words)) \
            or ("laptop" in words and ("problem" in words or "slow" in words)):
        speak("Checking your laptop.")
        speak(health_check())
        return True

    if "news" in words:
        speak(read_news())
        return True

    if "send" in words and ("message" in words or "whatsapp" in words):
        send_whatsapp()
        return True

    if ("what" in words and "open" in words) or "windows" in words or "screen" in words:
        speak(describe_windows())
        return True

    # --- play / search / open ---
    if "play" in words:
        song = command.replace("on youtube", "").replace("play", "").replace("song", "").strip()
        if song:
            play_song(song)
        else:
            speak("Which song should I play?")
        return True

    if "search" in words:
        query = command.replace("search for", "").replace("search", "").strip()
        if query:
            speak("Searching for " + query)
            webbrowser.open("https://www.google.com/search?q=" + quote(query))
        else:
            speak("What should I search for?")
        return True

    if "note" in words and ("take" in words or "make" in words or "write" in words):
        speak("What should I write?")
        note = listen()
        if note:
            write_note(note)
            speak("Note written")
        else:
            speak("I did not hear anything.")
        return True

    if "open" in words:
        for name, url in SITES.items():
            if name in command:
                speak("Opening " + name)
                webbrowser.open(url)
                return True
        for name, exe in APPS.items():
            if name in command:
                speak("Opening " + name)
                os.system("start " + exe)
                return True
        speak("Sorry, I do not know how to open that yet.")
        return True

    if "joke" in words:
        speak(random.choice(jokes))
        return True

    if "time" in words:
        speak("The time is " + datetime.now().strftime("%I:%M %p"))
        return True

    if "date" in words:
        speak("Today is " + datetime.now().strftime("%d %B %Y"))
        return True

    return False


# ---------- STARTUP ----------
os.makedirs(BASE_DIR, exist_ok=True)
threading.Thread(target=tracker, daemon=True).start()
calibrate()
speak("Hello creator. AMOX-1 is online in master mode. Say tutor mode for English practice.")

# ---------- MAIN LOOP ----------
while True:
    command = listen()
    if not command:
        continue

    words = command.split()

    if "master mode" in command:
        mode = "master"
        history.clear()
        speak("Master mode on. Ask me anything.")

    elif "tutor mode" in command:
        mode = "tutor"
        history.clear()
        speak("Tutor mode on. Let us practice English.")

    elif "stop" in words and len(words) <= 3:
        speak("Goodbye creator. See you soon.")
        break

    elif "new topic" in command and len(words) <= 4:
        history.clear()
        speak("Okay, new topic.")

    elif handle_command(command):
        pass

    else:
        wiki_answer = try_wiki(command)
        speak(wiki_answer if wiki_answer else ask_ai(command))