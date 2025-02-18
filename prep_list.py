# -*- coding: utf-8 -*- 

# external imports
import os
from dotenv import load_dotenv
import csv

# Internal import

load_dotenv()

FILE_IN = os.getenv("PREP_LIST_INPUT_FILE")
FILE_OUT = os.getenv("PREP_LIST_OUTPUT_FILE")

class Bibnb(object):
    def __init__(self, row:dict) -> None:
        self.bibnb:str = row["biblionumber"]
        self.input_ids:str = row["subfield"]
        self.id_list = self.input_ids.split()
        self.id_dict = {}
        self.analyse_input_ids()

    def analyse_input_ids(self):
        for authid in self.id_list:
            if not authid in self.id_dict:
                self.id_dict[authid] = 1
            else:
                self.id_dict[authid] += 1
    
    def to_dict(self):
        """Returns this bibnb as a dict"""
        output = {
            "biblinoumber":self.bibnb,
            "dupes":[]
        }
        no_dupes = []
        dupes = []
        for authid in self.id_dict:
            if self.id_dict[authid] < 2:
                no_dupes.append(authid)
            else:
                dupes.append(f"{authid} ({self.id_dict[authid]})")                
        output["dupes"] = ", ".join(dupes)
        return output

output = []
# Open input file
with open(FILE_IN, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=";")

    # For each line
    for row in reader:
        # Get row data
        data = Bibnb(row).to_dict()
        if data["dupes"] != "":
            data.pop("dupes")
            output.append(data)

# Write lines with duplicates to a new CSV file
with open(FILE_OUT, "w", encoding='utf-8', newline="") as f:
    headers = ["biblinoumber"]
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(output)
