# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['PACKAGE_DIR', 'DATA_DIR', 'PROMPTS_DIR', 'SQLALCHEMY_CONNECTION_STRING', 'OPENAI_API_KEY', 'VECTOR_DB_NAME',
           'VECTOR_DB', 'VECTOR_DB_PARAMS', 'MEMORY_PARAMS']

# %% ../nbs/00_core.ipynb 2
import langchain.vectorstores
import json

# %% ../nbs/00_core.ipynb 3
import nest_asyncio

nest_asyncio.apply()

# %% ../nbs/00_core.ipynb 4
import os
from dotenv import load_dotenv

# %% ../nbs/00_core.ipynb 5
try:
    __file__
    _IS_JUPYTER = False
except NameError:
    _IS_JUPYTER = True

# %% ../nbs/00_core.ipynb 6
if _IS_JUPYTER:
    PACKAGE_DIR = os.path.join(os.getcwd(), "..", "pino_inferior")
else:
    PACKAGE_DIR = os.path.dirname(__file__)
PACKAGE_DIR = os.path.abspath(PACKAGE_DIR)
PACKAGE_DIR

# %% ../nbs/00_core.ipynb 7
DATA_DIR = os.path.join(PACKAGE_DIR, "data")
DATA_DIR

# %% ../nbs/00_core.ipynb 8
PROMPTS_DIR = os.path.join(PACKAGE_DIR, "prompts")
PROMPTS_DIR

# %% ../nbs/00_core.ipynb 9
def _load_dotenv():
    path = os.getcwd()
    while path != os.path.dirname(path):
        dotenv_file = os.path.join(path, ".env")
        if os.path.exists(dotenv_file):
            load_dotenv(dotenv_file)
            return
        path = os.path.dirname(path)
    raise ValueError("Can't load .env file")

_load_dotenv()

# %% ../nbs/00_core.ipynb 10
SQLALCHEMY_CONNECTION_STRING = os.environ["SQLALCHEMY_CONNECTION"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# %% ../nbs/00_core.ipynb 11
VECTOR_DB_NAME = os.environ["VECTOR_DB"]
VECTOR_DB = getattr(langchain.vectorstores, VECTOR_DB_NAME)
VECTOR_DB_PARAMS = json.loads(os.environ["VECTOR_DB_PARAMS"])

# %% ../nbs/00_core.ipynb 12
MEMORY_PARAMS = json.loads(os.environ["MEMORY_PARAMS"])
