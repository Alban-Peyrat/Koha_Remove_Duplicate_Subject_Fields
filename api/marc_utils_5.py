# -*- coding: utf-8 -*- 

import pymarc
from typing import List, Tuple
import re

# ------------------------------ utils internal ------------------------------

def __get_all_subfield_values_as_list(field:pymarc.field.Field) -> List[str]:
    """Returns all subfield values (no matter the subfield code) as a list of string
    
    Takes as argument a pymarc Field"""
    return [elem.value for elem in field.subfields]

# ------------------------------ Gettign data ------------------------------

def get_years_in_specific_subfield(record:pymarc.record.Record, tag:str, code:str) -> List[int]:
    """Returns a list of ints containing the first 4 consecutive numbers in the specified field-subfield.
    
    Takes as argument :
        - record : the record object
        - tag {str}
        - code {str}"""
    
    dates = []
    for field in record.get_fields(tag):
        for subfield in field.get_subfields(code):
            years = re.findall(r"\b\d{4}\b", re.sub(r"(DL|COP\.|COPYRIGHT|COP|C)", "", subfield, flags=re.IGNORECASE))
            if len(years) > 0:
                dates.append(int(years[0]))
    return dates

def get_year_from_UNM_100(record:pymarc.record.Record, creation:bool=False) -> List[int]:
    """Returns a list of ints containing the position 9-12 or 0-3 of the 100$a if they are 4 consecutive numbers.
    
    Takes as argument :
        - record : the record object
        - creation {bool} : return record creation year and not publication year"""
    
    dates = []
    PATTERN = None
    if not creation:
        PATTERN = r"(?<=^.{9})\d{4}"
    else:
        PATTERN = r"^\d{4}"
    for field in record.get_fields("100"):
        for subfield in field.get_subfields("a"):
            years = re.findall(PATTERN, subfield)
            if len(years) > 0:
                dates.append(int(years[0]))
    return dates

def get_years_less_accurate(record:pymarc.record.Record, tag:str) -> List[int]:
    """Returns a list of ints containing the first 4 consecutive numbers in the specified field.
    
    Takes as argument :
        - record : the record object
        - tag {str}"""
    
    dates = []
    for field in record.get_fields(tag):
        for subfield in __get_all_subfield_values_as_list(field):
            years = re.findall(r"\d{4}", subfield)
            if len(years) > 0:
                dates.append(int(years[0]))
    return [date for date in dates if date > 1700 and date < 2100] #https://stackoverflow.com/questions/59925384/python-remove-elements-that-are-greater-than-a-threshold-from-a-list

def get_years(record:pymarc.record, tags:List[Tuple[str, str|None]]) -> List[int]:
    """Returns a list of ints containing either :
        - the first 4 consecutive numbers in the specified field-subfield
        - the first 4 consecutive numbers in the specified field concatenated
    
    Takes as argument :
        - record : the record object
        - tags : list of tuples of str : first value is the tag,
    second value is either the subfield code or None to use field concatenation one"""
    dates = []
    for tag_couple in tags:
        tag = tag_couple[0]
        code = tag_couple[1]
        if code == None:
            dates += get_years_less_accurate(record, tag)
        else:
            dates += get_years_in_specific_subfield(record, tag, code)
    return dates

# ------------------------------ Sort ------------------------------

def sort_fields_by_tag(record:pymarc.record.Record):
    """Sort the record fields by their tag"""
    record.fields = sorted(record.fields, key=lambda field: field.tag)

def __sort_subfields(subf_list:List[pymarc.field.Subfield], sort:List[str]) -> List[str]:
    """Sort a list of subfields and returns the new list :
    * If a subfield code is not in sort, its position will stay the same
    * If a subfield is in sort, it will be moved to that order
    * To sort at the end, use "*" as a code to separate values to use to sort at the beginning
    from values to use to sort at the end

    Takes as argument :
        - subf_list : subfields as given by pymarc.field.Field.subfields (list of pymarc.field.Subfield)
        - sort : a list of subfield codes (str)"""

    # Stores every existing subfield
    new_subf = []
    # get positive & negative sort
    positive_sort = []
    negative_sort = []
    if not "*" in sort:
        positive_sort = sort
    else:
        positive_sort = sort[:sort.index("*")]
        negative_sort = sort[sort.index("*")+1:len(sort)]
    
    # Positive sort
    for code in positive_sort:
        for subf in subf_list:
            if subf.code == code:
                new_subf.append(subf)

    # Default sort
    for subf in subf_list:
        if subf.code not in positive_sort + negative_sort:
            new_subf.append(subf)

    # Negative sort
    for code in negative_sort:
        for subf in subf_list:
            if subf.code == code:
                new_subf.append(subf)
    
    return new_subf

def sort_subfields_for_tag(record:pymarc.record.Record, tag:str, sort:list[str]):
    """Sort subfields for all field with this tag :
    * If a subfield code is not in sort, its position will stay the same
    * If a subfield is in sort, it will be moved to that order
    * To sort at the end, use "*" as a code to separate values to use to sort at the beginning
    from values to use to sort at the end

    Takes as argument :
        - record : the pymarc record
        - tag : the field tag to sort (str)
        - sort : a list of subfield codes (str)"""
    
    for field in record.get_fields(tag):
        field.subfields = __sort_subfields(field.subfields, sort)

# ------------------------------ Force ------------------------------

def force_indicators(record:pymarc.record.Record, tag:str, ind1:str=None, ind2:str=None):
    """Forces the indicators on every field with this tag in the record
    If one of the indicatior is None, keep its current value
    
    /!\\ Does not check if indicators are legal values

    Takes as argument :
        - record : a pymarc record
        - tag : the tag to check (str)
        - ind1 : first indicator (str), defaults to keeping the current one
        - ind2 : first indicator (str), defaults to keeping the current one"""
    for field in record.get_fields(tag):
        if ind1 is None:
            ind1 = field.indicator1
        if ind2 is None:
            ind2 = field.indicator2
        field.indicators = pymarc.field.Indicators(first=ind1, second=ind2)

# ------------------------------ Add ------------------------------

def add_missing_subfield_to_field(record:pymarc.record.Record, tag:str, code:str, val:str, pos:int=999):
    """Adds a subfield with this code with val to every field witht this tag only if the field
    does not already have a subfield with this code
    
    Takes as argument :
        - record : a pymarc record
        - tag : a field tag (str)
        - code : the subfield code (str)
        - val : the val to add
        - [OPTIONNAL] pos : the position if the subfield is added (default to 999)"""
    
    for field in record.get_fields(tag):
        if not code in field.subfields_as_dict():
            field.add_subfield(code, val, pos)

# ------------------------------ Edit ------------------------------

def edit_specific_repeatable_subfield_content_with_regexp(field:pymarc.field.Field, codes:List[str], pattern:str, repl:str) -> List[pymarc.field.Subfield]:
    """Apply a regexp substitution to all subfields of a code (no flag).
    Edits the field and also return the subfield list (as pymarc.field.Subfield)
    
    Takes as argument :
        - field : pymarc Field to edit
        - codes : list of codes to edit (str)
        - pattern : regexp pattern
        - repl : regexp sub pattern"""
    
    subf_list:List[pymarc.field.Subfield] = field.subfields
    new_subf = []
    for subf in subf_list:
        # If right codes, use the regex replace
        # Subfield are NammedTupples and those are IMMUTABLE /!\
        if subf.code in codes:
            new_subf.append(subf._replace(value=re.sub(pattern, repl, subf.value)))
        # Else, add the unedited subfield
        else:
            new_subf.append(subf)
            
    # Updates the field
    field.subfields = new_subf
    return new_subf

def edit_repeatable_subf_content_with_regexp_for_tag(record:pymarc.record.Record, tag:str, codes:List[str], pattern:str, repl:str):
    """Apply a regexp substitution to all subfields of a code (no flag).
    
    Takes as argument :
        - record : a pymarc record
        - tag : a field tag (str)
        - codes : list of codes to edit (str)
        - pattern : regexp pattern
        - repl : regexp sub pattern"""
    
    for field in record.get_fields(tag):
        edit_specific_repeatable_subfield_content_with_regexp(field, codes, pattern, repl)


def replace_specific_repeatable_subfield_content_not_matching_regexp(field:pymarc.field.Field, codes:List[str], pattern:str, repl:str) -> List[pymarc.field.Subfield]:
    """Replace all subfields of a code by a value if they do not match a regexp (no flag).
    Edits the field and also return the subfield list (as pymarc.field.Subfield)
    
    Takes as argument :
        - field : pymarc Field to edit
        - codes : list of codes to edit (str)
        - pattern : regexp pattern
        - repl : repalcement text"""
    
    subf_list:List[pymarc.field.Subfield] = field.subfields
    new_subf = []
    for subf in subf_list:
        # If right codes, check if the regex match
        if subf.code in codes:
            # If no match, rewrite using replacement string
            if not re.match(pattern, subf.value):
                new_subf.append(subf._replace(value=repl))
            # If match, add the unedited subfield
            else:
                new_subf.append(subf)
        # Else, add the unedited subfield
        else:
            new_subf.append(subf)

    # Updates the field
    field.subfields = new_subf
    return new_subf

def replace_repeatable_subf_content_not_matching_regexp_for_tag(record:pymarc.record.Record, tag:str, codes:List[str], pattern:str, repl:str):
    """Replace all subfields of a code by a value if they do not match a regexp (no flag).
    
    Takes as argument :
        - record : a pymarc record
        - tag : a field tag (str)
        - codes : list of codes to edit (str)
        - pattern : regexp pattern
        - repl : repalcement text"""
    
    for field in record.get_fields(tag):
        replace_specific_repeatable_subfield_content_not_matching_regexp(field, codes, pattern, repl)

def fix_7XX(record:pymarc.record.Record, prioritize_71X:bool=False):
    """Makes sure that only 1 7X0 is in the record and
    that there's at least one 7X0 if there are 7X1 or 7X2
     
    Takes as argument :
        - record : a pymarc record
        - [OPTIONNAL, False] prioritize_71X {bool} : priotize 70X
    instead of 71X"""
    prio_7X = "70"
    unprio_7X = "71"
    if prioritize_71X:
        prio_7X = "71"
        unprio_7X = "70"
    # if 700 & 710, keep the priotize ones
    all_7X0 = record.get_fields("700", "710")
    if len(all_7X0) > 1:
        # ↓ This is used to make sure we keep the first non prio
        # as a 0 in case the prio one don't have a 0 field
        has_prio_7X0 = len(record.get_fields(prio_7X + "0")) > 0
        first_occ = True
        for field in all_7X0:
            # i know I can nest things, but i like this better 
            if first_occ:
                if field.tag == unprio_7X + "0" and has_prio_7X0:
                    field.tag = unprio_7X + "1"
                elif field.tag == prio_7X + "0":
                    first_occ = False
                elif field.tag == unprio_7X + "0" and not has_prio_7X0:
                    first_occ = False
            else:
                field.tag = field.tag[:2] + "1"

    # Checks if there's a 7X0 if 7X1 are in the record
    if len(record.get_fields("700", "710")) == 0 and len(record.get_fields("701", "711", "702", "712")) > 0:
        # If there are, get the first field 
        for tag in [prio_7X + "1", unprio_7X + "1", prio_7X + "2", unprio_7X + "2"]:
            if len(record.get_fields(tag)) > 0:
                record.get_fields(tag)[0].tag = record.get_fields(tag)[0].tag[:2] + "0"
                break

# ------------------------------ Merge ------------------------------

def merge_all_fields_by_tag(record:pymarc.record.Record, tag:str, sort:List[str]=[]) -> pymarc.field.Field|None:
    """Merge ALL fields with the tag as one, sorting them if wanted
    Edits the record and also returns the new field
    Indicators used are from the first field
    
    Sorting :
        * If a subfield code is not in sort, its position will stay the same
        * If a subfield is in sort, it will be moved to that order
        * To sort at the end, use "*" as a code to separate values to use to sort at the beginning
        from values to use to sort at the end

    Takes as argument :
        - record : the pymarc record
        - tag : the field tag to merge (str)
        - sort : a list of subfield codes (str)"""
    
    # Return if no match
    if record.get_fields(tag) == []:
        return None
    # Create the new field
    new_field = pymarc.field.Field(tag, record.get_fields(tag)[0].indicators)
    # Stores every existing subfield
    curr_subf = []
    for field in record.get_fields(tag):
        curr_subf += field.subfields

    # Sort the subfields    
    new_field.subfields = __sort_subfields(curr_subf, sort)

    # Replace current fields by the new one
    record.remove_fields(tag)
    record.add_ordered_field(new_field)
    return new_field

def merge_all_subfields_with_code(record:pymarc.record.Record, tag:str, code:str, separator:str):
    """Merges all subfields with given code in every field with given tag.
    The position of the first subfield will be kept
    
    Takes as argument :
        - record : the pymarc record
        - tag : the field tag (str)
        - code : the subfield code to merge (str)
        - separator : the separtor to use between subfields (str)"""
    for field in record.get_fields(tag):
        value_list = field.get_subfields(code)
        # If no subfield with this code or only 1, skipp this field
        if len(value_list) < 2:
            continue
        consummed = False
        new_subfields = []
        # Iterate throguh all subfields
        for subf in field.subfields:
            # Ignore subfield if not the right code
            if subf.code != code:
                new_subfields.append(subf)
                continue
            # If first time seeign this subfield, change its value
            if not consummed:
                new_subfields.append(pymarc.Subfield(code, separator.join(value_list)))
                consummed = True
            # Delete the subfield if not forst occurrence
            # (Elif to avoid triggerring on 1st field)
            elif consummed:
                continue
        field.subfields = new_subfields

# ------------------------------ Split ------------------------------

def split_tags_if_multiple_specific_subfield(record:pymarc.record.Record, tag:str, code:str):
    """Splits a tag into multiple if there are multiple subfields with this code.
    Every other subfield is pasted with this one
    
    Takes as argument :
        - record : a pymarc record
        - tag : the tag to check (str)
        - code : the code to check (str)"""
    
    for field in record.get_fields(tag):
        # Leave if there is no subfield with this code
        if not code in field.subfields_as_dict():
            continue
        # Leave if there is only one subfield with this code
        if len(field.subfields_as_dict()[code]) < 2:
            continue
        # Get this subfield values
        vals = field.subfields_as_dict()[code]
        # Get all other subfield values
        other_subf = []
        for subf in field.subfields:
            if subf.code != code:
                other_subf.append(subf)
        # Append new field for each subfield
        for val in vals:
            # You NEED to copy the list because pymarc doesn't create a copy
            # 
            new_field = pymarc.field.Field(tag, field.indicators, subfields=other_subf.copy())
            new_field.add_subfield(code, val)
            record.add_ordered_field(new_field)

        # Delete the original field
        record.remove_field(field)

def split_merged_tags(record:pymarc.record.Record, tag:str):
    """Splits a tag into multiple if there are multiple subfields with the same code.
    In case some tags do not have all subfields, copies the first occurence of this subfield
    
    Takes as argument :
        - record : a pymarc record
        - tag : the tag to check (str)"""
    
    for field in record.get_fields(tag):
        all_subf = field.subfields_as_dict()
        # Stores the highest number or a repeated subfield
        highest_repeat = 1
        for code in all_subf:
            if len(all_subf[code]) > highest_repeat:
                highest_repeat = len(all_subf[code])
        # Skip this field if all subfields are not repeated
        if highest_repeat < 1:
            continue

        # Creates the new fields
        for index in range(0, highest_repeat):
            new_field = pymarc.field.Field(tag=tag, indicators=field.indicators)
            # Add every subfield
            for code in all_subf:
                # Index is not superior to maximum subfields for this code
                if index < len(all_subf[code]):
                    new_field.add_subfield(code, all_subf[code][index])
                # Index is out of range, defaults to the first subfield
                else:
                    new_field.add_subfield(code, all_subf[code][0])
            # Add the new field to the record
            record.add_ordered_field(new_field)

        # Delete the original field
        record.remove_field(field)

# ------------------------------ Delete ------------------------------
    
def delete_empty_subfields(record:pymarc.record.Record):
    "Deletes every empty subfields"
    for field in record:
        # Skip control fields
        if field.is_control_field():
            continue
        # If something is empty
        if "" in __get_all_subfield_values_as_list(field):
            # Don't use delete subfield, it deletes the first occurrence found
            new_subf_list = []
            # Loop thorugh all subfields and copy those with values
            for subf in field.subfields:
                if subf.value != "":
                    new_subf_list.append(subf)
            # Replace current subfields by the new list
            field.subfields = new_subf_list

def delete_empty_fields(record:pymarc.record.Record):
    "Deletes every empty fields"
    for field in record:
        # Control fields
        if field.is_control_field():
            if field.data == "":
                record.remove_field(field)
        # Data fields
        else:
            if field.subfields == []:
                record.remove_field(field)


def delete_field_if_all_subfields_match_regexp(record:pymarc.record.Record, tag:str, code:str, pattern:str, keep_if_no_subf:bool=True):
    """For all fields with given tag, delete the entire field if ALL subfields with this code match the regexp.
    
    Takes as argument :
        - record : a pymarc record
        - tag : the tag to check (str)
        - code : the code to check (str)
        - pattern : the regexp pattern to check
        - [OPTIONNAL, True] keep_if_no_subf : if set to false, deletes the field if
    no subfield had the code"""

    for field in record.get_fields(tag):
        # If the field is not here, keep or del (yeah nesting "if" was not necessary but easier to read)
        # Why do I yap like that ?
        if not code in field.subfields_as_dict():
            if keep_if_no_subf:
                continue
            else:
                record.remove_field(field)
                continue
        
        # The field has subfields for this code
        delete = True
        for content in field.subfields_as_dict()[code]:
            # At least one of the subfied does not match, keep the field
            if not re.match(pattern, content):
                delete = False
        
        if delete:
            record.remove_field(field)


def delete_multiple_subfield_for_tag(record:pymarc.record.Record, tag:str, code:str):
    """Only keeps the first subfield with this code of all fields with this tag
    
    Takes as argument :
        - record : a pymarc record
        - tag : the tag to check (str)
        - code : the code to check (str)"""
    
    for field in record.get_fields(tag):
        # Leave if there is no subfield with this code
        if not code in field.subfields_as_dict():
            continue
        # Don't use delete subfield, it deletes the first occurrence found
        first = True
        new_subf_list = []
        # Loop thorugh all subfields and copy those with values
        for subf in field.subfields:
            if subf.code != code:
                new_subf_list.append(subf)
            # Do not merge this elif, you need to set first to false only if it's the first occurrence of THIS subfield
            elif subf.code == code and first:
                new_subf_list.append(subf)
                first = False
        # Replace current subfields by the new list
        field.subfields = new_subf_list

# ------------------------------ Debug ------------------------------

def field_as_string(field:pymarc.field.Field) -> str:
    """Returns the field as a string in WinIBW style.
    /!\\ This means that blank indicators are turned to #"""
    if field.control_field:
        return f"{field.tag} {field.data}"
    subf_as_string = []
    for subf in field.subfields:
        subf_as_string.append("$" + subf.code + subf.value)
    ind1 = field.indicator1
    if ind1 == " ":
        ind1 = "#"
    ind2 = field.indicator2
    if ind2 == " ":
        ind2 = "#"
    return f"{field.tag} {ind1}{ind2}{''.join(subf_as_string)}"

def record_as_string(record:pymarc.record.Record) -> str:
    """Returns the entire record as a string in WinIBW style
    /!\\ This means that blank indicators are turned to #"""
    fields_as_string = []
    for field in record.fields:
        fields_as_string.append(field_as_string(field))
    return "\n".join(fields_as_string)