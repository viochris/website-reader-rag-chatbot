# Standard library imports
import os
import sys
import logging
import traceback

# Third-party library imports
import chromadb
import nest_asyncio
from dotenv import load_dotenv

# LlamaIndex core components and modules
from llama_index.core import (
    Settings,
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.memory import Memory

# LlamaIndex integrations (Readers, Vector Stores, LLMs, Embeddings)
from llama_index.readers.web import TrafilaturaWebReader
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

# Patch asyncio to allow nested event loops if running in specific environments
nest_asyncio.apply()

# Suppress verbose debug/info logs from underlying HTTP and API clients
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)

# ==============================================================================
# 1. ENVIRONMENT CONFIGURATION
# ==============================================================================
# Load environment variables from the .env file
load_dotenv()

# Verify the presence of the Google API Key before proceeding
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("🚨 [SYSTEM ERROR] GOOGLE_API_KEY is missing. Please check your .env file.")

# Define the target URLs for web scraping and ingestion
urls = ["https://en.wikipedia.org/wiki/Retrieval-augmented_generation"]

try:
    # ==============================================================================
    # 2. SYSTEM SETTINGS & LLM CONFIGURATION
    # ==============================================================================
    print("⚙️ [SYSTEM] Configuring LlamaIndex Settings (LLM & Embeddings)...")
    
    # Configure global LLM and Embedding models using Google Gemini
    Settings.llm = GoogleGenAI(model="models/gemini-3.6-flash", api_key=GOOGLE_API_KEY, temperature=0.3)
    Settings.embed_model = GoogleGenAIEmbedding(model_name="models/gemini-embedding-2", api_key=GOOGLE_API_KEY)
    
    # Configure node parser for chunking documents
    Settings.node_parser = SentenceSplitter(
        chunk_size=512, 
        chunk_overlap=50
    )

    # Initialize the Reranker to improve search accuracy by rescoring the top-k retrieved nodes
    print("⚙️ [SYSTEM] Initializing Cross-Encoder Reranker...")
    reranker = SentenceTransformerRerank(
        model="cross-encoder/ms-marco-MiniLM-L-2-v2",
        top_n=3
    )

    # ==============================================================================
    # 3. CHROMA DB SETUP (CLOUD CLIENT)
    # ==============================================================================
    print("⏳ [SYSTEM] Initializing ChromaDB Cloud Client...")
    chroma_client = chromadb.CloudClient(api_key=os.getenv("CHROMA_API_KEY"))
    
    # Create or retrieve the specific collection for website data
    chroma_collection = chroma_client.get_or_create_collection("website_docs")

    # Wrap the collection into a VectorStore and attach it to the StorageContext
    print("🔌 [SYSTEM] Attaching ChromaVectorStore adapter...")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # ==============================================================================
    # 4. DATA INGESTION & INDEXING (WEB SCRAPING)
    # ==============================================================================
    # Verify if the database already contains data to prevent redundant API calls and scraping
    if chroma_collection.count() == 0:
        print("⏳ [SYSTEM] ChromaDB is empty. Scraping and loading data from specified URLs...")
        
        # Instantiate the web reader and load data from the provided URLs
        reader = TrafilaturaWebReader()
        documents = reader.load_data(
            urls=urls,
            include_comments=False, 
            include_tables=True,
            include_formatting=True,
            with_metadata=True,
            show_progress=True
        )
        print(f"✅ [SYSTEM] Successfully loaded data from {len(urls)} URL(s).")
        
        print("⚙️ [SYSTEM] Creating Vector Store Index and embedding documents to ChromaDB Cloud...")
        index = VectorStoreIndex.from_documents(documents=documents, storage_context=storage_context)
        print("✅ [SYSTEM] Index successfully generated and stored in ChromaDB Cloud.")
    else:
        print("📂 [SYSTEM] Existing data found in ChromaDB. Bypassing web scraping phase...")
        
        # Reconstruct the index directly from the persisted vector store
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
        print("✅ [SYSTEM] Index successfully loaded from cloud storage.")

    # ==============================================================================
    # 5. CHAT ENGINE & MEMORY INITIALIZATION
    # ==============================================================================
    print("🧠 [SYSTEM] Initializing Chat Engine and persistent PostgreSQL memory...")
    
    # Initialize conversational memory to maintain context across sessions using the AsyncPG backend
    memory = Memory.from_defaults(
        session_id="website_session",
        token_limit=40000,
        async_database_uri=os.getenv("ASYNCPG_DATABASE_URL"),
        table_name="website_reader_memory"
    )

    # Define the core instructions and persona for the Chat Engine
    system_prompt = (
        "You are an intelligent and analytical AI assistant. "
        "Your primary objective is to answer user queries strictly based on the provided context extracted from web pages. "
        "If a question requires details from the website context, provide clear and comprehensive explanations. "
        "If the answer cannot be found in the context, explicitly state that you do not know."
    )

    # Instantiate the Chat Engine with context mode, rerankers, and persistent memory integration
    chat_engine = index.as_chat_engine(
        chat_mode="context",
        llm=Settings.llm,
        node_postprocessors=[reranker],
        system_prompt=system_prompt, 
        similarity_top_k=5,
        memory=memory
    )
    print("✅ [SYSTEM] Chat Engine successfully integrated and ready for interaction.")

    # ==============================================================================
    # 6. INTERACTIVE CHAT LOOP
    # ==============================================================================
    print("\n" + "="*70)
    print("💬 [SYSTEM] Interactive Web Reader Session Started. Type 'exit' to stop.")
    print("="*70)

    while True:
        # Capture user input from the CLI
        user_input = input("\n🗣️ [USER] You: ").strip()

        # Guard Clause: Handle termination commands
        if user_input.lower() in ["exit", "close", "out", "break", "keluar", "x"]:
            print("🛑 [SYSTEM] Terminating session. Goodbye!")
            break
            
        # Guard Clause: Handle empty inputs directly
        if not user_input:
            print("⚠️ [SYSTEM] Input cannot be empty. Please ask a question.")
            continue
            
        # Process valid queries through the Chat Engine
        print("🧠 [AI] Processing your query against the website context...")
        ai_response = chat_engine.chat(user_input)

        # Guard Clause: Validate response generation
        if not ai_response:
            print("⚠️ [SYSTEM] AI failed to generate a response or no relevant context found.")
            continue
            
        # Display the final successful result
        print("-" * 70)
        print("🤖 [AI RESPONSE]:")
        print(ai_response)
        print("-" * 70)

# ==============================================================================
# 7. EXCEPTION HANDLING & ERROR ROUTING
# ==============================================================================
except Exception as e:
    error_type = type(e).__name__
    error_msg = str(e).lower()
    error_raw = str(e)

    print("\n" + "="*70)
    print("💥 [CRITICAL FAILURE] LlamaIndex execution aborted!")
    print("="*70)
    
    # Output the raw traceback stack first for deep debugging purposes
    print("🔍 [TRACEBACK LOG]:")
    traceback.print_exc()
    print("-" * 70)

    # Output the human-readable root cause summary at the very bottom for better CLI UX
    print("📌 [ERROR SUMMARY]:")
    
    # Handle API Rate Limits
    if error_type == "ResourceExhausted" or "quota" in error_msg or "429" in error_msg:
        print(f"🚨 [API ERROR] {error_type}: Google API quota exceeded or rate limited. Details: {error_raw}")
        
    # Handle missing or empty data directories/inputs
    elif error_type == "ValueError" and "empty" in error_msg:
        print(f"🚨 [DATA ERROR] {error_type}: A data source is empty or missing valid inputs. Details: {error_raw}")
        
    # Handle Authentication failures
    elif error_type == "InvalidArgument" or "api_key" in error_msg:
        print(f"🚨 [AUTH ERROR] {error_type}: Invalid API Key configuration. Details: {error_raw}")
        
    # Handle Database/ChromaDB initialization errors (Cloud Client)
    elif error_type in ["OperationalError", "DatabaseError", "InvalidCollectionException"] or "chroma" in error_msg:
        print(f"🚨 [DATABASE ERROR] {error_type}: ChromaDB Cloud connection failed. Details: {error_raw}")
        
    # Handle PostgreSQL/AsyncPG connection errors
    elif "asyncpg" in error_msg or "postgres" in error_msg:
        print(f"🚨 [DATABASE ERROR] {error_type}: Failed to connect or write to the PostgreSQL memory database. Details: {error_raw}")
        
    # Handle File System or Network Permission errors
    elif error_type == "PermissionError":
        print(f"🚨 [ACCESS ERROR] {error_type}: System denied access. Details: {error_raw}")
        
    # Generic fallback for unknown exceptions
    else:
        print(f"🚨 [UNKNOWN ERROR] {error_type}: Unexpected failure. Details: {error_raw}")
        
    print("="*70 + "\n")
    
    # Exit the program with a non-zero code to signal execution failure to the OS/Runtime
    sys.exit(1)
    