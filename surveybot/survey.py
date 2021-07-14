import json


class Survey:

    def __init__(self, data: str):
        js = json.loads(data)

        self.name = js["name"]
        self.code = js["entrance_code"]
        self.allow_restarts = js["allow_restarts"]
        self.end_message = js["end_message"]

        self.questions = [Question(x) for x in js["questions"]]


class Question:

    def __init__(self, data: dict):
        self.text = data["text"]
        self.text_allowed = data["text_allowed"]
        self.audio_allowed = data["audio_allowed"]
        self.roundies_allowed = data["roundies_allowed"]
