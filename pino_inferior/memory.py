# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/04_retriever.ipynb.

# %% auto 0
__all__ = ['TEXT_HASH_COLUMN', 'INPUT_RETRIEVER_QUERY', 'INTERMEDIATE_RETRIEVER_DOCUMENTS', 'OUTPUT_RETRIEVER_DOCUMENTS',
           'BLACKLISTED_META_PROPERTIES', 'ScoreProcessing', 'md5string', 'ParagraphSplitter', 'SentenceSplitter',
           'SequentialSplitter', 'Memory']

# %% ../nbs/04_retriever.ipynb 3
import re
from typing import List, Set, Dict, Callable, Tuple, Union
import hashlib
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import MarkdownHeaderTextSplitter, Document
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema.embeddings import Embeddings
from langchain.schema.vectorstore import VectorStore
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .core import OPENAI_API_KEY, VECTOR_DB, VECTOR_DB_PARAMS, MEMORY_PARAMS
from .models import aengine, ParagraphMemoryRecord
from datetime import datetime
from langchain.schema.runnable import RunnableSequence
from langchain.chains import TransformChain
import pandas as pd
import asyncio

# %% ../nbs/04_retriever.ipynb 5
TEXT_HASH_COLUMN = "ParagraphHash"

# %% ../nbs/04_retriever.ipynb 6
def md5string(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

# %% ../nbs/04_retriever.ipynb 7
class ParagraphSplitter:
    def split_text(self, text: str) -> List[Document]:
        return [
            Document(page_content=item, metadata={TEXT_HASH_COLUMN: f"{md5string(item)}"})
            for item in text.split("\n")
        ]

# %% ../nbs/04_retriever.ipynb 8
class SentenceSplitter:
    def __init__(self):
        self.separators=["\.\s", "\?", "\!"]
    
    def _split_rest_separators(self, text: str, separators: List[str]) -> List[Document]:
        if len(separators) == 0:
            return [Document(page_content=text, metadata={})]
        current_separator = separators[0]
        next_separators = separators[1:]
        result = []
        for item in re.split(current_separator, text):
            result += self._split_rest_separators(item, next_separators)
        return result

    def split_text(self, text: str) -> List[Document]:
        return self._split_rest_separators(text, self.separators)

# %% ../nbs/04_retriever.ipynb 9
class SequentialSplitter:
    def __init__(self, splitters: list) -> None:
        self.splitters = splitters

    def _split_inner(self, text: str, rest_splitters: list) -> List[Document]:
        if len(rest_splitters) == 0:
            return [Document(page_content=text, metadata={})]
        current_splitter = rest_splitters[0]
        next_splitters = rest_splitters[1:]
        result = []
        for item in current_splitter.split_text(text):
            if isinstance(item, str):
                item = Document(page_content=item, metadata={})
            metadata = item.metadata
            for record in self._split_inner(item.page_content, next_splitters):
                result.append(Document(
                    page_content=record.page_content,
                    metadata=dict(metadata, **record.metadata)
                ))
        return result

    def split_text(self, text: str) -> List[Document]:
        return self._split_inner(text, self.splitters)

# %% ../nbs/04_retriever.ipynb 11
async def _remove_known_paragraphs(session: AsyncSession, paragraphs: List[Document]) -> List[Document]:
    """
    Filter a paragraph to remember only new ones (paragraphs might be shared between documents)
    """
    # Query by paragraph MD5
    hashes = set()
    for document in paragraphs:
        assert TEXT_HASH_COLUMN in document.metadata
        hash = document.metadata[TEXT_HASH_COLUMN]
        hashes.add(hash)
    sql_query = select(ParagraphMemoryRecord).filter(
        ParagraphMemoryRecord.md5.in_(hashes)
    )
    sql_search = await session.scalars(sql_query)
    # Build a set of md5-text pairs to filter only the non-known combinations
    #  (can't be just md5 because of potential collisions)
    blacklisted_pairs = set()
    for record in sql_search:
        blacklisted_pairs.add((record.md5, record.text))
    # Filter itself
    result = []
    for document in paragraphs:
        pair = (document.metadata[TEXT_HASH_COLUMN], document.page_content)
        if pair not in blacklisted_pairs:
            result.append(document)
            # Add to blacklist in case of duplicated paragraphs within same insert query
            blacklisted_pairs.add(pair)
    return result


# %% ../nbs/04_retriever.ipynb 12
async def _store_paragraphs(documents_paragraphs: List[Document],
                            sentence_splitter: SentenceSplitter,
                            engine: AsyncEngine,
                            vectorstore: VectorStore):
    """
    Store given paragraphs
    """
    def _prepare_sentence_documents(text: str, metadata: dict) -> List[Document]:
        """
        Split paragraph to a list of Documents representing individual sentences
        """
        result = []
        for item in sentence_splitter.split_text(document.page_content):
            item_metadata = dict(**metadata)
            item_text_full = ""
            # Join metadata to the sentence
            for key in metadata:
                if key == TEXT_HASH_COLUMN:
                    continue
                item_text_full = f"{item_text_full} : {metadata[key]}"
            # Join main text
            item_text_full = f"{item_text_full} : {item.page_content}"
            item_text_full = item_text_full.strip(" :")
            # Store original text in the metadata
            item_metadata["_text"] = text
            # Create document
            result.append(Document(
                page_content=item_text_full,
                metadata=item_metadata,
            ))
        return result

    sentences_to_add = []
    assert isinstance(engine, AsyncEngine)
    async with AsyncSession(engine) as session:
        async with session.begin():
            # Remove known paragraphs
            documents_paragraphs = await _remove_known_paragraphs(session,
                                                                  documents_paragraphs)
            # Prepare paragraphs to store in the ORM and sentences to store in the vector DB
            records = []
            for document in documents_paragraphs:
                assert TEXT_HASH_COLUMN in document.metadata
                hash = document.metadata[TEXT_HASH_COLUMN]
                records.append(
                    ParagraphMemoryRecord(
                        text=document.page_content,
                        meta=document.metadata,
                        md5=hash,
                        created_at=datetime.now()
                    )
                )
                sentences_to_add += _prepare_sentence_documents(
                    document.page_content,
                    metadata=document.metadata,
                )
            # Add paragraphs to the DB
            session.add_all(records)
        # Add sentences to the vector DB
        if sentences_to_add:
            vectorstore.add_documents(sentences_to_add)

# %% ../nbs/04_retriever.ipynb 13
async def _get_paragraphs(
    sentence_vector_search_document_scores: List[Tuple[Document, float]],
    engine: AsyncEngine
) -> List[Tuple[ParagraphMemoryRecord, float]]:
    """
    Extract paragraphs from the database using sentences extracted by vector DB
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        def _get_hashes_to_search(sentence_vector_search: List[Document]) -> Set[str]:
            """
            Get paragraph hashes to use in `md5 IN ...` condition
            """
            parapraph_hashes = set()
            for item in sentence_vector_search:
                parapraph_hashes.add(item.metadata[TEXT_HASH_COLUMN])
            return parapraph_hashes
        
        async def _extract_paragraphs_by_hashes(hashes: Set[str]) -> Dict[str, List[ParagraphMemoryRecord]]:
            """
            Extract `ParagraphMemoryRecord` using given hashes
            """
            hash_to_paragraphs = {}
            async with session.begin():
                sql_query = select(ParagraphMemoryRecord).filter(
                    ParagraphMemoryRecord.md5.in_(hashes)
                )
                sql_search = await session.scalars(sql_query)
                for record in sql_search:
                    if record.md5 not in hash_to_paragraphs:
                        hash_to_paragraphs[record.md5] = []
                    hash_to_paragraphs[record.md5].append(record)
            return hash_to_paragraphs
        
        def _filter_paragraphs_by_metadata(sentence_vector_search: List[Document],
                                           hash2paragraph: Dict[str, List[ParagraphMemoryRecord]]) \
                                           -> List[List[ParagraphMemoryRecord]]:
            """
            In case of md5 collision to additional filtering by common keys metadata's values being the same
            """
            records_meta_found = []
            for item in sentence_vector_search:
                item_meta = item.metadata
                item_meta_keys = set(item_meta)
                potential_findings = hash2paragraph[item.metadata[TEXT_HASH_COLUMN]]
                found = []
                for record in potential_findings:
                    record_meta = record.meta
                    common_meta_keys = item_meta_keys & set(record_meta)
                    item_common_meta = {key: item_meta[key] for key in common_meta_keys}
                    record_common_meta = {key: record_meta[key] for key in common_meta_keys}
                    if item_common_meta == record_common_meta:
                        found.append(record)
                records_meta_found.append(found)
            return records_meta_found
        
        def _filter_paragraphs_by_text(sentence_vector_search: List[Document],
                                    paragraphs: List[List[ParagraphMemoryRecord]]) \
            -> List[ParagraphMemoryRecord]:
            """
            Finally filter paragraphs be checking if sentence text is within them
            """
            result = []
            for item, item_records_meta_found in zip(sentence_vector_search, paragraphs):
                found = None
                for record in item_records_meta_found:
                    if item.metadata["_text"] in record.text:
                        found = record
                        break
                assert found is not None
                result.append(found)
            return result
        
        sentence_vector_search = [
            document
            for document, _ in sentence_vector_search_document_scores
        ]
        sentence_vector_scores = [
            score
            for _, score in sentence_vector_search_document_scores
        ]
        hashes = _get_hashes_to_search(sentence_vector_search)
        hash2paragraph = await _extract_paragraphs_by_hashes(hashes)
        paragraphs_meta_cleaned = _filter_paragraphs_by_metadata(sentence_vector_search, hash2paragraph)
        paragraphs_text_cleaned = _filter_paragraphs_by_text(sentence_vector_search, paragraphs_meta_cleaned)
        return [
            (item, score)
            for item, score in zip(paragraphs_text_cleaned, sentence_vector_scores)
        ]

# %% ../nbs/04_retriever.ipynb 14
def _unique_documents(documents: List[Tuple[ParagraphMemoryRecord, float]],
                      score_processor: Callable[[ParagraphMemoryRecord, float], float]) -> \
    List[Tuple[ParagraphMemoryRecord, float]]:
    """
    Given top_sentences_k pairs (paragraph - sentence score) return pairs (unique paragraph - best sentence score)
    """
    documents_by_id = {
        document.id: document
        for document, _ in documents
    }
    records = []
    for document, score in documents:
        records.append({"id": document.id, "score": score, "created_at": document.created_at})
    df = pd.DataFrame.from_records(records)
    df["score_processed"] = [
        score_processor(documents_by_id[row["id"]], row["score"])
        for _, row in df.iterrows()
    ]
    if len(df) == 0:
        return []
    id2max_score = df.groupby("id")["score_processed"].max()
    id2max_score = id2max_score.sort_values(ascending=False)
    return [
        (documents_by_id[doc_id], id2max_score[doc_id])
        for doc_id in id2max_score.index
    ]

# %% ../nbs/04_retriever.ipynb 16
INPUT_RETRIEVER_QUERY = "query"
INTERMEDIATE_RETRIEVER_DOCUMENTS = "documents"
OUTPUT_RETRIEVER_DOCUMENTS = "documents_text"

BLACKLISTED_META_PROPERTIES = {TEXT_HASH_COLUMN}

# %% ../nbs/04_retriever.ipynb 17
def _no_score_processing(document: ParagraphMemoryRecord, score: float) -> float:
    return score


ScoreProcessing = Union[None, Callable[[ParagraphMemoryRecord, float], float]]


class Memory:
    def __init__(self, engine: AsyncEngine, vector_db: VectorStore, \
                 lower_score_is_better: bool,
                 score_processing: ScoreProcessing = None,
                 top_k_sentences: int = 50,
                 top_k_paragraphs: int = 5) -> None:
        """
        Memory wrapper
        :param engine: SQLAlchemy engine for SQL part of database
        :param vector_db: Vector storage for sentences
        :param lower_score_is_bettter: Different embedder & stores operates different metrics. Like cosine distance - or similarity?
        :param top_k_sentences: How many sentences retrieved from the DB
        :param top_k_paragraphs: How many paragraphs retrieved from the DB by found top_k_sentences sentences.
        """
        self.engine = engine
        self.vector_db = vector_db
        self.lower_score_is_better = lower_score_is_better
        self.sentence_splitter = SentenceSplitter()
        self.score_processing = score_processing
        self.top_k_sentences = top_k_sentences
        self.top_k_paragraphs = top_k_paragraphs

    def store(self, paragraphs: List[Document]) -> None:
        """
        Store given paragraphs in the satabase
        """
        asyncio.get_event_loop().run_until_complete(
            self.astore(paragraphs)
        )

    async def astore(self, paragraphs: List[Document]) -> None:
        """
        Store given paragraphs in the satabase. Async version
        """
        await _store_paragraphs(
            documents_paragraphs=paragraphs,
            sentence_splitter=self.sentence_splitter,
            engine=self.engine,
            vectorstore=self.vector_db
        )

    def _process_scores(self, documents: List[Tuple[Document, float]]) -> List[Tuple[Document, float]]:
        k = 1
        if self.lower_score_is_better:
            k = -1
        return [
            (doc, score * k)
            for doc, score in documents
        ]
    
    def _get_score_processing(self):
        if self.score_processing:
            score_processing = self.score_processing
        else:
            score_processing = _no_score_processing
        return score_processing
    
    def retrieve(self, query: str) -> List[Tuple[ParagraphMemoryRecord, float]]:
        """
        Retrive query-relevant paragraphs from the database
        :param query: Search query
        :returns: Search result
        """
        return asyncio.get_event_loop().run_until_complete(
            self.aretrieve(query)
        )
    
    async def aretrieve(self, query: str) -> List[Tuple[ParagraphMemoryRecord, float]]:
        """
        Retrive query-relevant paragraphs from the database. Async version.
        :param query: Search query
        :returns: Search result
        """
        score_processing = self._get_score_processing()
        # TODO: Add proper async calls to Milvus
        sentence_similarity_search = await asyncio.to_thread(
            self.vector_db.similarity_search_with_score,
            query,
            k=self.top_k_sentences
        )
        sentence_similarity_search = self._process_scores(sentence_similarity_search)
        
        document_extraction = await _get_paragraphs(
            sentence_similarity_search,
            self.engine
        )
        documents = _unique_documents(document_extraction, score_processing)
        documents = documents[:self.top_k_paragraphs]
        return documents
    
    def build_retriever_chain(self) -> RunnableSequence:
        """
        Build langchain chain from retrieving
        :returns: LangChain chain consuming `{INPUT_RETRIEVER_QUERY: string_query}` 
            and returning `{OUTPUT_RETRIEVER_DOCUMENTS: found_paragraphs_text}`
        """
        def _retrieve_documents(row):
            return {
                INTERMEDIATE_RETRIEVER_DOCUMENTS: self.retrieve(row[INPUT_RETRIEVER_QUERY])
            }
        
        async def _aretrieve_documents(row):
            return {
                INTERMEDIATE_RETRIEVER_DOCUMENTS: await self.aretrieve(row[INPUT_RETRIEVER_QUERY])
            }
        
        def _stringify_documents(row):
            documents: List[Tuple[ParagraphMemoryRecord, float]] = row[INTERMEDIATE_RETRIEVER_DOCUMENTS]
            records = []
            for doc, _ in documents:
                record = {}
                record["text"] = doc.text
                record["meta"] = "\n\n".join([
                    f"# {property_name} : {value}"
                    for property_name, value in doc.meta.items()
                    if property_name not in BLACKLISTED_META_PROPERTIES
                ])
                records.append(record)
            df = pd.DataFrame.from_records(records)
            joined_paragraphs = []
            if len(df) > 0:
                for meta_text, sub_df in df.groupby("meta"):
                    paragraphs_joined_text = "\n\n".join(sub_df["text"])
                    meta_joined_text = f"{meta_text}\n\n{paragraphs_joined_text}"
                    joined_paragraphs.append(meta_joined_text)
            joined_text = "\n\n".join(joined_paragraphs)
            return {
                OUTPUT_RETRIEVER_DOCUMENTS: joined_text,
            }
        
        async def _astringify_documents(row):
            return _stringify_documents(row)
        
        retriever = TransformChain(
            transform=_retrieve_documents,
            atransform=_aretrieve_documents,
            input_variables=[INPUT_RETRIEVER_QUERY],
            output_variables=[INTERMEDIATE_RETRIEVER_DOCUMENTS],
        )
        stringifier = TransformChain(
            transform=_stringify_documents,
            atransform=_astringify_documents,
            input_variables=[INTERMEDIATE_RETRIEVER_DOCUMENTS],
            output_variables=[OUTPUT_RETRIEVER_DOCUMENTS]
        )

        return retriever | stringifier
