# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/02_fallacies.ipynb.

# %% auto 0
__all__ = ['FALLACIES_FNAME', 'FALLACIES_PROMPT_DIR', 'INPUT_FALLACIES', 'INPUT_HISTORY', 'INPUT_CONTEXT', 'INPUT_QUERY',
           'INTERMEDIATE_FALLACIES_STR', 'INTERMEDIATE_HISTORY_STR', 'INTERMEDIATE_LAST_AUTHOR', 'OUTPUT_LLM_OUTPUT',
           'OUTPUT_SHORT_ANSWER', 'LLM_OUTPUT_MARKER', 'system_prompt', 'instruction_prompt', 'chat_prompt',
           'FallacyExample', 'Fallacy', 'read_fallacies', 'LengthConfig', 'build_fallacy_detection_chain']

# %% ../nbs/02_fallacies.ipynb 3
from .core import DATA_DIR, PROMPTS_DIR, OPENAI_API_KEY
from langchain.schema.runnable import RunnableSequence
from langchain.llms.openai import BaseLLM
from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chains.transform import TransformChain
from langchain.schema.messages import AIMessage, AIMessageChunk
import os
from dataclasses import dataclass
from typing import Union, List, Callable
import json
from datetime import datetime
from .message import Message
import tiktoken

# %% ../nbs/02_fallacies.ipynb 4
FALLACIES_FNAME = os.path.join(DATA_DIR, "fallacies.json")
FALLACIES_PROMPT_DIR = os.path.join(PROMPTS_DIR, "fallacies")

# %% ../nbs/02_fallacies.ipynb 5
INPUT_FALLACIES = "fallacies"
INPUT_HISTORY = "history"
INPUT_CONTEXT = "context"
INPUT_QUERY = "query"

INTERMEDIATE_FALLACIES_STR = "fallacies_str"
INTERMEDIATE_HISTORY_STR = "history_str"
INTERMEDIATE_LAST_AUTHOR = "last_message_author"

OUTPUT_LLM_OUTPUT = "llm_output"
OUTPUT_SHORT_ANSWER = "answer"

LLM_OUTPUT_MARKER = "Therefore"

# %% ../nbs/02_fallacies.ipynb 8
@dataclass
class FallacyExample:
    """
    Example of a logical fallacy
    """
    text: str # Statement
    response: str # Fallacy detector response, explaining why it is a fallacy

    def __str__(self) -> str:
        return f"Example: {self.text}\nExample Response: {self.response}"


@dataclass
class Fallacy:
    """
    Fallacy representation
    """
    name: str # Fallacy name (like "ad hominem" and so)
    description: str # Fallacy description
    example: Union[FallacyExample, None] # Fallacy example

    def __str__(self):
        result = f"# {self.name}\n\n{self.description}"
        if self.example:
            result += "\n\n" + str(self.example)
        return result
    

def read_fallacies(fname: str) -> List[Fallacy]:
    """
    Read the file with fallacies markup
    :param fname: File name. Should contain JSON representing a list of `Fallacy`
    :returns: Fallacies list
    """
    with open(fname, "r", encoding="utf-8") as src:
        data = json.load(src)
    result = []
    for item in data:
        if item.get("example"):
            example = FallacyExample(**item["example"])
        else:
            example = None
        fallacy = Fallacy(name=item["name"], description=item["description"], example=example)
        result.append(fallacy)
    return result

# %% ../nbs/02_fallacies.ipynb 11
system_prompt = SystemMessagePromptTemplate.from_template_file(
    os.path.join(FALLACIES_PROMPT_DIR, "system.txt"),
    input_variables=[]
)
instruction_prompt = HumanMessagePromptTemplate.from_template_file(
    os.path.join(FALLACIES_PROMPT_DIR, "instruction.txt"),
    input_variables=[INTERMEDIATE_FALLACIES_STR,
                     INTERMEDIATE_HISTORY_STR,
                     INTERMEDIATE_LAST_AUTHOR,
                     INPUT_CONTEXT,
                     INPUT_QUERY]
)
chat_prompt = ChatPromptTemplate.from_messages([system_prompt, instruction_prompt])

# %% ../nbs/02_fallacies.ipynb 15
def _stringify(row: dict,
               length_function: Callable[[str], int],
               max_fallacies_length: int,
               max_messages_length: int) -> dict:
    fallacies: List[Fallacy] = row[INPUT_FALLACIES]
    history: List[Message] = row[INPUT_HISTORY] # TODO: cut

    fallacies_str = "\n\n".join(map(str, fallacies))
    while True:
        history_str = "\n\n".join(map(str, history))
        if length_function(history_str) <= max_messages_length:
            break
        else:
            history = history[1:]
    assert len(history) > 0, f"History length became less than {max_messages_length} only after removing all messages"
    assert length_function(fallacies_str) <= max_fallacies_length, f"Too big fallacies representation. Expected up to {max_fallacies_length}, got {length_function(fallacies_str)}"

    return {
        INTERMEDIATE_FALLACIES_STR: fallacies_str,
        INTERMEDIATE_HISTORY_STR: history_str,
    }

# %% ../nbs/02_fallacies.ipynb 18
def _extract_last_user(row: dict) -> dict:
    history: List[Message] = row[INPUT_HISTORY]
    assert len(history) > 0
    return {
        INTERMEDIATE_LAST_AUTHOR: history[-1].author
    }

# %% ../nbs/02_fallacies.ipynb 21
def _extract_answer_from_cot(row: dict) -> dict:
    response: Union[AIMessage, AIMessageChunk] = row[OUTPUT_LLM_OUTPUT]
    text: str = response.content
    text = text.split(LLM_OUTPUT_MARKER)[-1]
    text = text.split(":", maxsplit=1)[-1]
    text = text.strip()
    return {
        OUTPUT_SHORT_ANSWER: text
    }

# %% ../nbs/02_fallacies.ipynb 23
@dataclass
class LengthConfig:
    """
    Fallacy detector text length configuration
    """
    length_function: Callable[[str], int] # Text length getter
    max_messages_length: int = 2048 # Max history size
    max_fallacies_length: int = 4096 # Max fallacy list representation size


def build_fallacy_detection_chain(llm: BaseLLM, lengths: LengthConfig) -> RunnableSequence:
    """
    Build a sequential chain invoking fallacy detection
    :param llm: Language model to use inside fallacy detector (like ChatOpenAI)
    :param lengths: Fallacy detector text length configuration
    :returns: Sequential chain consuming message history and returning LLM output (and extracted short answer).
    """
    def _stringify_transform(row: dict) -> dict:
        return _stringify(
            row,
            lengths.length_function,
            lengths.max_fallacies_length,
            lengths.max_messages_length,
        )

    stringify_transform = TransformChain(
        input_variables=[INPUT_FALLACIES, INPUT_HISTORY],
        output_variables=[INTERMEDIATE_FALLACIES_STR, INTERMEDIATE_HISTORY_STR],
        transform=_stringify_transform,
    )
    extract_last_user_transform = TransformChain(
        input_variables=[INPUT_HISTORY],
        output_variables=[INTERMEDIATE_LAST_AUTHOR],
        transform=_extract_last_user,
    )
    extract_answer_transform = TransformChain(
        input_variables=[OUTPUT_LLM_OUTPUT],
        output_variables=[OUTPUT_SHORT_ANSWER],
        transform=_extract_answer_from_cot,
    )
    return stringify_transform | \
        extract_last_user_transform | \
        chat_prompt | \
        llm | \
        extract_answer_transform
