# -*- coding: utf-8 -*- 

# Coded for Koha 23.11

# external imports
import os
import dotenv
import csv
from typing import Dict, List
from enum import Enum, IntEnum
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
    AUTH_ID_HAS_NO_CURRENT_FIELD = 33

class AlphaScript_Priority(IntEnum):
    NONE = 0
    MID = 5
    TOP = 10

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
        self.headers = ["bibnb", "index", "tag", "auth_id", "field", "replaced_by"]
        self.writer = csv.DictWriter(self.file, extrasaction="ignore", fieldnames=self.headers, delimiter=";")
        self.writer.writeheader()

    def write(self, bibnb:int, index:int, tag:str, auth_id:str, field:pymarc.field.Field, replaced_by:pymarc.field.Field):
        # Use str to prevent crash if I'm stupid when coding
        self.writer.writerow({
            "bibnb":str(bibnb),
            "index":str(index),
            "tag":str(tag),
            "auth_id":str(auth_id),
            "field":marc_utils.field_as_string(field),
            "replaced_by":marc_utils.field_as_string(replaced_by)
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

class Preferred_Field(object):
    """Must be used after ensuring the field has at least 1 $9"""
    def __init__(self, field:pymarc.field.Field):
        self.id:str = get_auth_id(field)
        self.old_field:pymarc.field.Field = None
        self.current_field:pymarc.field.Field = None
        self.update_with_new_field(field)
    
    def update_with_new_field(self, field:pymarc.field.Field) -> bool:
        """Updates the authority with new field.
        Returns if the new field is used instead of the old one"""
        # If no current field was used, adds it and end here
        if self.current_field == None:
            self.current_field = field
            return True
        # If the field already existed, checks if there are PPN
        if len(field.get_subfields("3")) > 0:
            # Checks if current field has PPN
            # If not, replace the olf field
            if not self.has_ppn:
                self.__replace_current_field(field)
                return True
            # If there are PPN, checks which field is the closest to
            # the same of Koha ID & PPN
            if not self.nb_ppn_match_nb_ids:
                # If new field is closer to the perfect match, replace it
                if abs(len(field.get_subfields("9")) - len(field.get_subfields("3"))) < abs(self.nb_koha_id - self.nb_ppn):
                    self.__replace_current_field(field)
                    return True
                
                # If the difference bewten nb of PPN & nb of Koha ID is the
                # same between both check for $7 Alphabet/Script priority
                elif abs(len(field.get_subfields("9")) - len(field.get_subfields("3"))) == abs(self.nb_koha_id - self.nb_ppn):
                    if self.__new_field_has_alphascript_priority(field):
                        self.__replace_current_field(field)
                        return True
            # Current field has same nb of PPN as Koha ID, if new field
            # is in the same situation, check for $7 Alphabet/Script priority 
            if len(field.get_subfields("9")) == len(field.get_subfields("3")):
                if self.__new_field_has_alphascript_priority(field):
                    self.__replace_current_field(field)
                    return True
        # New field has no PPN, if current field also has no PPN :
        # -> check for $7 Alphabet/Script priority 
        if not self.has_ppn:
            if self.__new_field_has_alphascript_priority(field):
                self.__replace_current_field(field)
                return True   

        # By default, return False
        return False

    @property
    def nb_koha_id(self) -> int:
        """Returns the number of $9 in current field.
        Returns -1 if no current field is defined"""
        if self.current_field == None:
            return -1
        return len(self.current_field.get_subfields("9"))

    @property
    def nb_ppn(self) -> int:
        """Returns the number of $3 in current field.
        Returns -1 if no current field is defined"""
        if self.current_field == None:
            return -1
        return len(self.current_field.get_subfields("3"))

    @property
    def has_ppn(self) -> bool:
        """Returns if current field has PPN"""
        return self.nb_ppn > 0
    
    @property
    def nb_ppn_match_nb_ids(self) -> bool:
        """Returns if the number of PPN matches the number of IDs"""
        return self.nb_ppn == self.nb_koha_id

    @property
    def alphascript_priority(self) -> AlphaScript_Priority:
        """Returns current field Alphabet/Script priority"""
        if self.current_field == None:
            return AlphaScript_Priority.NONE
        return get_alphascript_priority(self.current_field)

    def __replace_current_field(self, field:pymarc.field.Field):
        self.old_field = self.current_field
        self.current_field = field
    
    def __new_field_has_alphascript_priority(self, field:pymarc.field.Field) -> bool:
        return get_alphascript_priority(field) > self.alphascript_priority

# ----------------- Functions definition -----------------
def get_auth_id(field:pymarc.field.Field) -> str:
    """Returns the auth id of a field"""
    return "-".join(field.get_subfields("9"))

def get_alphascript_priority(field:pymarc.field.Field) -> AlphaScript_Priority:
    """Returns the field alphabet/Script Priority.
    $7='ba0yba0y' > $7='ba' > $7=other / none"""
    if len(field.get_subfields("7")) < 1:
        return AlphaScript_Priority.NONE
    if field.get_subfields("7")[0] == "ba0yba0y":
        return AlphaScript_Priority.TOP
    elif field.get_subfields("7")[0] == "ba":
        return AlphaScript_Priority.MID
    return AlphaScript_Priority.NONE

def dedupe_field(record:pymarc.record.Record, tag:str, index:int=None, bibnb:int=None) -> bool:
    """Removes multiple occurence of fields sharing the same $9
    
    Returns a bool to know if the record was edited"""
    auth_id_index:Dict[str, Preferred_Field] = {}
    fields:List[pymarc.field.Field] = []
    for field in record.get_fields(tag):
        # If no authority ID, keep the field but log a warning
        if not field.get("9"):
            ERRORS_FILE.write(Error_Types.WARNING_FIELD_WITHOUT_AUTHORITY_ID, index=index, bibnb=bibnb, msg=marc_utils.field_as_string(field))
            LOG.record_message(Level.WARNING, index, bibnb, msg=f"Field without authority ID : {marc_utils.field_as_string(field)}")
            fields.append(field)
            continue
        # For info purpose, checks if multiple $9
        # RAMEAU terms might have multiple $9 ($a-$x), with different combination possible
        # 1.1 : Keeping this behaviour evenn if new class might have tools to deals wiht it better
        if len(field.get_subfields("9")) > 1:
            ERRORS_FILE.write(Error_Types.WARNING_MULTIPLE_AUTHORITY_ID_IN_ONE_FIELD, index=index, bibnb=bibnb, msg=marc_utils.field_as_string(field))
            LOG.record_message(Level.WARNING, index, bibnb, msg=f"Field has multiple authority ID : {marc_utils.field_as_string(field)}")
        # Get auth ID to check against index
        auth_id = get_auth_id(field)
        # If this auth_id does not exist, adds it to the index
        if not auth_id in auth_id_index:
            auth_id_index[auth_id] = Preferred_Field(field)
        # If it does exist, dedupes it
        else:
            changed = auth_id_index[auth_id].update_with_new_field(field)
            deleted_field = field
            if changed:
                deleted_field = auth_id_index[auth_id].old_field
                LOG.record_message(Level.INFO, index, bibnb, msg=f"Replacing preferred field for authority ID {auth_id} from {marc_utils.field_as_string(auth_id_index[auth_id].old_field)} to {marc_utils.field_as_string(auth_id_index[auth_id].current_field)}")
            # Log an info + report
            LOG.record_message(Level.INFO, index, bibnb, msg=f"Deduping on authority ID {auth_id} : {marc_utils.field_as_string(deleted_field)}")
            DELETED_FIELD_FILE.write(bibnb, index, tag, auth_id, deleted_field, auth_id_index[auth_id].current_field)
            continue
    
    # Once loop is over, for each defined auth_id, add the corretc field
    for auth_id in auth_id_index:
        if auth_id_index[auth_id].current_field != None:
            fields.append(auth_id_index[auth_id].current_field)
        else:
            ERRORS_FILE.write(Error_Types.AUTH_ID_HAS_NO_CURRENT_FIELD, index=index, bibnb=bibnb, msg=f"{auth_id} is defined in Index but has no current field")
            LOG.record_message(Level.ERROR, index, bibnb, msg=f"{auth_id} is defined in Index but has no current field")

    # Once all fields are selected, check if there were duplicates for this tag
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
