# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/09_server.ipynb.

# %% auto 0
__all__ = ['RequestId', 'CallbackSystem', 'CallbackType', 'CallbackTime', 'CallbackResponse', 'AsyncCallback',
           'FALLACY_TOOL_DESCRIPTION', 'MEMORY_TOOL_DESCRIPTION', 'FALLACIES', 'embeddings_openai', 'embeddings',
           'memory_tool', 'ApiMethodImplementation', 'ApiMethods', 'UserDescription', 'UserDescriptionWithStyle',
           'Request', 'Message', 'CommentRequest', 'process_comment_request', 'aprint', 'ContextRequest',
           'process_context_extraction_request', 'server']

# %% ../nbs/09_server.ipynb 2
import os
from typing import List, Tuple, Callable, Awaitable, Dict
from langchain.vectorstores.base import VectorStore
from langchain.schema.runnable import RunnableSequence
from langchain.chat_models.base import BaseChatModel
from langchain.embeddings.base import Embeddings
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from pydantic.dataclasses import dataclass
from datetime import datetime
import tiktoken
from pino_inferior.core import SERVER_OPENAI_API_KEYS, \
    OPENAI_FALLACY_MODEL, OPENAI_AGENT_MODEL, OPENAI_CONTEXT_MODEL, \
    SERVER_MAX_FALLACIES_LENGTH, SERVER_MAX_THREAD_LENGTH, \
    SERVER_MAX_CONTEXT_LENGTH, \
    SERVER_AGENT_MAX_ITERATIONS, \
    SERVER_MAX_CONTEXT_EXTRACTOR_POST_LENGTH, \
    SERVER_HOST, SERVER_PORT, \
    VECTOR_DB, VECTOR_DB_PARAMS, MEMORY_PARAMS, \
    OPENAI_MEMORY_EMBEDDER_MODEL, \
    read_file
from pino_inferior.fallacy import build_fallacy_detection_chain, read_fallacies, \
    FALLACIES_FNAME
from .models import aengine
from .memory import Memory
from .agent import RolePlayAgent, ToolDescription, \
    TOOLS_PROMPTS_DIR, \
    INPUT_FALLACY_QUERY, OUTPUT_FALLACY_QUERY, \
    INPUT_RETRIEVER_QUERY, OUTPUT_RETRIEVER_DOCUMENTS, \
    FallacyLengthConfig, \
    LengthConfig as AgentLengthConfig, \
    PromptMarkupConfig as AgentPromptMarkupConfig, \
    Message as AgentMessage, \
    AGENT_INPUT_TIME, AGENT_INPUT_CONTEXT, AGENT_INPUT_FALLACIES, \
    AGENT_INPUT_HISTORY, AGENT_INPUT_TOOLS, AGENT_INPUT_USERNAME, \
    AGENT_INPUT_CHARACTER, AGENT_INPUT_GOAL, AGENT_INPUT_STYLE_EXAMPLES, \
    AGENT_INPUT_STYLE_DESCRIPTION
from langchain_openai_limiter import LimitAwaitChatOpenAI, ChooseKeyChatOpenAI, \
    LimitAwaitOpenAIEmbeddings, ChooseKeyOpenAIEmbeddings
from .function_callbacks import LLMEventType, AsyncLLMCallback, \
    AsyncFunctionalStyleChatCompletionHandler
from pino_inferior.context_extractor import build_context_extractor_chain, \
    LengthConfig as ContextExtractorLengthConfig, \
    PromptMarkupConfig as ContextExtractorPromptMarkupConfig, \
    CONTEXT_INPUT_TEXT, CONTEXT_INPUT_POST_TIME, \
    CONTEXT_INPUT_GOALS, CONTEXT_INPUT_CURRENT_TIME, \
    CONTEXT_INPUT_USERNAME, CONTEXT_INPUT_CHARACTER, \
    CONTEXT_OUTPUT_CONTEXT
import traceback
from copy import copy
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from websockets.server import serve, WebSocketServerProtocol
from pydantic.tools import parse_obj_as
import json
from pydantic.json import pydantic_encoder

# %% ../nbs/09_server.ipynb 3
try:
    __file__
    IS_JUPYTER = False
except NameError:
    IS_JUPYTER = True

# %% ../nbs/09_server.ipynb 5
def _initialize_openai_chat_model(name: str, callbacks: List[AsyncFunctionalStyleChatCompletionHandler]) -> Tuple[ChatOpenAI, BaseChatModel]:
    gpt = ChatOpenAI(
        model_name=name,
        streaming=True,
    )
    limited_gpt = LimitAwaitChatOpenAI(chat_openai=gpt)
    choose_key_gpt = ChooseKeyChatOpenAI(openai_api_keys=SERVER_OPENAI_API_KEYS,
                                         chat_openai=limited_gpt,
                                         callbacks=callbacks,)
    return gpt, choose_key_gpt

# %% ../nbs/09_server.ipynb 6
def _initialize_openai_embedder_model(name: str) -> Tuple[OpenAIEmbeddings, Embeddings]:
    embedder = OpenAIEmbeddings(
        model=name,
    )
    limited_embedder = LimitAwaitOpenAIEmbeddings(openai_embeddings=embedder)
    choose_key_embedder = ChooseKeyOpenAIEmbeddings(openai_api_keys=SERVER_OPENAI_API_KEYS,
                                                    openai_embeddings=limited_embedder)
    return embedder, choose_key_embedder

# %% ../nbs/09_server.ipynb 7
def _parse_json_as(cls, json_text):
    return parse_obj_as(cls, json.loads(json_text))

# %% ../nbs/09_server.ipynb 9
@dataclass
class UserDescription:
    name: str
    character: str
    goals: str


@dataclass
class UserDescriptionWithStyle(UserDescription):
    style_examples: List[str]
    style_description: str

# %% ../nbs/09_server.ipynb 10
RequestId = int


@dataclass
class Request:
    id: RequestId

# %% ../nbs/09_server.ipynb 11
CallbackSystem = str
CallbackType = str
CallbackTime = datetime
CallbackResponse = str

AsyncCallback = Callable[[RequestId, CallbackSystem, CallbackType, CallbackTime, CallbackResponse], Awaitable[None]]

# %% ../nbs/09_server.ipynb 14
FALLACY_TOOL_DESCRIPTION = read_file(os.path.join(TOOLS_PROMPTS_DIR, "fallacy.txt"))
MEMORY_TOOL_DESCRIPTION = read_file(os.path.join(TOOLS_PROMPTS_DIR, "memory.txt"))
FALLACIES = read_fallacies(FALLACIES_FNAME)

# %% ../nbs/09_server.ipynb 15
@dataclass
class Message:
    author: str
    time: str
    content: str


@dataclass
class CommentRequest(Request):
    context: str
    history: List[Message]
    user: UserDescriptionWithStyle

# %% ../nbs/09_server.ipynb 16
def _initialize_fallacy_tool(llm: ChatOpenAI) -> Tuple[ToolDescription, RunnableSequence]:
    encoding = tiktoken.encoding_for_model(llm.model_name)
    length_config = FallacyLengthConfig(
        length_function=lambda text: len(encoding.encode(text)),
        max_messages_length=SERVER_MAX_THREAD_LENGTH,
        max_fallacies_length=SERVER_MAX_FALLACIES_LENGTH,
    )
    description = ToolDescription(
        name="fallacy",
        description=FALLACY_TOOL_DESCRIPTION,
        input_key=INPUT_FALLACY_QUERY,
        output_key=OUTPUT_FALLACY_QUERY,
    )
    chain = build_fallacy_detection_chain(llm, length_config)
    return description, chain

# %% ../nbs/09_server.ipynb 17
def _initialize_memory_tool(embedder: OpenAIEmbeddings) \
    -> Tuple[ToolDescription, RunnableSequence]:
    vector_store = VECTOR_DB(embedding_function=embedder, **VECTOR_DB_PARAMS)
    container = Memory(
        engine=aengine,
        vector_db=vector_store,
        **MEMORY_PARAMS
    )
    description = ToolDescription(
        name="memory",
        description=MEMORY_TOOL_DESCRIPTION,
        input_key=INPUT_RETRIEVER_QUERY,
        output_key=OUTPUT_RETRIEVER_DOCUMENTS,
    )
    chain = container.build_retriever_chain()
    return description, chain

# %% ../nbs/09_server.ipynb 18
embeddings_openai, embeddings = _initialize_openai_embedder_model(OPENAI_MEMORY_EMBEDDER_MODEL)
memory_tool = _initialize_memory_tool(embedder=embeddings)


def _initialize_agent(fallacy_callbacks: List[AsyncFunctionalStyleChatCompletionHandler],
                      agent_callbacks: List[AsyncFunctionalStyleChatCompletionHandler]) \
                         -> Tuple[ChatOpenAI, ChatOpenAI, OpenAIEmbeddings, RolePlayAgent]:
    fallacy_gpt, fallacy_llm = _initialize_openai_chat_model(OPENAI_FALLACY_MODEL, fallacy_callbacks)
    agent_gpt, agent_llm = _initialize_openai_chat_model(OPENAI_AGENT_MODEL, agent_callbacks)
    
    agent_gpt_encoding = tiktoken.encoding_for_model(agent_gpt.model_name)
    
    fallacy_tool = _initialize_fallacy_tool(fallacy_llm)
    
    tools = [fallacy_tool, memory_tool]

    agent = RolePlayAgent(
        tools=tools,
        lengths=AgentLengthConfig(
            cut_function=lambda text, length: agent_gpt_encoding.decode(agent_gpt_encoding.encode(text)[:length]),
            length_function=lambda text: len(agent_gpt_encoding.encode(text)),
            max_messages_length=SERVER_MAX_THREAD_LENGTH,
            max_context_length=SERVER_MAX_CONTEXT_LENGTH,
        ),
        prompt_markup=AgentPromptMarkupConfig(),
        llm=agent_llm,
        max_iter=SERVER_AGENT_MAX_ITERATIONS,
    )
    
    return fallacy_gpt, agent_gpt, embeddings_openai, agent

# %% ../nbs/09_server.ipynb 19
async def process_comment_request(request: CommentRequest, callback: AsyncCallback) -> None:
    async def _inner_callback(system: str, envent_type: str, time: datetime, content: str) -> None:
        await callback(request.id, system, envent_type, time, content)

    async def _fallacy_callback(event_type: LLMEventType, time: datetime, content: str) -> None:
        await _inner_callback("fallacy", event_type.value, time, content)

    async def _agent_callback(event_type: LLMEventType, time: datetime, content: str) -> None:
        await _inner_callback("agent", event_type.value, time, content)

    await _inner_callback("system", "START", datetime.now(), "")
    try:
        fallacy_gpt, agent_gpt, _, agent = _initialize_agent(
            [AsyncFunctionalStyleChatCompletionHandler(_fallacy_callback)],
            [AsyncFunctionalStyleChatCompletionHandler(_agent_callback)]
        )
        inputs = {
            AGENT_INPUT_TIME: datetime.now(),
            AGENT_INPUT_CONTEXT: request.context,
            AGENT_INPUT_FALLACIES: FALLACIES,
            AGENT_INPUT_HISTORY: [
                AgentMessage(message.author, pd.to_datetime(message.time), message.content)
                for message in request.history
            ],
            AGENT_INPUT_TOOLS: agent.tools,
            AGENT_INPUT_USERNAME: request.user.name,
            AGENT_INPUT_CHARACTER: request.user.character,
            AGENT_INPUT_GOAL: request.user.goals,
            AGENT_INPUT_STYLE_EXAMPLES: request.user.style_examples,
            AGENT_INPUT_STYLE_DESCRIPTION: request.user.style_description,
        }
        response = await agent.arun(inputs)
        await _inner_callback("system", "END", datetime.now(), response)
    except Exception as err:
        await _inner_callback("system", "ERROR", datetime.now(), traceback.format_exception(err))
        raise err

# %% ../nbs/09_server.ipynb 20
async def aprint(*args, **kwargs):
    print(*args, **kwargs)

# %% ../nbs/09_server.ipynb 23
@dataclass
class ContextRequest(Request):
    text: str
    time: str
    user: UserDescription

# %% ../nbs/09_server.ipynb 24
def _initialize_context_extractor(callbacks: List[AsyncFunctionalStyleChatCompletionHandler]) -> RunnableSequence:
    _, llm = _initialize_openai_chat_model(OPENAI_CONTEXT_MODEL, callbacks)
    encoding = tiktoken.encoding_for_model(llm.model_name)
    context_extractor = build_context_extractor_chain(
        llm,
        lengths=ContextExtractorLengthConfig(
            cut_function=lambda text, length: encoding.decode(encoding.encode(text)[:length]),
            length_function=lambda text: len(encoding.encode(text)),
            max_post_length=SERVER_MAX_CONTEXT_EXTRACTOR_POST_LENGTH,
            max_response_length=SERVER_MAX_CONTEXT_LENGTH,
        ),
        prompts=ContextExtractorPromptMarkupConfig()
    )
    return context_extractor

# %% ../nbs/09_server.ipynb 25
async def process_context_extraction_request(request: ContextRequest, callback: AsyncCallback) -> None:
    async def _inner_callback(system: str, envent_type: str, time: datetime, content: str) -> None:
        await callback(request.id, system, envent_type, time, content)
    
    async def _context_callback(event_type: LLMEventType, time: datetime, content: str) -> None:
        await _inner_callback("context", event_type.value, time, content)
    
    await _inner_callback("system", "START", datetime.now(), "")
    try:
        context_extractor = _initialize_context_extractor([
            AsyncFunctionalStyleChatCompletionHandler(_context_callback)
        ])
        response = await context_extractor.ainvoke({
            CONTEXT_INPUT_TEXT: request.text,
            CONTEXT_INPUT_POST_TIME: pd.to_datetime(request.time),
            CONTEXT_INPUT_GOALS: request.user.goals,
            CONTEXT_INPUT_CURRENT_TIME: datetime.now(),
            CONTEXT_INPUT_USERNAME: request.user.name,
            CONTEXT_INPUT_CHARACTER: request.user.character,
        })
        response_text = response[CONTEXT_OUTPUT_CONTEXT]
        await _inner_callback("system", "END", datetime.now(), response_text)
    except Exception as err:
        await _inner_callback("system", "ERROR", datetime.now(), traceback.format_exception(err))
        raise err

# %% ../nbs/09_server.ipynb 30
ApiMethodImplementation = Callable[[Request, AsyncCallback], Awaitable[None]]
ApiMethods = Dict[str, Tuple[ApiMethodImplementation, type]]

# %% ../nbs/09_server.ipynb 31
def _parse_message(methods: ApiMethods, message: str) -> Tuple[ApiMethodImplementation, Request]:
    method, params = message.split(" ", maxsplit=1)
    assert method in methods
    method_implementation, request_class = methods[method]
    request = _parse_json_as(request_class, params)
    return method_implementation, request    

# %% ../nbs/09_server.ipynb 33
async def server() -> None:
    methods = {
        "comment": (process_comment_request, CommentRequest),
        "context": (process_context_extraction_request, ContextRequest),
    }

    async def process(websocket: WebSocketServerProtocol) -> None:
        async def _send(id: RequestId,
                  callback_system: CallbackSystem,
                  callback_type: CallbackType,
                  time: CallbackTime,
                  response: CallbackResponse) -> None:
            await websocket.send(json.dumps({
                "id": id,
                "callbackSystem": callback_system,
                "callbackType": callback_type,
                "time": str(time),
                "response": response
            }))

        message: str
        # TODO: parallel
        async for message in websocket:
            handler, request = None, None
            try:
                handler, request = _parse_message(methods, message)
            except Exception as err:
                await _send(-1, "system", "ERROR", datetime.now(), f"Can't parse request: {traceback.format_exception(err)}")
            if handler is not None and request is not None:
                asyncio.create_task(handler(request, _send))
    
    async with serve(process, SERVER_HOST, SERVER_PORT):
        await asyncio.Future()  # run forever

# %% ../nbs/09_server.ipynb 34
if (__name__ == "__main__") and (not IS_JUPYTER):
    asyncio.run(server())
