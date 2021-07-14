import datetime
import json
import os
import subprocess
from pathlib import Path

import telebot
from vosk import Model, KaldiRecognizer

from models import session, Answer
from survey import Survey

SURVEY_PATH = Path("../survey.json")
DATA_PATH = Path("../data/")
SURVEY = None

MODEL = Model("../model")

if SURVEY_PATH.exists():
    SURVEY = Survey(SURVEY_PATH.read_text())

if not DATA_PATH.exists():
    DATA_PATH.mkdir()

bot = telebot.TeleBot(os.getenv("BOTTOKEN"))

state = {}


@bot.message_handler(content_types=["document"], func=lambda msg: SURVEY is None)
def set_survey(message: telebot.types.Message):
    data = bot.download_file(bot.get_file(message.document.file_id).file_path)

    try:
        SURVEY = Survey(data.decode())
    except Exception as e:
        bot.send_message(message.chat.id, f"Unable to load survey, {e}")
        return

    SURVEY_PATH.write_bytes(data)
    bot.send_message(message.chat.id, F"Set survey {SURVEY.name}")


@bot.message_handler(commands=['start', 'restart'])
def send_welcome(message: telebot.types.Message):
    global state, SURVEY

    if SURVEY is None:
        bot.send_message(message.chat.id, "Загрузи файл с опросом для продолжения")
        return

    else:
        bot.send_message(message.chat.id, "Напиши мне свой код для начала опроса")
        return


@bot.message_handler(content_types=["text"], func=lambda msg: msg.from_user.id not in state)
def verify_code(message: telebot.types.Message):
    if SURVEY.code == message.text:  # TODO Check restart
        state[message.from_user.id] = 0
        bot.send_message(message.chat.id, SURVEY.questions[0].text)
    else:
        bot.send_message(message.chat.id, "Неверный код")


@bot.message_handler(content_types=["text", "video_note", "voice"], func=lambda msg: msg.from_user.id in state)
def process_answer(message: telebot.types.Message):
    if message.content_type == "text":
        session.add(Answer(text=message.text, question=state[message.from_user.id], is_text=True))
    elif message.content_type == "voice":
        data = bot.download_file(bot.get_file(message.voice.file_id).file_path)
        file_name = f"{message.from_user.full_name}_{state[message.from_user.id] + 1}_{datetime.datetime.now()}.waw"
        abs_path = str((DATA_PATH / Path(file_name)).resolve())

        (DATA_PATH / Path(file_name)).write_bytes(data)

        process = subprocess.Popen(['ffmpeg', '-loglevel', 'quiet', '-i',
                                    abs_path,
                                    '-ar', str(16000), '-ac', '1', '-f', 's16le', '-'],
                                   stdout=subprocess.PIPE)

        rec = KaldiRecognizer(MODEL, 16000)

        decoded = ""

        while True:
            data = process.stdout.read(4000)
            if len(data) == 0:
                break
            rec.AcceptWaveform(data)

        session.add(
            Answer(text=json.loads(rec.FinalResult())["text"], question=state[message.from_user.id], is_text=True,
                   filename=file_name))
    else:
        pass  # TODO

    if state[message.from_user.id] == len(SURVEY.questions) - 1:
        bot.send_message(message.chat.id, SURVEY.end_message)
        del state[message.from_user.id]
    else:
        state[message.from_user.id] += 1
        bot.send_message(message.chat.id, SURVEY.questions[state[message.from_user.id]].text)


bot.polling()
