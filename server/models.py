from sqlalchemy import Column, Integer, String
from db import Base


class User(Base):
    __tablename__ = "userdata"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String)
    password = Column(String)