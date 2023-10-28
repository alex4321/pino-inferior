# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/07_agent.ipynb.

# %% auto 0
__all__ = ['AGENT_PROMPTS_DIR', 'TOOLS_PROMPTS_DIR', 'AGENT_INPUT_HISTORY', 'AGENT_INPUT_TOOLS', 'AGENT_INPUT_CONTEXT',
           'AGENT_INPUT_FALLACIES', 'AGENT_INPUT_USERNAME', 'AGENT_INPUT_CHARACTER', 'AGENT_INPUT_GOAL',
           'AGENT_INPUT_TIME', 'AGENT_INPUT_STYLE_EXAMPLES', 'AGENT_INPUT_STYLE_DESCRIPTION',
           'AGENT_INTERMEDIATE_HISTORY_STR', 'AGENT_INTERMEDIATE_TOOLS_STR', 'AGENT_INTERMEDIATE_TIME_STR',
           'AGENT_INTERMEDIATE_STYLE_EXAMPLES', 'agent_system_prompt', 'agent_instruction_prompt', 'agent_llm_prompt',
           'ToolDescription', 'build_stringification_chain', 'LLMOutputParseError']

# %% ../nbs/07_agent.ipynb 4
import os
from typing import List, Tuple, Union, Dict
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, \
    ChatPromptTemplate
from .models import aengine
from .core import PROMPTS_DIR, OPENAI_API_KEY, VECTOR_DB, VECTOR_DB_PARAMS, MEMORY_PARAMS
from .message import Message
from .memory import Memory, INPUT_RETRIEVER_QUERY, OUTPUT_RETRIEVER_DOCUMENTS
from langchain.schema.runnable import RunnableSequence
from langchain.chains import TransformChain
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Milvus
from dataclasses import dataclass
from langchain.chat_models import ChatOpenAI
from langchain.schema import AIMessage
from langchain.prompts.chat import ChatPromptValue
from .fallacy import build_fallacy_detection_chain, LengthConfig as FallacyLengthConfig, \
    read_fallacies, FALLACIES_FNAME, \
    INPUT_QUERY as INPUT_FALLACY_QUERY, OUTPUT_SHORT_ANSWER as OUTPUT_FALLACY_QUERY
from datetime import datetime
from langchain.chat_models.base import BaseChatModel
from enum import Enum
from typing import Callable
import asyncio
import tiktoken
from datetime import datetime
from dataclasses import dataclass

# %% ../nbs/07_agent.ipynb 5
AGENT_PROMPTS_DIR = os.path.join(PROMPTS_DIR, "roleplay_agent")
TOOLS_PROMPTS_DIR = os.path.join(AGENT_PROMPTS_DIR, "tools")

# %% ../nbs/07_agent.ipynb 6
def _read_file(fname: str) -> str:
    with open(fname, "r", encoding="utf-8") as src:
        return src.read()

# %% ../nbs/07_agent.ipynb 7
AGENT_INPUT_HISTORY = "history"
AGENT_INPUT_TOOLS = "tools"
AGENT_INPUT_CONTEXT = "context"
AGENT_INPUT_FALLACIES = "fallacies"
AGENT_INPUT_USERNAME = "name"
AGENT_INPUT_CHARACTER = "character"
AGENT_INPUT_GOAL = "goals"
AGENT_INPUT_TIME = "time"
AGENT_INPUT_STYLE_EXAMPLES = "style_examples"
AGENT_INPUT_STYLE_DESCRIPTION = "style_description"

AGENT_INTERMEDIATE_HISTORY_STR = "input_str"
AGENT_INTERMEDIATE_TOOLS_STR = "tools_str"
AGENT_INTERMEDIATE_TIME_STR = "time_str"
AGENT_INTERMEDIATE_STYLE_EXAMPLES = "style_examples_str"

# %% ../nbs/07_agent.ipynb 9
@dataclass
class ToolDescription:
    name: str
    description: str
    input_key: Union[str, None]
    output_key: str

# %% ../nbs/07_agent.ipynb 11
agent_system_prompt = SystemMessagePromptTemplate.from_template(_read_file(
    os.path.join(AGENT_PROMPTS_DIR, "system.txt")
))
agent_instruction_prompt = HumanMessagePromptTemplate.from_template(_read_file(
    os.path.join(AGENT_PROMPTS_DIR, "instruction.txt")
))
agent_llm_prompt = ChatPromptTemplate.from_messages([agent_system_prompt, agent_instruction_prompt])

# %% ../nbs/07_agent.ipynb 12
def build_stringification_chain(
        length_function: Callable[[str], int],
        max_messages_length: int,
        max_tools_length: int,
        max_context_length: int,
        max_username_length: int,
        max_character_length: int,
        max_goal_length: int,
        max_style_examples_length: int,
        max_style_description_length: int,
) -> TransformChain:
    def _stringify_messages(row):
        messages: List[Message] = row[AGENT_INPUT_HISTORY]
        while True:
            messages_str = "\n\n".join(map(str, messages))
            if length_function(messages_str) <= max_messages_length:
                break
            else:
                messages = messages[1:]
        assert len(messages) > 0, \
            f"Only after cutting all the messages total length become less than {max_messages_length}"
        return messages_str
    
    def _stringify_tools(row):
        tools: List[Tuple[ToolDescription, RunnableSequence]] = row[AGENT_INPUT_TOOLS]
        tools_str = "\n\n".join([
            f"-- {tool.name}: {tool.description}"
            for tool, _ in tools
        ])
        assert length_function(tools_str) <= max_tools_length, \
            f"Total size of tools description should be lower than {max_tools_length}"
        return tools_str
        
    def _stringify_time(row):
        time: datetime = row[AGENT_INPUT_TIME]
        return time.strftime("%d %b %Y %H:%M")
    
    def _stringify_style_examples(row):
        examples: List[str] = row[AGENT_INPUT_STYLE_EXAMPLES]
        examples_str = "\n\n".join(examples)
        assert length_function(examples_str) <= max_style_examples_length, \
            f"Total size of style exampes should be lower than {max_style_examples_length}"
        return examples_str    

    def agent_stringify(row):
        messages_str = _stringify_messages(row)
        tools_str = _stringify_tools(row)
        time_str = _stringify_time(row)
        style_examples_str = _stringify_style_examples(row)
        
        assert length_function(row[AGENT_INPUT_CONTEXT]) <= max_context_length
        assert length_function(row[AGENT_INPUT_USERNAME]) <= max_username_length
        assert length_function(row[AGENT_INPUT_CHARACTER]) <= max_character_length
        assert length_function(row[AGENT_INPUT_GOAL]) <= max_goal_length
        assert length_function(row[AGENT_INPUT_STYLE_DESCRIPTION]) <= max_style_description_length

        return {
            AGENT_INTERMEDIATE_HISTORY_STR: messages_str,
            AGENT_INTERMEDIATE_TOOLS_STR: tools_str,
            AGENT_INTERMEDIATE_TIME_STR: time_str,
            AGENT_INTERMEDIATE_STYLE_EXAMPLES: style_examples_str
        }
    
    async def aagent_stringify(row):
        return agent_stringify(row)
    
    return TransformChain(
        transform=agent_stringify,
        atransform=aagent_stringify,
        input_variables=[
            AGENT_INPUT_HISTORY,
            AGENT_INPUT_TOOLS,
            AGENT_INPUT_CONTEXT,
            AGENT_INPUT_USERNAME,
            AGENT_INPUT_CHARACTER,
            AGENT_INPUT_GOAL,
            AGENT_INPUT_TIME,
            AGENT_INPUT_STYLE_EXAMPLES,
            AGENT_INPUT_STYLE_DESCRIPTION,
        ],
        output_variables=[
            AGENT_INTERMEDIATE_HISTORY_STR,
            AGENT_INTERMEDIATE_TOOLS_STR,
            AGENT_INTERMEDIATE_TIME_STR,
            AGENT_INTERMEDIATE_STYLE_EXAMPLES,
        ],
    )

# %% ../nbs/07_agent.ipynb 15
async def _arun_agent_llm(agent_prompt: ChatPromptTemplate,
                          agent_llm: BaseChatModel,
                          tool_call_stop_sequence: str,
                          response_stop_sequence: str) -> str:
    response = await agent_llm.ainvoke(
        agent_prompt,
        stop=[tool_call_stop_sequence, response_stop_sequence]
    )
    return response.content

# %% ../nbs/07_agent.ipynb 17
def _split_by_marker(text: str, open_marker: str, close_marker: str) -> List[str]:
    blocks = text.split(open_marker)
    before_last_open_marker = open_marker.join(blocks[:-1])
    before_last_close_marker = blocks[-1].split(close_marker)[0]
    return before_last_open_marker, before_last_close_marker

# %% ../nbs/07_agent.ipynb 18
class _NextAction:
    TOOL = 1
    RESPONSE = 2
    UNKNOWN = 3


@dataclass
class _ParsedResponse:
    chain_of_thoughts: str
    next_action: _NextAction
    next_action_type: str
    next_action_query: str

# %% ../nbs/07_agent.ipynb 19
class LLMOutputParseError(ValueError):
    def __init__(self, output: str):
        super(LLMOutputParseError, self).__init__(
            f"LLM output parsing error: {output}"
        )

# %% ../nbs/07_agent.ipynb 20
def _parse_agent_output(response: str, tools: List[ToolDescription], response_marker: str) -> _ParsedResponse:
    for tool in tools:
        tool_open_marker = f"[{tool.name}]"
        tool_close_marker = f"[/{tool.name}]"
        if response.endswith(tool_close_marker):
            chain_of_thoughts, query = _split_by_marker(response,
                                                        tool_open_marker,
                                                        tool_close_marker)
            return _ParsedResponse(
                chain_of_thoughts=chain_of_thoughts,
                next_action=_NextAction.TOOL,
                next_action_type=tool.name,
                next_action_query=query
            )
    response_open_marker = f"[{response_marker}]"
    response_close_marker = f"[/{response_marker}]"
    if response_open_marker in response:
        chain_of_thoughts, response = _split_by_marker(response,
                                                       response_open_marker,
                                                       response_close_marker)
        return _ParsedResponse(
            chain_of_thoughts=chain_of_thoughts,
            next_action=_NextAction.RESPONSE,
            next_action_type="",
            next_action_query=response,
        )
    raise LLMOutputParseError(response)

# %% ../nbs/07_agent.ipynb 21
def _extract_tool_representations(tools: List[Tuple[ToolDescription, RunnableSequence]]) -> Tuple[List[ToolDescription], Dict[str, Tuple[ToolDescription, RunnableSequence]]]:
    tool_descriptions = [
        description
        for description, _ in tools
    ]
    tools_by_name = {
        description.name: (description, tool)
        for description, tool in tools
    }
    return tool_descriptions, tools_by_name


def _process_tool(inputs: dict, response: _NextAction, tools_by_name: Dict[str, Tuple[ToolDescription, RunnableSequence]]) \
    -> Tuple[dict, RunnableSequence, str, str]:
    assert response.next_action_type in tools_by_name
    tool_description, tool_chain = tools_by_name[response.next_action_type]
    tool_inputs = dict(inputs, **{tool_description.input_key: response.next_action_query})
    return tool_inputs, tool_chain, tool_description.output_key, tool_description.name


async def _process_tool_response(tool_name: str,
                                 query: str,
                                 output: str,
                                 tool_call_stop_sequence: str,
                                 tool_call_close_sequence: str,
                                 tool_length_function: Callable[[str], int],
                                 tool_cut_function: Callable[[str, int], str],
                                 tool_query_max_length: int,
                                 tool_response_max_length: int) \
                                    -> Tuple[str, None, bool]:
    if tool_length_function(query) > tool_query_max_length:
        query = tool_cut_function(query, tool_query_max_length)
    if tool_length_function(output) > tool_response_max_length:
        output = tool_cut_function(output, tool_response_max_length)
    suffix = f"[{tool_name}]{query}[/{tool_name}]" + \
        f"{tool_call_stop_sequence}\n" + \
        f"```\n{output}\n```\n" + \
        f"{tool_call_close_sequence}"
    final_response = None
    continue_further = True
    return suffix, final_response, continue_further


async def _aprocess_agent_iteration_output(
        inputs: dict,
        llm_output: str,
        tool_call_stop_sequence: str,
        tool_call_close_sequence: str,
        tools: List[Tuple[ToolDescription, RunnableSequence]],
        tool_length_function: Callable[[str], int],
        tool_cut_function: Callable[[str, int], str],
        tool_query_max_length: int,
        tool_response_max_length: int,
        response_marker: str,
) -> Tuple[AIMessage, Union[str, None], bool]:
    tool_descriptions, tools_by_name = _extract_tool_representations(tools)
    response = _parse_agent_output(llm_output, tool_descriptions, response_marker)
    assert response.next_action in {_NextAction.TOOL, _NextAction.RESPONSE}
    if response.next_action == _NextAction.TOOL:
        tool_inputs, tool_chain, tool_output_key, tool_name = _process_tool(inputs, response, tools_by_name)
        tool_output = (await tool_chain.ainvoke(tool_inputs))[tool_output_key]
        suffix, final_response, continue_further = await _process_tool_response(
            tool_name,
            response.next_action_query,
            tool_output,
            tool_call_stop_sequence,
            tool_call_close_sequence,
            tool_length_function,
            tool_cut_function,
            tool_query_max_length,
            tool_response_max_length,
        )
    elif response.next_action == _NextAction.RESPONSE:
        suffix = f"[{response_marker}]{response.next_action_query}[/{response_marker}]"
        final_response = response.next_action_query
        continue_further = False
    message = AIMessage(content=f"{response.chain_of_thoughts}{suffix}")
    return message, final_response, continue_further

# %% ../nbs/07_agent.ipynb 23
async def _arun_agent_iteration(inputs: dict,
                         agent_prompt: ChatPromptValue,
                         agent_llm: BaseChatModel,
                         tool_call_stop_sequence: str,
                         tool_call_close_sequence: str,
                         tools: List[Tuple[ToolDescription, RunnableSequence]],
                         tool_length_function: Callable[[str], int],
                         tool_cut_function: Callable[[str, int], str],
                         tool_query_max_length: int,
                         tool_response_max_length: int,
                         response_marker: str) -> Tuple[AIMessage, Union[str, None], bool]:
    llm_output = await _arun_agent_llm(
        agent_prompt=agent_prompt,
        agent_llm=agent_llm,
        tool_call_stop_sequence=tool_call_stop_sequence,
        response_stop_sequence=f"[/{response_marker}]",
    )
    return await _aprocess_agent_iteration_output(
        inputs,
        llm_output,
        tool_call_stop_sequence,
        tool_call_close_sequence,
        tools,
        tool_length_function,
        tool_cut_function,
        tool_query_max_length,
        tool_response_max_length,
        response_marker,
    )

# %% ../nbs/07_agent.ipynb 25
def _run_agent(inputs: dict,
               agent_input_preprocessor: RunnableSequence,
               agent_llm: BaseChatModel,
               tool_call_stop_sequence: str,
               tool_call_close_sequence: str,
               tools: List[Tuple[ToolDescription, RunnableSequence]],
               tool_length_function: Callable[[str], int],
               tool_cut_function: Callable[[str, int], str],
               tool_query_max_length: int,
               tool_response_max_length: int,
               response_marker: str,
               max_iteration_count: int,
               max_token_count: int) -> str:
    return asyncio.get_event_loop().run_until_complete(
        _arun_agent(
            inputs,
            agent_input_preprocessor,
            agent_llm,
            tool_call_stop_sequence,
            tool_call_close_sequence,
            tools,
            tool_length_function,
            tool_cut_function,
            tool_query_max_length,
            tool_response_max_length,
            response_marker,
            max_iteration_count,
            max_token_count,
        )
    )

    
async def _arun_agent(inputs: dict,
                      agent_input_preprocessor: RunnableSequence,
                      agent_llm: BaseChatModel,
                      tool_call_stop_sequence: str,
                      tool_call_close_sequence: str,
                      tools: List[Tuple[ToolDescription, RunnableSequence]],
                      tool_length_function: Callable[[str], int],
                      tool_cut_function: Callable[[str, int], str],
                      tool_query_max_length: int,
                      tool_response_max_length: int,
                      response_marker: str,
                      max_iteration_count: int,
                      max_token_count: int) -> str:
    chat_inputs: ChatPromptValue = await agent_input_preprocessor.ainvoke(inputs)
    ai_messages = []
    for _ in range(max_iteration_count):
        token_count_without_ai = agent_llm.get_num_tokens_from_messages(chat_inputs.messages)
        assert token_count_without_ai <= max_token_count, \
            f"Session length ({token_count_without_ai}) exceeds {max_iteration_count} limit"

        ai_message, final_response, continue_further = await _arun_agent_iteration(
            inputs,
            chat_inputs,
            agent_llm,
            tool_call_stop_sequence,
            tool_call_close_sequence,
            tools,
            tool_length_function,
            tool_cut_function,
            tool_query_max_length,
            tool_response_max_length,
            response_marker
        )
        ai_messages.append(ai_message)
        chat_inputs.messages.append(ai_message)

        if continue_further:
            token_count_with_ai = agent_llm.get_num_tokens_from_messages(chat_inputs.messages)
            assert token_count_with_ai <= max_token_count, \
                f"With latest AI message session length ({token_count_with_ai}) exceeds {max_token_count} while no response achieved"
            continue
        assert final_response is not None, "Did not got final response"
        return final_response
    raise ValueError(f"Did not got final LLM response after {max_iteration_count} iterations")
