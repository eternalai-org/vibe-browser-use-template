from browser_use import Controller
from .models import browser_use_custom_models
from pydantic import BaseModel

_controler = Controller(
    output_model=browser_use_custom_models.FinalAgentResult
)

def get_controler():
    return _controler

# register custom function here
...