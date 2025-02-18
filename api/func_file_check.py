# -*- coding: utf-8 -*- 

# External imports
import os

def check_file_existence(path:str) -> bool:
    """Returns if a file exists, returns a boolean"""
    return os.path.exists(path)

def check_dir_existence(path:str, create:bool=True):
    """Returns if a directory exists.
    If optional argument create is set to True,
    attempt creating the directory before returning if the directory exists"""
    if not create and os.path.exists(path):
        return True
    elif not create and not os.path.exists(path):
        return False
    else:
        try:
            os.makedirs(path)
        except:
            pass # do nothing
        return os.path.exists(path)
