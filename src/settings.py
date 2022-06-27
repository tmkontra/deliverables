import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    DEPLOYMENT: str = "local" # "private", "demo"
    PASSWORD: str = os.getenv("AUTH_PASSWORD")
    SECRET_KEY: str = os.getenv("SECRET_KEY")
