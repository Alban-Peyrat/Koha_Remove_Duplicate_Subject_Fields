# -*- coding: utf-8 -*- 

# Coded for Koha 23.11

# external imports
import logging
import json
import requests
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, List
from enum import Enum


NS = {"marc": "http://www.loc.gov/MARC21/slim"}

# ↓ Tf ?
# Ensuite, faire les appels
# Token expire après 3600, check sa validité + relancer un get token si nécessaire
# ya moyen qu'après un call les inforamtions du tokken sont renvoyés

# ----------------- Enum def -----------------

class Content_Type(Enum):
    MARCXML = "application/marcxml+xml"
    MARC_IN_JSON = "application/marc-in-json"
    RAW_MARC = "application/marc"
    RAW_TEXT = "text/plain"
    JSON = "application/json"

class Record_Schema(Enum):
    MARC21 = "MARC21"
    UNIMARC = "UNIMARC"

class Errors(Enum):
    # Request Error
    GENERIC_REQUEST_ERROR = 0
    HTTP_ERROR = 1
    GENERIC_REQUEST_ERROR_INTO_NAME_ERROR = 2
    # Data error
    INVALID_BIBNB = 10
    RECORD_DOES_NOT_EXIST = 11
    # 2XX : authorities
    INVALID_AUTH_ID = 200
    AUTHORIRY_DOES_NOT_EXIST = 201
    # 3XX : parameters errors
    CONTENT_TYPE_NOT_SUPPORTED = 300
    RECORD_SCHEMA_NOT_SUPPORTED = 301
    API_NOT_SUPPORTED = 302

class Status(Enum):
    UNKNOWN = 0
    SUCCESS = 1
    ERROR = 2

class Api_Name(Enum):
    GET_BIBLIO = 0
    UPDATE_BIBLIO = 1
    ADD_BIBLIO = 2
    # 2XX : authorities
    GET_AUTH = 200
    GET_AUTH_LIST = 201

# ----------------- Func def -----------------

def validate_bibnb(id:str) -> str|None:
    """Checks if the biblionumber is only a number, returns it as a string striped.
    Returns None if biblinoumber is invalid"""
    id = str(id).strip()
    if not(re.search(r"^\d*$", id)):
        return None
    else:
        return id

def validate_int(nb:int|str|None, default:int=-1) -> int:
    """Checks if the number is a positive integer.
    Returns it as an int, or a default value (-1 by default)"""
    # Makes sure the default value in correct
    if type(default) != int:
        try:
            default = int(default)
        except:
            default = -1
    # Actual valiqation
    nb = validate_bibnb(nb)
    if not nb:
        return default
    return int(nb)

def validate_content_type(format:Content_Type|str, default:bool=True) -> Content_Type|None:
    """Checks if the content type has a legal value
    Defaults to RAW_MARC if value is illegal,
    unless optional default argument is set to False, then return None
    
    Returns a Content_Type member"""
    if type(format) == Content_Type:
        return format
    elif type(format) == str:
        for member in Content_Type:
            if member.value == format:
                return member
    else:
        if default:
            return Content_Type.RAW_MARC
        return None

def validate_record_schema(schema:Record_Schema|str, default:bool=True) -> Record_Schema|None:
    """Checks if the record schema has a legal value
    Defaults to UNIMARC if value is illegal,
    unless optional default argument is set to False, then return None
    
    Returns a Record_Schema member"""
    if type(schema) == Record_Schema:
        return schema
    elif type(schema) == str:
        for member in Record_Schema:
            if member.value == schema:
                return member
    else:
        if default:
            return Record_Schema.UNIMARC
        return None

def validate_api_name(api:Api_Name|str) -> Api_Name|None:
    """Checks if the api name has a legal value
    Returns a Api_Name member or None if it's invalid"""
    if type(api) == Api_Name:
        return api
    elif type(api) == str:
        for member in Api_Name:
            if member.value == api:
                return member
    else:
        return None

def add_to_dict_if_inexistent(dict:dict, key:str, value:None) -> None:
    """Checks if this key is already defined in the dict.
    If not, adds it and the value, else, does nothing"""
    if not key in dict:
        dict[key] = value

# ----------------- Class def -----------------

class KohaRESTAPIClient(object):
    """KohaRESTAPIClient
    =======
    A set of function to use Koha REST APIs
    On init take as arguments :
    - koha_url : Koha server URL
    - client_id
    - client_secret
    - service [opt] : service name
"""
    def __init__(self, koha_url, client_id, client_secret, service='KohaRESTAPIClient'):
        self.service = service
        self.init_logger()
        self.endpoint = str(koha_url).rstrip("/") + "/api/v1/"
        self.error:Errors = None
        self.error_msg:str = None
        self.status:Status = Status.UNKNOWN

        # Try authentification
        try:
            r = requests.request(method="POST", url=self.endpoint + "oauth/token",
                            data={
                                "grant_type": "client_credentials",
                                "client_id": client_id,
                                "client_secret": client_secret
                            }
                        )
            r.raise_for_status()
        # Error managing
        except requests.exceptions.HTTPError:
            self.status = Status.ERROR
            self.error = Errors.HTTP_ERROR
            self.log.http_error(r, init=True)
            self.error_msg = r.reason
        except requests.exceptions.RequestException as generic_error:
            try:
                self.status = Status.ERROR
                self.error = Errors.GENERIC_REQUEST_ERROR
                self.log.request_generic_error(r, generic_error, msg="Generic exception", init=True)
                self.error_msg = f"Generic exception : {r.reason}"
            except NameError as e:
                self.status = Status.ERROR
                self.error = Errors.GENERIC_REQUEST_ERROR_INTO_NAME_ERROR
                self.log.generic_error(e, msg="Generic exception then NameError", init=True)
                self.error_msg = e
        # Access authorized
        else:
            token = json.loads(r.content)
            # Store token 
            self.token = token
            self.status = Status.SUCCESS
            self.log.info(f"{self.log.init_name} :: Access authorized")

    # ---------- API methods ----------

    # ----- Authorities -----
    def get_auth(self, id:str, format:Content_Type=Content_Type.RAW_MARC) -> str|Errors:
        """Returns the authority record WITHOUT decoding it.
        If an error occurred, returns an Errors element"""
        # Checks if the provided ID is a number
        api = Api_Name.GET_AUTH
        auth_id = validate_bibnb(id)
        # Leaves if not
        if auth_id == None:
            self.log.error(f"{api.name} Invalid input authority ID ({id})")
            return Errors.INVALID_AUTH_ID
        # Checks if content-type is correct
        content_type = validate_content_type(format)

        # Try getting the authority
        # Hm, I'm getting an error 500 when trying to get the auth record as MARCXML
        # But other 4 format work, so Idk, marcxml issue ? Though it works for biblios
        try:
            headers = {
                "Authorization":f"{self.token['token_type']} {self.token['access_token']}",
                "accept":content_type.value
            }
            r = requests.get(f"{self.endpoint}authorities/{auth_id}", headers=headers)
            r.raise_for_status()
        # Error handling
        except requests.exceptions.RequestException as generic_error:
            self.log.request_generic_error(r, generic_error, msg=f"{api.name} Generic exception")
            if r.status_code == 404:
                return Errors.AUTHORIRY_DOES_NOT_EXIST
            else:
                return Errors.GENERIC_REQUEST_ERROR
        # Succesfully retrieve the record
        else:
            self.log.debug(f"{api.name} Authority {id} retrieved")
            return r.content

    def list_auth(self, query:Dict={}, format:Content_Type=Content_Type.RAW_MARC, page:int=1, nb_res:int=40, auth_type:str=None) -> str|Errors:
        """Returns a list of authorities WITHOUT decoding them.
        If an error occurred, returns an Errors element
        
        If an authority type is provided in the query, will use this one"""
        # Checks if the provided ID is a number
        api = Api_Name.GET_AUTH_LIST
        # Checks if content-type is correct
        content_type = validate_content_type(format)
        page = validate_int(page, default=1)
        nb_res = validate_int(nb_res, default=1)

        # Try getting the authority
        # Hm, I'm getting an error 500 when trying to get the auth record as MARCXML
        # But other 4 format work, so Idk, marcxml issue ? Though it works for biblios
        try:
            headers = {
                "Authorization":f"{self.token['token_type']} {self.token['access_token']}",
                "accept":content_type.value
            }
            params = {
                "_page":page,
                "_per_page":nb_res
            }
            data = {}
            # If query is a dict, use it as body
            if type(query) == dict:
                data = query
            # If an auth type is provided and none was provided in the query, adds it
            if auth_type:
                add_to_dict_if_inexistent(data, "framework_id", str(auth_type))
            r = requests.get(f"{self.endpoint}authorities", headers=headers, data=data, params=params)
            r.raise_for_status()
        # Error handling
        except requests.exceptions.RequestException as generic_error:
            self.log.request_generic_error(r, generic_error, msg=f"{api.name} Generic exception")
            return Errors.GENERIC_REQUEST_ERROR
        # Succesfully retrieve the record
        else:
            self.log.debug(f"{api.name} Authority list retrieved")
            return r.content

    # ----- Biblios -----

    def get_biblio(self, id:str, format:Content_Type=Content_Type.RAW_MARC) -> str|Errors:
        """Returns the record WITHOUT decoding it.
        If an error occurred, returns an Errors element"""
        # Checks if the provided ID is a number
        api = Api_Name.GET_BIBLIO
        bibnb = validate_bibnb(id)
        # Leaves if not
        if bibnb == None:
            self.log.error(f"{api.name} Invalid input biblionumber ({id})")
            return Errors.INVALID_BIBNB
        # Checks if content-type is correct
        content_type = validate_content_type(format)

        # Try getting the biblio
        try:
            headers = {
                "Authorization":f"{self.token['token_type']} {self.token['access_token']}",
                "accept":content_type.value
            }
            r = requests.get(f"{self.endpoint}biblios/{bibnb}", headers=headers)
            r.raise_for_status()
        # Error handling
        except requests.exceptions.RequestException as generic_error:
            self.log.request_generic_error(r, generic_error, msg=f"{api.name} Generic exception")
            if r.status_code == 404:
                return Errors.RECORD_DOES_NOT_EXIST
            else:
                return Errors.GENERIC_REQUEST_ERROR
        # Succesfully retrieve the record
        else:
            self.log.debug(f"{api.name} Record {id} retrieved")
            return r.content

    def __post_biblio(self, api:Api_Name, record:str, format:Content_Type=Content_Type.RAW_MARC, record_schema:Record_Schema=Record_Schema.UNIMARC, framework_id:str=None, id:str=None) -> str|Errors:
        """Private function for add & update biblio.
        Returns the API repsonse content (or an error)
        
        Takes as argument :
            - api {Api_Name} : ADD_BIBLIO or UPDATE_BIBLIO
            - record {str} : record as a string for the format
            - format {Content_Type} : format of the record, either RAW_MARC (default), MARCXML or MARC_IN_JSON
            - record_schema {Record_Schema} : UNIMARC (default) or MARC21
            - [optionnal] framework_id {str} : code of the framework ID in Koha
            - [optionnal] id {str} : MANDATORY for UPDATE_BIBLIO : the biblionumber to update (useless for ADD_BIBLIO)"""
        # Check if the api name is correct : if not, return an error
        api = validate_api_name(api)
        if api == None or api not in [
            Api_Name.ADD_BIBLIO,
            Api_Name.UPDATE_BIBLIO
            ]:
            return Errors.API_NOT_SUPPORTED
        
        # Check if the content type is correct : if not, return an error
        content_type = validate_content_type(format, default=False)
        if content_type == None or content_type in [
            Content_Type.JSON,
            Content_Type.RAW_TEXT
            ]:
            return Errors.CONTENT_TYPE_NOT_SUPPORTED
        
        # Check if the record chema is correct : if not, return an error
        record_schema = validate_record_schema(record_schema, default=False)
        if record_schema == None:
            return Errors.RECORD_SCHEMA_NOT_SUPPORTED

        # If update, validate the biblionumber
        if api == Api_Name.UPDATE_BIBLIO:
            bibnb = validate_bibnb(id)
            # Leaves if not
            if bibnb == None:
                self.log.error(f"{api.name} Invalid input biblionumber ({id})")
                return Errors.INVALID_BIBNB

        # Try psoting the biblio
        try:
            headers = {
                "Authorization":f"{self.token['token_type']} {self.token['access_token']}",
                "Content-type":content_type.value,
                "x-record-schema":record_schema.value
            }
            # Add framework id if set
            if framework_id:
                headers["x-framework-id"] = framework_id
            data = record # yes just put the record as it is
            url = f"{self.endpoint}biblios"
            method = "POST"
            if api == Api_Name.UPDATE_BIBLIO:
                url = url + f"/{bibnb}"
                method = "PUT"
            r = requests.request(method, url, headers=headers, data=data)
            r.raise_for_status()
        # Error handling
        except requests.exceptions.RequestException as generic_error:
            self.log.request_generic_error(r, generic_error, msg=f"{api.name} Generic exception")
            if r.status_code == 404:
                return Errors.RECORD_DOES_NOT_EXIST
            else:
                return Errors.GENERIC_REQUEST_ERROR
        # Succesfully retrieve the record
        else:
            if api == Api_Name.UPDATE_BIBLIO:
                self.log.debug(f"{api.name} Record {id} updated")
            else:
                self.log.debug(f"{api.name} Record added")
            return r.content

    def add_biblio(self, record:str, format:Content_Type=Content_Type.RAW_MARC, record_schema:Record_Schema=Record_Schema.UNIMARC, framework_id:str=None) -> str|Errors:
        """Add a new biblio record to Koha
        Returns the API repsonse content (or an error)
        
        Takes as argument :
            - record {str} : record as a string for the format
            - format {Content_Type} : format of the record, either RAW_MARC (default), MARCXML or MARC_IN_JSON
            - record_schema {Record_Schema} : UNIMARC (default) or MARC21
            - [optionnal] framework_id {str} : code of the framework ID in Koha"""
        return self.__post_biblio(Api_Name.ADD_BIBLIO, record=record, format=format, record_schema=record_schema, framework_id=framework_id)

    def update_biblio(self, id:str, record:str, format:Content_Type=Content_Type.RAW_MARC, record_schema:Record_Schema=Record_Schema.UNIMARC, framework_id:str=None) -> str|Errors:
        """Update a biblio record in Koha 
        Returns the API repsonse content (or an error)
        
        Takes as argument :
            - id {str} : the biblionumber to update
            - record {str} : record as a string for the format
            - format {Content_Type} : format of the record, either RAW_MARC (default), MARCXML or MARC_IN_JSON
            - record_schema {Record_Schema} : UNIMARC (default) or MARC21
            - [optionnal] framework_id {str} : code of the framework ID in Koha"""
        return self.__post_biblio(Api_Name.UPDATE_BIBLIO, record=record, format=format, record_schema=record_schema, framework_id=framework_id, id=id)

    # ---------- Logger methods for other classes / functions ----------
    def init_logger(self):
        """Init the logger"""
        self.log = self.Logger(self)

    class Logger(object):
        def __init__(self, parent) -> None:
            self.parent:KohaRESTAPIClient = parent
            self.logger = logging.getLogger(self.parent.service)
            self.init_name = "KohaRESTAPIClient_Init"

        def http_error(self, r:requests.Response, msg:str="", init=False):
            """Log an error statement with the service then HTTP Status, Method, URL and response.
            
            Takes as argument :
                - requests.Reponse
                - [optional] msg : a message to display before HTTP infos
                - [optionnal, default to False] init : if True, set service as 'KohaRESTAPIClient_Init'"""
            # Optinnal Message
            if msg != "":
                msg = f"{msg}. "
            # Service
            service = self.parent.service
            if init:
                service = self.init_name
            self.logger.error(f"{service} :: {msg}HTTP Status : {r.status_code} || Method : {r.request.method} || URL : {r.url} || Reason : {r.text}")

        def request_generic_error(self, r:requests.Response, reason, msg:str="", init=False):
            """Log an error statement with the service then HTTP Status, Method, URL and error reason.
            
            Takes as argument :
                - requests.Reponse
                - reason : the exception message
                - [optional] msg : a message to display before HTTP infos
                - [optionnal, default to False] init : if True, set service as 'KohaRESTAPIClient_Init'"""
            # Optinnal Message
            if msg != "":
                msg = f"{msg}. "
            # Service
            service = self.parent.service
            if init:
                service = self.init_name
            self.logger.error(f"{service} :: {msg}HTTP Status : {r.status_code} || Method : {r.request.method} || URL : {r.url} || Reason : {reason}")

        def generic_error(self, reason, msg:str, init=False):
            """Log an error statement with the service followed by the error message then the error reason.
            
            Takes as argument :
                - reason : the exception message
                - msg : a message to display before HTTP infos
                - [optionnal, default to False] init : if True, set service as 'KohaRESTAPIClient_Init'"""
            # Optinnal Message
            if msg != "":
                msg = f"{msg}. "
            # Service
            service = self.parent.service
            if init:
                service = self.init_name
            self.logger.error(f"{service} :: {msg} || {reason}")

        def critical(self, msg:str):
            """Basic log critical function"""
            self.logger.critical(f"{msg}")

        def debug(self, msg:str):
            """Log a debug statement logging first the service then the message"""
            self.logger.debug(f"{self.parent.service} :: {msg}")

        def info(self, msg:str):
            """Basic log info function"""
            self.logger.info(f"{msg}")

        def error(self, msg:str):
            """Log a error statement logging first the service then the message"""
            self.logger.error(f"{self.parent.service} :: {msg}")
