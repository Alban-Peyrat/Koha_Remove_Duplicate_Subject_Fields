# -*- coding: utf-8 -*- 

# External import
import logging
from logging.handlers import RotatingFileHandler
from enum import Enum

class Level(Enum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4

class Logger(object):# From FCR
    def __init__(self, path:str, name:str) -> None:
        self.name = name
        self.__init_logs(path, name, "DEBUG")
        self.logger = logging.getLogger(name)

    def __init_logs(self, logsrep,programme,niveau):
        # logs.py by @louxfaure, check file for more comments
        # D'aprés http://sametmax.com/ecrire-des-logs-en-python/
        logsfile = logsrep + "/" + programme + ".log"
        logger = logging.getLogger(programme)
        logger.setLevel(getattr(logging, niveau))
        # Formatter
        formatter = logging.Formatter(u'%(asctime)s :: %(levelname)s :: %(message)s')
        file_handler = RotatingFileHandler(logsfile, 'a', 10000000, 1, encoding="utf-8")
        file_handler.setLevel(getattr(logging, niveau))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # For console
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(getattr(logging, niveau))
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        logger.info('Logger initialised')

    # ---------- basics ----------

    def debug(self, msg:str):
        """Log a debug statement logging first the service then the message"""
        self.logger.debug(f"{self.name} :: {msg}")

    def info(self, msg:str):
        """Log a info statement logging first the service then the message"""
        self.logger.info(f"{self.name} :: {msg}")

    def warning(self, msg:str):
        """Log a warning statement logging first the service then the message"""
        self.logger.warning(f"{self.name} :: {msg}")

    def error(self, msg:str):
        """Log a error statement logging first the service then the message"""
        self.logger.error(f"{self.name} :: {msg}")

    def critical(self, msg:str):
        """Log a critical statement logging first the service then the message"""
        self.logger.critical(f"{self.name} :: {msg}")

    # ---------- Advanced ----------

    def __msg_to_level(self, level:Level, msg:str):
        """Internal function that calls the rigth log function"""
        if level == Level.DEBUG:
            self.logger.debug(msg)
        elif level == Level.INFO:
            self.logger.info(msg)
        elif level == Level.WARNING:
            self.logger.warning(msg)
        elif level == Level.ERROR:
            self.logger.error(msg)
        elif level == Level.CRITICAL:
            self.logger.critical(msg)

    def record_message(self, level:Level, index:int, id:str|None, msg:str):
        """Log at wanted level with the record index and ID before the message.
        The ID can be None"""
        output = f"Index {index} : {msg}"
        if id != None:
            output = f"ID {id} (index : {index}) : {msg}"
        self.__msg_to_level(level, output)

    def message_data(self, level:Level, msg:str, data):
        """Log at wanted level a msg and data separated by :"""
        self.__msg_to_level(level, f"{msg} : {data}")

    def big_message(self, level:Level, msg:str):
        """Logs at wanted level a message encapsuled between ----"""
        self.__msg_to_level(level, f"--------------- {msg} ---------------")

