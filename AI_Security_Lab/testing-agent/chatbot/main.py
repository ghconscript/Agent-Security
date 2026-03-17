#!/usr/bin/env python
import os
from time import sleep

from dotenv import load_dotenv

import baserun
from chatbot.bot import run_chatbot

load_dotenv()


def main():
    baserun.init()

    username = os.getlogin()
    with baserun.with_session(username):
        run_chatbot()
        sleep(1)


if __name__ == "__main__":
    main()
