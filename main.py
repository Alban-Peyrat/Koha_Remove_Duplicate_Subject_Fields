# -*- coding: utf-8 -*- 

# Coded for Koha 23.11

# external imports
import os
import dotenv
import csv
from typing import Dict, List
from enum import Enum
import pymarc

# Internal imports
from api.Koha_REST_API_Client import KohaRESTAPIClient, Content_Type, Status as Koha_Api_Status, Errors as Koha_Api_Errors, validate_int
from api.cl_log import Logger, Level
from api.func_file_check import check_file_existence, check_dir_existence
import api.marc_utils_5 as marc_utils

# Load paramaters
dotenv.load_dotenv()

SERVICE = "Koha_Remove_Subjects_Dupes"
# Load tags
RAW_SUBJECT_TAGS=os.getenv("SUBJECTS_TAG")
SUBJECT_TAGS:List[str] = []
# Parse tags and make sure they are datafields
for tag in RAW_SUBJECT_TAGS.split(","):
    tag_as_int = validate_int(tag)
    if tag_as_int > 9 and tag_as_int < 1000:
        if tag_as_int < 100:
            SUBJECT_TAGS.append("0" + str(tag_as_int))
        else:
            SUBJECT_TAGS.append(str(tag_as_int))
# if no tag was kept, exit
if len(SUBJECT_TAGS) < 1:
    print(r"/!\ No tag is set to be deduped /!\ ")
    exit()
# Load input file
INPUT_FILE_PATH = os.path.abspath(os.getenv("INPUT_FILE"))
# Leaves if the file doesn't exists
if not check_file_existence(INPUT_FILE_PATH):
    print(r"/!\ Input file does not exist /!\ ")
    exit()
# Load output folder
OUTPUT_PATH = os.path.abspath(os.getenv("OUTPUT_PATH"))
# Check if folder exist, creates if not folder or leave if it can not
if not check_dir_existence(OUTPUT_PATH):
    print(r"/!\ Output folder does not exist & could not be created /!\ ")
    exit()
# Load other stuff
RECORD_NB_LIMIT = validate_int(os.getenv("RECORD_NB_LIMIT"), 500)

# ----------------- Enum definition -----------------
class Error_Types(Enum):
    REQUESTS_GET_ERROR = 0
    SECURITY_STOP = 1
    REQUESTS_PUT_ERROR = 2
    BIBNB_IS_INCORRECT = 10
    NO_RECORD = 20
    NO_BIBNB_IN_RECORD = 21
    FAILED_TO_PARSE_MARC = 21
    WARNING_FIELD_WITHOUT_AUTHORITY_ID = 30
    RECORD_WAS_NOT_CHANGED = 31
    WARNING_MULTIPLE_AUTHORITY_ID_IN_ONE_FIELD = 32
    

# ----------------- Classes definition -----------------
class Error_File(object):
    def __init__(self, file_path:str) -> None:
        self.path = file_path
        self.file = open(self.path, "w", newline="", encoding='utf-8')
        self.headers = ["error_type", "index", "bibnb", "message"]
        self.writer = csv.DictWriter(self.file, extrasaction="ignore", fieldnames=self.headers, delimiter=";")
        self.writer.writeheader()

    def write(self, error_type:Error_Types, index:int=None, bibnb:int=None, msg:str=None):
        # Use str to prevent crash if I'm stupid when coding
        self.writer.writerow({
            "error_type":error_type.name,
            "index":str(index),
            "bibnb":str(bibnb),
            "message":str(msg)
            })

    def close(self):
        self.file.close()

class Report_Deleted_Fields_File(object):
    def __init__(self, file_path:str) -> None:
        self.path = file_path
        self.file = open(self.path, "w", newline="", encoding='utf-8')
        self.headers = ["bibnb", "index", "tag", "auth_id", "field"]
        self.writer = csv.DictWriter(self.file, extrasaction="ignore", fieldnames=self.headers, delimiter=";")
        self.writer.writeheader()

    def write(self, bibnb:int, index:int, tag:str, auth_id:str, field:str):
        # Use str to prevent crash if I'm stupid when coding
        self.writer.writerow({
            "bibnb":str(bibnb),
            "index":str(index),
            "tag":str(tag),
            "auth_id":str(auth_id),
            "field":str(field)
            })

    def close(self):
        self.file.close()

class Report_Updated_Bibnb_File(object):
    def __init__(self, file_path:str) -> None:
        self.path = file_path
        self.file = open(self.path, "w", newline="", encoding='utf-8')

    def write(self, bibnb:int):
        # Use str to prevent crash if I'm stupid when coding
        self.file.write(f"{str(bibnb)}\n")

    def close(self):
        self.file.close()

# ----------------- Functions definition -----------------
def dedupe_field(record:pymarc.record.Record, tag:str, index:int=None, bibnb:int=None) -> bool:
    """Removes multiple occurence of fields sharing the same $9
    
    Returns a bool to know if the record was edited"""
    auth_id_index:List[str] = []
    fields:List[pymarc.field.Field] = []
    for field in record.get_fields(tag):
        # If no authority ID, keep the field but log a warning
        if not field.get("9"):
            ERRORS_FILE.write(Error_Types.WARNING_FIELD_WITHOUT_AUTHORITY_ID, index=index, bibnb=bibnb, msg=marc_utils.field_as_string(field))
            LOG.record_message(Level.WARNING, index, bibnb, msg=f"Field without authority ID : {marc_utils.field_as_string(field)}")
            fields.append(field)
            continue
        # For info purpose, checks if multiple $9, as this should not be the case
        if len(field.get_subfields("9")) > 1:
            ERRORS_FILE.write(Error_Types.WARNING_MULTIPLE_AUTHORITY_ID_IN_ONE_FIELD, index=index, bibnb=bibnb, msg=marc_utils.field_as_string(field))
            LOG.record_message(Level.WARNING, index, bibnb, msg=f"Field has multiple authority ID : {marc_utils.field_as_string(field)}")
        # Checks if this ID was already met
        # If yes, log an info + report & don't add the field to the list
        auth_id = field.get("9")
        if auth_id in auth_id_index:
            LOG.record_message(Level.INFO, index, bibnb, msg=f"Deduping on authority ID {auth_id} : {marc_utils.field_as_string(field)}")
            DELETED_FIELD_FILE.write(bibnb, index, tag, auth_id, field)
            continue
        # If no, add the authority ID to the index & the field to the fields
        auth_id_index.append(auth_id)
        fields.append(field)
    
    # Once loop is over, check if there were duplicates for this tag
    if len(fields) == len(record.get_fields(tag)):
        LOG.record_message(Level.INFO, index, bibnb, msg=f"Tag {tag} did not have duplicates")
        return False
    
    # If there were duplicates, remove fields from the record and 
    LOG.record_message(Level.INFO, index, bibnb, msg=f"Tag {tag} had duplicates : removing them")
    record.remove_fields(tag)
    record.add_ordered_field(*fields) # don't forget the * before the list
    return True

# ----------------- Preparing Main -----------------
KOHA = KohaRESTAPIClient(os.getenv("KOHA_URL"), os.getenv("KOHA_CLIENT_ID"), os.getenv("KOHA_CLIENT_SECRET"))
# Leave if failed to connect to Koha
if KOHA.status != Koha_Api_Status.SUCCESS:
    print(r"/!\ Failed to connect to Koha /!\ ")
    exit()
LOG = Logger(os.getenv("LOGS_FOLDER"), SERVICE)
ERRORS_FILE = Error_File(OUTPUT_PATH + r"\KRSD_errors.csv")
DELETED_FIELD_FILE = Report_Deleted_Fields_File(OUTPUT_PATH + r"\KRSD_deleted_fields.csv")
UPDATED_BIBNB_FILE = Report_Updated_Bibnb_File(OUTPUT_PATH + r"\KRSD_update_bibnb.txt")
LOG.big_message(Level.INFO, "Execution settings")
LOG.message_data(Level.INFO, "Input file", INPUT_FILE_PATH)
LOG.message_data(Level.INFO, "Report deleted fields file", DELETED_FIELD_FILE.path)
LOG.message_data(Level.INFO, "Updated biblionumbers file", UPDATED_BIBNB_FILE.path)
LOG.message_data(Level.INFO, "Errors file", ERRORS_FILE.path)
LOG.message_data(Level.INFO, "Maximum of records to process", RECORD_NB_LIMIT)
LOG.message_data(Level.INFO, "Tags to process", ", ".join(SUBJECT_TAGS))
LOG.big_message(Level.INFO, "Starting main script")

# ----------------- Main -----------------
# Iterate through all records to fix
with open(INPUT_FILE_PATH, mode="r") as f:
    file_lines = f.readlines()
    security = 0
    for index, line in enumerate(file_lines):
        security = security + 1
        if security > RECORD_NB_LIMIT:
            ERRORS_FILE.write(Error_Types.SECURITY_STOP, index=index, msg="Security check : maximum number of records reached")
            LOG.record_message(Level.CRITICAL, index, None, f"Security check : maximum number of records reached")
            break
        bibnb = validate_int(line.strip())
        # Catch mal formed bibnb
        if bibnb < 1:
            ERRORS_FILE.write(Error_Types.BIBNB_IS_INCORRECT, index=index, msg=line.strip())
            LOG.record_message(Level.ERROR, index, None, f"Incorrect biblionumber : {line.strip()}")
            continue
        
        # Get record with Koha private GET API
        raw_record = KOHA.get_biblio(bibnb, Content_Type.RAW_MARC)
        # An error occured while getting the record, log & skip to next one
        if type(raw_record) == Koha_Api_Errors:
            ERRORS_FILE.write(Error_Types.REQUESTS_GET_ERROR, index=index, bibnb=bibnb, msg=raw_record.name)
            LOG.record_message(Level.ERROR, index, bibnb, f"An error happened with the API trying to get the record : {raw_record.name}")
            continue
        # ||| On verra si on a besoin de cette aprtie du code ou pas
        # # Pymarc is not reading records because of the new lines
        # # So decode the string, remove them, then reencode the string
        # # Make sure to only remove \n at the end of record, otherwise record length won't match
        # AUTH_INDEX.add_auth_list_to_index(raw_authority_list.decode().replace("\x1e\x1d\n", "\x1e\x1d").encode(), page)
        # ||| fin du On verra si on a besoin de cette aprtie du code ou pas
        
        # Parse record
        record = None
        try:
            record = pymarc.record.Record(data=raw_record, to_unicode=True, force_utf8=True)
        except:
            ERRORS_FILE.write(Error_Types.FAILED_TO_PARSE_MARC, index=index, bibnb=bibnb)
            LOG.record_message(Level.ERROR, index, bibnb, "Failed to parse MARC record")
            continue

        # If record is invalid
        if record is None:
            ERRORS_FILE.write(Error_Types.NO_RECORD, index=index, bibnb=bibnb)
            LOG.record_message(Level.ERROR, index, bibnb, "Record is empty / invalid")
            continue # Fatal error, skipp

        # Checks that there is a biblionumber for PUT
        if not record.get("001"):
            ERRORS_FILE.write(Error_Types.NO_BIBNB_IN_RECORD, index=index, bibnb=bibnb)
            LOG.record_message(Level.ERROR, index, bibnb, "Record has no biblionumber")
            continue

        # Track if record was changed
        record_was_changed = False
        # For each subject tag, dedupe the fields
        for tag in SUBJECT_TAGS:
            tag_changed_record = dedupe_field(record, tag, index=index, bibnb=bibnb)
            # Temp varaible to avoid changing record_was_changed back to False
            if tag_changed_record:
                record_was_changed = True
        
        # If the record was not changed, log and go to next record
        if not record_was_changed:
            # Output the info in error file as records sent to the script should change
            ERRORS_FILE.write(Error_Types.RECORD_WAS_NOT_CHANGED, index=index, bibnb=bibnb)
            LOG.record_message(Level.INFO, index, bibnb, "Record was not changed")
            continue

        # If the record was changed, send the edited one to Koha via PUT API
        update_response = KOHA.update_biblio(bibnb, record=record.as_marc())
        # An error occured while getting the record, log & skip to next one
        if type(update_response) == Koha_Api_Errors:
            ERRORS_FILE.write(Error_Types.REQUESTS_PUT_ERROR, index=index, bibnb=bibnb, msg=update_response.name)
            LOG.record_message(Level.ERROR, index, bibnb, f"An error happened with the API trying to update the record : {update_response.name}")
            continue

        # Report & log
        UPDATED_BIBNB_FILE.write(bibnb)
        LOG.record_message(Level.INFO, index, bibnb, "Record was updated without duplicates")

ERRORS_FILE.close()
DELETED_FIELD_FILE.close()   
UPDATED_BIBNB_FILE.close() 

LOG.big_message(Level.INFO, "<(^-^)> <(^-^)> Script fully executed without FATAL errors <(^-^)> <(^-^)>")    
