# Remove duplicate subject fields from Koha records

[![Active Development](https://img.shields.io/badge/Maintenance%20Level-Actively%20Developed-brightgreen.svg)](https://gist.github.com/cheerfulstoic/d107229326a01ff0f333a1d3476e068d)

This application is used to remove duplicate subject fields from MARC bibliographic records using Koha 23.11 REST APIs.

An additional script (`prep_list.py`, a quickly repurposed `AR108_duplicates_subject_id`) filters the result of a SQL report merging in one column all the authority IDs, outputing the list of of biblionumber containing duplicates authorities ID.
SQL report example :

<!-- report ID 1500 -->

```SQL
SELECT biblionumber,
    ExtractValue(metadata, CONCAT('//datafield[@tag="',  TRIM(<<Field Tag>>), '"]/subfield[@code="', TRIM(<<Subfield Code>>), '"]')) AS subfield

FROM biblio_metadata
```

## Requirements

* Uses `pymarc` 5.2.0

Included in the repository :

* [`Alban-Peyrat/Koha_API_interface/Koha_REST_API_Client.py`](https://github.com/Alban-Peyrat/Koha_API_interface/blob/main/Koha_REST_API_Client.py) 2025-02-18 version)
* [`Alban-Peyrat/Find_and_Compare_Records/func_file_check.py`](https://github.com/Alban-Peyrat/Find_and_Compare_Records/blob/master/func_file_check.py) (from version 2.0.1)
* [`Alban-Peyrat/Pymarc_utils/marc_utils_5.py`](https://github.com/Alban-Peyrat/Pymarc_utils/blob/main/marc_utils_5.py) (2024-12-13 version)
* `Alban-Peyrat/IPRAUS_integration/cl_log.py` (2024-11-21 version), based on `Archires_Auto_Koha_Report` 2024-09-25 version (based on FCR version 2.0.1)

## Environment variables

For `main.py` :

* Processing settings :
  * `SUBJECTS_TAG` : tags to check, as a list of ints, using `,` as separator
  * `RECORD_NB_LIMIT` : maximum number of record to process. Defaults to `500`
* Koha API settings :
  * `KOHA_URL` : Koha intranet domain name
  * `KOHA_CLIENT_ID` : Koha Client ID of an account with `catalogue` permission
  * `KOHA_CLIENT_SECRET` : Koha Client secret of an account with `catalogue` permission
* File settings :
  * `LOGS_FOLDER` : path to the folder containing the log file (file will be nammed `Koha_Remove_Subjects_Dupes.log`)
  * `LOG_LEVEL` : logging level to use : `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (`INFO` by default)
  * `INPUT_FILE` : input file containing a list of iblionumbers separated by line feed
  * `OUTPUT_PATH` : path to the folder containing the output files

For `prep_list.py` :

* `PREP_LIST_INPUT_FILE` : path to the file containing an extract of Koha data, needs columns `biblionumber` and `subfield` (see introduction for a report example)
* `PREP_LIST_OUTPUT_FILE` : path to the output file

## Script processing

### Effects of the script

![Flowchart of the script](./img/flowchart.png)

### Output files

_Note : all CSV files use `;` as separator._

`KRSD_update_bibnb.txt` contains all biblionumber that were actually updated.

`KRSD_deleted_fields.csv` contains all deleted fields, with columns :

* `bibnb` : biblinoumber of the record
* `index` : index of the record in the input file
* `tag` : tag of the deleted field
* `auth_id` : authority ID of the deleted field
* `field` : the entire field as a string

`KRSD_deleted_fields.csv` contains all errors or unexpected situation, with columns :

* `error_type` : the error type
  * `REQUESTS_GET_ERROR` : an error happenned while trying to retrieve the record. The message will have the name of the error
  * `SECURITY_STOP` : the maximum number of records was reached
  * `BIBNB_IS_INCORRECT` : biblionumber is incorrect (not a positive integer)
  * `NO_RECORD` : record is empty / invalid
  * `NO_BIBNB_IN_RECORD` : record does not have a `001` (as those are records retrieved from Koha, all should have one)
  * `FAILED_TO_PARSE_MARC` : failed to parse the record
  * `WARNING_FIELD_WITHOUT_AUTHORITY_ID` : warning (not an error), one of the analysed field did not have authority ID
  * `RECORD_WAS_NOT_CHANGED` : the record did not change (as the script should only be used on records that should change)
  * `WARNING_MULTIPLE_AUTHORITY_ID_IN_ONE_FIELD` : warning (not an error), one of the analysed field had multiple autority ID
* `index` : index of the record in the input file
* `bibnb` : biblinoumber of the record
* `message` : aditional message if necessary, errors (or warnings) on specific fields usually have the entire field as a string
