from io import StringIO
import sys
from json_repair import repair_json
import logging 

logger = logging.getLogger()

class CustomStream(StringIO):
    pass
    
class STDOutCapture(object):
    def __init__(self, buffer: StringIO):
        self.orig = sys.stdout
        self.buffer = buffer 
 
    def __enter__(self):
        sys.stdout = self.buffer

    def __exit__(self, *_):
        sys.stdout = self.orig
        
def get_system_prompt() -> str:
    import os

    if os.path.exists('system_prompt.txt'):
        with open('system_prompt.txt', 'r') as fp:
            return fp.read()

    return ''

def repair_json_no_except(json_str: str) -> str:
    try:
        return repair_json(json_str)
    except:
        logger.info(f"failed to repair json string {json_str}")
        return json_str
