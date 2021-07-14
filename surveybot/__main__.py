import csv
import datetime
import json
import os
import subprocess
from pathlib import Path

import telebot
from vosk import Model, KaldiRecognizer, SetLogLevel

from surveybot.models import session, Answer
from surveybot.survey import Survey

SetLogLevel(-10)

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


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


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
    """
    /restart will result in new attempt to fill a survey, even if one is already underway
    /start will start a new fill only if the old one does not exist or was fully finished
    :param message:
    :return:
    """
    global state, SURVEY

    if SURVEY is None:
        bot.send_message(message.chat.id, "Загрузи файл с опросом для продолжения")
        return

    else:
        last_answer = session.query(Answer).filter(Answer.author == message.from_user.id).order_by(
            Answer.stamp.desc()).first()
        if message.text == "/restart":
            if last_answer is None or SURVEY.allow_restarts:
                bot.send_message(message.chat.id, "Напиши мне свой код для начала опроса")
                return
            else:
                bot.send_message(message.chat.id, "Вы уже проходили этот опрос, проходить его повторно нельзя")
                return
        else:
            if not last_answer:
                bot.send_message(message.chat.id, "Напиши мне свой код для начала опроса")
                return
            elif last_answer.question != len(SURVEY.questions) - 1:
                bot.send_message(message.chat.id,
                                 "У вас есть неоконченный опрос. Если вы хотите начать сначала, напишите /restart. Возвращаю вас к текущему вопросу")
                state[message.from_user.id] = last_answer.question + 1
                bot.send_message(message.chat.id, SURVEY.questions[state[message.from_user.id]].text)
            else:
                if SURVEY.allow_restarts:
                    bot.send_message(message.chat.id, "Напиши мне свой код для начала опроса")
                    return
                else:
                    bot.send_message(message.chat.id, "Вы уже проходили этот опрос, проходить его повторно нельзя")
                    return


@bot.message_handler(commands=["export"])
def export(message: telebot.types.Message):
    try:
        if message.text.split(" ")[1] == SURVEY.export_code:
            for file in DATA_PATH.glob("*"):
                bot.send_audio(message.chat.id, file.read_bytes(), title=file.name)

            user_to_answers = {}

            for entity in session.query(Answer).all():
                if entity.author in user_to_answers:
                    user_to_answers[entity.author].append(entity)
                else:
                    user_to_answers[entity.author] = [entity]

            for el in user_to_answers.values():
                el.sort(key=lambda x: x.stamp)

            with open("results.csv", "w", newline='') as csvfile:
                spamwriter = csv.writer(csvfile, delimiter=',')
                for id, answers in user_to_answers.items():
                    for chunk in chunks(answers, len(SURVEY.questions)):
                        to_write = [str(id)]
                        for question in chunk:
                            if question.is_text:
                                to_write.append(question.text)
                            else:
                                to_write.append(question.text + " : " + question.filename)

                        spamwriter.writerow(to_write)

            with open("results.csv", "r") as file:
                bot.send_document(message.chat.id, file, caption="results.csv")

        else:
            bot.send_message(message.chat.id, "Неверный код")
    except Exception as e:
        bot.send_message(message.chat.id, f"{str(e)} while exporting things")


@bot.message_handler(content_types=["text"], func=lambda msg: msg.from_user.id not in state)
def verify_code(message: telebot.types.Message):
    last_answer = session.query(Answer).filter(Answer.author == message.from_user.id).order_by(
        Answer.stamp.desc()).first()
    if SURVEY.code == message.text:
        if last_answer is None or SURVEY.allow_restarts:
            state[message.from_user.id] = 0
            bot.send_message(message.chat.id, SURVEY.questions[0].text)
        else:
            bot.send_message(message.chat.id, "Вы уже проходили этот опрос, проходить его повторно нельзя")
    else:
        bot.send_message(message.chat.id, "Неверный код")


@bot.message_handler(content_types=["text", "video_note", "voice"], func=lambda msg: msg.from_user.id in state)
def process_answer(message: telebot.types.Message):
    if message.content_type == "text":
        if SURVEY.questions[state[message.from_user.id]].text_allowed:
            session.add(
                Answer(text=message.text, question=state[message.from_user.id], is_text=True,
                       author=message.from_user.id))
        else:
            bot.send_message(message.chat.id, "На этот вопрос нельзя ответить текстом")
            return
    elif message.content_type == "voice":
        if SURVEY.questions[state[message.from_user.id]].audio_allowed:
            data = bot.download_file(bot.get_file(message.voice.file_id).file_path)
            file_name = f"{message.from_user.full_name}_{state[message.from_user.id] + 1}_{datetime.datetime.now()}.ogg"
            abs_path = str((DATA_PATH / Path(file_name)).resolve())

            (DATA_PATH / Path(file_name)).write_bytes(data)

            process = subprocess.Popen(['ffmpeg', '-loglevel', 'quiet', '-i',
                                        abs_path,
                                        '-ar', str(16000), '-ac', '1', '-f', 's16le', '-'],
                                       stdout=subprocess.PIPE)

            rec = KaldiRecognizer(MODEL, 16000)

            while True:
                data = process.stdout.read(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)

            session.add(
                Answer(text=json.loads(rec.FinalResult())["text"], question=state[message.from_user.id], is_audio=True,
                       filename=file_name, author=message.from_user.id))
        else:
            bot.send_message(message.chat.id, "На этот вопрос нельзя ответить аудио")
            return
    else:
        if SURVEY.questions[state[message.from_user.id]].roundies_allowed:
            return
        else:
            bot.send_message(message.chat.id, "На этот вопрос нельзя ответить кругляшом")
            return

    if state[message.from_user.id] == len(SURVEY.questions) - 1:
        bot.send_message(message.chat.id, SURVEY.end_message)
        del state[message.from_user.id]
    else:
        state[message.from_user.id] += 1
        bot.send_message(message.chat.id, SURVEY.questions[state[message.from_user.id]].text)

    session.commit()


bot.polling()
