"""
This is an updated version of the Chroma Client class, which is responsible for interacting with the Chroma database.

When we have the request in a "RetrievalAugmentedResponse" Object we create new collections of embedded chunked messages search
the fittest data from query and then pass it to Model to generate answer.
"""
import asyncio
import time


import sentence_transformers
import chromadb
from typing import Dict

from source.ChromaАndRAG.llmGateway import LLMGateway
from source.MiddleWareResponseModels import RetrievalAugmentedResponse
from source.Logging import get_logger

class ChromaDBHelper:
    """
    This class is responsible for interacting with the Chroma database.
    It handles the creation of collections, adding and deleting channels, and querying the database.
    """
    def __init__(
            self,
            model: str,
            host: str,
            port: int,
            n_result: int,
            max_chunk_size_in_sentences: int,
            max_cache: int,
            time_to_live: int,
            llm_gateway: LLMGateway,
    ):
        self.client = chromadb.HttpClient(
            port=port,
            host=host,
            ssl=False,
            headers=None
        )
        self.n_result = n_result
        self.max_chunk_size_in_sentences = max_chunk_size_in_sentences
        self.pending_collections: Dict[str, (chromadb.Collection, int)] = {} # We will implement TTL cache right in the class.
        self.max_cache = max_cache
        self.time_to_live = time_to_live
        self.SentenceTransformer = sentence_transformers.SentenceTransformer(model)
        self.running = True
        self.llm_gateway = llm_gateway
        self.chroma_logger = get_logger("ChromaDBHelper", "network")


    def acknowledge(self, channel_name: str):
        """
        It acknowledges that such channel collection is present in database.
        """
        self.chroma_logger.info(f"Crawler asked for acknowledge for {channel_name}")
        if not self.running:
            return False
        if channel_name in self.pending_collections:
            if time.time() - self.pending_collections[channel_name][1] >= self.time_to_live:
                # If the collection is older than the time to live, we remove it.
                self.client.delete_collection(channel_name)
                del self.pending_collections[channel_name]
                return False
            return True
        else:
            return False

    def chunk_and_encode(self, text: str):
        """
        Splits the text into chunks of a specified size and encodes them using a SentenceTransformer model.
        """
        sentences = text.split(". ")
        chunks = []
        current_chunk = []

        for sentence in sentences:
            if len(current_chunk) < self.max_chunk_size_in_sentences:
                current_chunk.append(sentence)
            else:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]

        if current_chunk:
            chunks.append(" ".join(current_chunk))
        embedded_chunks = self.SentenceTransformer.encode(chunks)
        return chunks, embedded_chunks

    async def process_response(self, response: RetrievalAugmentedResponse):
        """
        This method will process the response and add the messages to the response object.
        """
        channels_and_messages = response.channels_and_messages
        results_dict = {}
        start_time = time.time()
        self.chroma_logger.info(f"Caught response from {response.user_name} with query: {response.query}")

        # First off create new collections
        for channel_name, messages in channels_and_messages.items():
            if channel_name in self.pending_collections:
                # If the collection is already present, we just need to add the messages to it.
                collection = self.pending_collections[channel_name][0]
            else:
                # Create a new collection
                collection = self.client.create_collection(
                    name=channel_name,
                )
                self.pending_collections[channel_name] = (collection, time.time())
                # Now we need to chunk and encode the messages
                for message in messages:
                    chunks, embedded_chunks = self.chunk_and_encode(message)
                    collection.add(
                        documents=chunks,
                        embeddings=embedded_chunks,
                        metadatas=[{"channel_name": channel_name}] * len(chunks),
                        ids=[str(i) for i in range(len(chunks))],
                    )
            # Now we query the collection
            results = collection.query(
                query_embeddings=self.SentenceTransformer.encode(response.query),
                n_results=self.n_result,
            )
            results_dict[channel_name] = results.get("documents", [])

        self.chroma_logger.info(f"Processed chroma query in {time.time() - start_time} seconds")
        # Now we add everything to response.
        response.chroma_response = results_dict
        response.set_next(self.llm_gateway.generate_response)







