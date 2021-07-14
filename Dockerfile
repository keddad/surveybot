FROM python:3.9

RUN apt-get update -y
RUN apt-get install ffmpeg -y

RUN pip install pipenv
COPY Pipfile* ./
RUN pipenv install --system

COPY surveybot surveybot/
CMD python -m surveybot