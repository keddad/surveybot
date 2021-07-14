# surveybot

Simple telegram bot for conducting surveys with support for audio and video messages. It uses Vosk for voice
recognition, so you better put your model in model file.

```/start``` starts a survey. If User already started a survey, he will continue where he left

```/restart``` allows you to start a new survey, even if you haven't finished one

```/export <code>``` allows you to export all the media and the .csv with results
