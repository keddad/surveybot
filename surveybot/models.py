import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///:memory:')
Base = declarative_base()


class Answer(Base):
    __tablename__ = 'answers'

    id = Column(Integer, primary_key=True)

    question = Column(Integer)
    stamp = Column(DateTime, default=datetime.datetime.utcnow)

    is_text = Column(Boolean)
    is_audio = Column(Boolean)
    is_rounides = Column(Boolean)

    text = Column(String)
    filename = Column(String)


Base.metadata.create_all(engine)
session = sessionmaker(bind=engine)()
