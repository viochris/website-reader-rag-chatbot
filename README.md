# 🌐 Website Reader RAG Chatbot

An end-to-end, CLI-based RAG chatbot that lets you chat with the content of any web page. It scrapes and indexes the page once, retrieves and reranks the most relevant passages for every question, and answers strictly from what the page actually says, while remembering the conversation across runs.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat&logo=python&logoColor=white)
![LlamaIndex](https://img.shields.io/badge/Framework-LlamaIndex-6E56CF?style=flat)
![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB%20Cloud-FF6F00?style=flat)
![Trafilatura](https://img.shields.io/badge/Ingestion-Trafilatura-critical?style=flat)
![Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?style=flat&logo=googlegemini&logoColor=white)
![Reranker](https://img.shields.io/badge/Reranker-Cross--Encoder-yellowgreen?style=flat)
![PostgreSQL](https://img.shields.io/badge/Memory-PostgreSQL%20(AsyncPG)-336791?style=flat&logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)

## 📌 Overview

This repository contains a CLI-based Retrieval-Augmented Generation (RAG) assistant that lets you have a conversation with the content of one or more web pages. It's built as a single, end-to-end script (`website-reader-cmd.py`). Point it at a list of URLs and it scrapes and cleans the page text, chunks and embeds it, stores the vectors in ChromaDB Cloud, and then opens an interactive chat loop where every answer is grounded in the retrieved page content.

The application configures LlamaIndex's global `Settings` for the LLM, the embedding model, and the node parser. It scrapes and indexes data only when the target ChromaDB collection is empty, rebuilds the index straight from the vector store on every later run, and wires that index into a context-mode chat engine with cross-encoder reranking and persistent PostgreSQL-backed memory.

Every answer is retrieved, not memorized. The system prompt instructs the model to answer strictly from the retrieved web page context, and to state explicitly that it doesn't know when the answer isn't there.

### ✨ Key Features
* 🕸️ **Automated web ingestion.** Scrapes and cleans the target pages with `TrafilaturaWebReader`, keeping tables and formatting, dropping comments, and attaching page metadata to every document.
* 🧠 **Semantic retrieval over page content.** Pages are split into overlapping chunks and embedded with Google's Gemini embedding model, then stored in a ChromaDB Cloud collection and searched by meaning rather than by exact keyword.
* ♻️ **Idempotent by design.** On startup the app checks whether the ChromaDB collection already contains data. If it does, it skips scraping and embedding entirely and just loads the existing index.
* 🎯 **Retrieve-then-rerank retrieval.** Pulls the top 5 chunks per query, then narrows them down to the top 3 with a `cross-encoder/ms-marco-MiniLM-L-2-v2` reranker before they ever reach the LLM.
* 💬 **Persistent conversational memory.** Chat history is stored via `Memory` backed by AsyncPG and PostgreSQL, so context isn't lost between runs.
* 🧱 **Grounded by instruction.** A strict system prompt tells the model to answer only from the retrieved context and to admit when the page doesn't contain the answer.
* 🛡️ **Layered, categorized error handling.** Top-level failures are routed into clear, human-readable categories such as API quota, authentication, database, permission, or data errors, with the raw traceback printed first for debugging.

---

## 🎯 Context & Problem Statement

This project exists to solve a concrete, everyday reading problem rather than to show off a tech stack for its own sake, so it's worth spelling out what that problem is and why neither a keyword search nor a general-purpose chatbot already solves it.

### 📖 The Problem

Web pages, whether they're technical documentation, a long encyclopedia article, a blog post, or a product page, are where most written knowledge lives today, and they're also long, dense, and only searchable by exact keyword. Pressing `Ctrl+F` finds strings, not answers. Pasting the page into a general chatbot or just asking it about the topic brings a different set of problems. The gap between how much a page contains and how hard it is to ask it a direct question breaks down into three more specific issues.

1. **Keyword search can't answer questions.** Finding the part of a long page that explains *why* something works, or how two ideas relate, means guessing the right keyword and reading around every match by hand. Page search matches words, not meaning, so a question phrased differently from the page's wording can come back with nothing.
2. **A general-purpose chatbot answers from memory, not from the page.** Asked about a specific page, a plain LLM may rely on stale training data, blend in other sources, or simply guess, and it has no built-in obligation to say "that isn't on this page." There's no way to tell which parts of the answer came from the page you actually care about.
3. **Naive pipelines are wasteful and forgetful.** A basic scrape-embed-ask script re-downloads and re-embeds the same page on every run, which costs time and embedding API calls, and it loses the whole conversation the moment the process exits.

### 💡 The Solution

Rather than bolting a chatbot onto a pasted page and hoping for the best, this project treats a web page as a source of truth that needs to be captured, indexed, and retrieved from on every question. Each of the three problems above maps to one deliberate piece of the pipeline, not a generic feature added for its own sake.
* 🔎 **Problem 1 → chunk, embed, and retrieve semantically.** Page text is split into overlapping chunks and embedded with Gemini, so a question is matched to the passages closest in meaning even when the wording differs. This only works as well as the extracted text allows, and pages that render their content with JavaScript may not be captured at all (see System Limitations).
* 🧱 **Problem 2 → ground every answer in retrieved, reranked context.** Retrieved chunks are rescored by a cross-encoder before they reach the LLM, and a strict system prompt tells the model to answer only from that context and to say it doesn't know otherwise. This is an instruction to the model rather than a hard guarantee, and the current version doesn't print which chunks or URLs backed each answer (see System Limitations).
* ♻️ **Problem 3 → persist both the index and the conversation.** Vectors live in ChromaDB Cloud and the ingestion path is skipped when the collection already has data, while chat history lives in PostgreSQL, so repeated use stays cheap and context survives restarts. The ingestion gate only checks whether the collection is empty, which brings its own trade-offs (see System Limitations).

Taken together, these three pieces close the core gap this project set out to solve, but they don't make the pipeline finished. The sections below spell out exactly where the current version still falls short and what's planned to address it.

---

## 🧩 Tech Stack Highlights

| Layer | Tool | Role |
| :--- | :--- | :--- |
| **Web ingestion** | `TrafilaturaWebReader` (`llama-index-readers-web`) | Scrapes the target URLs and extracts clean page text with metadata |
| **Orchestration** | LlamaIndex core (`Settings`, `StorageContext`, `VectorStoreIndex`, `SentenceSplitter`) | Global LLM/embedding config, chunking, and index construction |
| **Text embeddings** | `GoogleGenAIEmbedding` (`models/gemini-embedding-2`) | Embeds page chunks |
| **Vector storage** | ChromaDB Cloud (`chromadb.CloudClient`, `ChromaVectorStore`) | Stores page chunk vectors in the `website_docs` collection |
| **Retrieval** | `VectorStoreIndex` chat engine (`similarity_top_k=5`) | Pulls the top 5 most similar chunks per query |
| **Reranking** | `SentenceTransformerRerank` (`cross-encoder/ms-marco-MiniLM-L-2-v2`) | Rescores retrieved chunks and keeps the top 3 |
| **LLM** | `GoogleGenAI` (`models/gemini-3.6-flash`, temperature 0.3) | Answer generation |
| **Chat engine** | LlamaIndex `context` chat mode | Retrieves context on every turn and injects it into the prompt |
| **Conversation memory** | `Memory` + AsyncPG (PostgreSQL) | Persistent chat history across runs |
| **Config & runtime** | `python-dotenv`, `nest-asyncio` | Loads secrets from `.env` and allows nested event loops |

---

## ⚙️ Configuration Reference

Every tunable value currently lives directly in `website-reader-cmd.py`.

| Setting | Value | Effect |
| :--- | :--- | :--- |
| **Target pages** | `urls = [...]` (default: the Wikipedia article on Retrieval-augmented generation) | The pages scraped and indexed on a fresh run |
| **Chunking** | `chunk_size=512`, `chunk_overlap=50` | How page text is split before embedding |
| **Retrieval depth** | `similarity_top_k=5` | Number of chunks fetched per query |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-2-v2`, `top_n=3` | Chunks that actually reach the LLM |
| **LLM** | `models/gemini-3.6-flash`, `temperature=0.3` | Answer model and its randomness |
| **Chroma collection** | `website_docs` | Where page vectors are stored |
| **Memory** | `session_id="website_session"`, `token_limit=40000`, `table_name="website_reader_memory"` | How chat history is stored and trimmed |
| **Scraper options** | `include_comments=False`, `include_tables=True`, `include_formatting=True`, `with_metadata=True` | What Trafilatura keeps from each page |
| **Exit commands** | `exit`, `close`, `out`, `break`, `keluar`, `x` | Ends the chat session |

---

## 🖥️ Example Console Output

An illustrative first-run session, based on the messages the script prints:

```text
⚙️ [SYSTEM] Configuring LlamaIndex Settings (LLM & Embeddings)...
⚙️ [SYSTEM] Initializing Cross-Encoder Reranker...
⏳ [SYSTEM] Initializing ChromaDB Cloud Client...
🔌 [SYSTEM] Attaching ChromaVectorStore adapter...
⏳ [SYSTEM] ChromaDB is empty. Scraping and loading data from specified URLs...
✅ [SYSTEM] Successfully loaded data from 1 URL(s).
⚙️ [SYSTEM] Creating Vector Store Index and embedding documents to ChromaDB Cloud...
✅ [SYSTEM] Index successfully generated and stored in ChromaDB Cloud.
🧠 [SYSTEM] Initializing Chat Engine and persistent PostgreSQL memory...
✅ [SYSTEM] Chat Engine successfully integrated and ready for interaction.

======================================================================
💬 [SYSTEM] Interactive Web Reader Session Started. Type 'exit' to stop.
======================================================================

🗣️ [USER] You: <your question about the page>
🧠 [AI] Processing your query against the website context...
----------------------------------------------------------------------
🤖 [AI RESPONSE]:
<an answer grounded in the retrieved page context>
----------------------------------------------------------------------
```

On later runs, the ingestion lines are replaced by `📂 [SYSTEM] Existing data found in ChromaDB. Bypassing web scraping phase...`.

---

## 📁 Repository Structure

| Path | Description |
| :--- | :--- |
| `website-reader-cmd.py` | The full pipeline. Scraping, indexing, retrieval, chat engine, and CLI loop, all in one script |
| `requirements.txt` | All Python dependencies, with install notes inside the file |
| `LICENSE` | MIT License |
| `README.md` | You're reading it |

---

## 🏗️ Architecture & Data Flow

### 🔄 End-to-End System Flowchart

```mermaid
flowchart TD
    A["Target URL(s) from the urls list"] --> B{"Is the ChromaDB collection website_docs empty?"}

    B -- "Yes" --> C
    B -- "No" --> H["VectorStoreIndex.from_vector_store loads existing data"]

    subgraph Ingestion ["Runs only if the collection is empty"]
        C["TrafilaturaWebReader scrapes and cleans page text"] --> D["SentenceSplitter chunks text, 512 size and 50 overlap"]
        D --> E["GoogleGenAIEmbedding produces text vectors"]
        E --> F["ChromaDB Cloud collection website_docs"]
    end

    F --> G["VectorStoreIndex"]
    H --> G

    G --> I["Retriever, top 5 chunks"]
    I --> J["SentenceTransformerRerank narrows to top 3"]
    J --> K["Context Chat Engine"]
    L["AsyncPG / PostgreSQL Persistent Memory"] --> K
    M["Gemini LLM via Google GenAI"] --> K
    K --> N["Interactive CLI Chat Loop"]
    N --> O["Answer grounded in page context"]
```

> **Note.** On every run, the app first checks whether the ChromaDB collection is already populated. If it is, it skips scraping and embedding entirely and loads the existing index directly. The full ingestion path above only runs once per fresh collection.

---

## 💻 Installation & Reproduction Steps

### 📋 Prerequisites
* **Python 3.10 or newer** is required.
* **Accounts and keys** you'll need include a Google AI Studio API key for Gemini, a [Chroma Cloud](https://www.trychroma.com/) API key, and a reachable PostgreSQL database for conversation memory.
* **Internet access** on the first run, both to scrape the target pages and to download the cross-encoder reranker weights from Hugging Face.

### 🛠️ CLI Installation & Execution

#### 1. Clone the Repository
```bash
git clone https://github.com/viochris/website-reader-rag-chatbot.git
cd website-reader-rag-chatbot
```

#### 2. Create and Activate a Virtual Environment
```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
> The LlamaIndex ecosystem ships as many small, fast-moving sub-packages. If you hit a resolver conflict, try installing into a clean virtual environment and letting `pip` resolve every package from `requirements.txt` in a single command rather than one at a time, since that gives it the full picture needed to pick mutually compatible versions.

#### 4. Configure Environment Variables
Create a `.env` file in the project root.
```env
GOOGLE_API_KEY=your_google_ai_studio_key
CHROMA_API_KEY=your_chroma_cloud_key
ASYNCPG_DATABASE_URL=postgresql://user:password@host:port/dbname
```
> Only `GOOGLE_API_KEY` is explicitly validated at startup. The other two variables are passed straight to their clients. Keep `.env` out of version control.

#### 5. Set the Target Pages
Currently the target URL(s) are set directly in the script.
```python
urls = ["https://en.wikipedia.org/wiki/Retrieval-augmented_generation"]
```
Edit this list before the first run to point the pipeline at different pages (see System Limitations below).

#### 6. Run the Application
```bash
python website-reader-cmd.py
```
Type your questions at the `🗣️ [USER] You:` prompt. Type `exit`, `close`, `out`, `break`, `keluar`, or `x` to end the session.

---

## 📝 Conclusion

Putting the whole pipeline together, this project set out to solve three concrete problems: keyword search that can't answer questions about a long page, a general-purpose chatbot that answers from memory instead of from the page, and naive pipelines that re-scrape, re-embed, and forget everything between runs. The pipeline built here addresses all three directly. It chunks and embeds page content so questions are matched by meaning, it reranks what it retrieves and instructs the model to answer only from that context, and it persists both the vectors and the conversation so repeated use stays cheap and continuous.

The design choices behind this also hold up reasonably well on their own terms. Treating ingestion as idempotent, so re-running the app skips straight to loading the existing index, avoids paying for the same scrape and embeddings twice. Reranking with a small cross-encoder before the LLM is a deliberate quality step rather than a shortcut, and keeping the whole flow in one readable script with categorized error handling makes it easy to follow, run, and modify.

That said, this is a solution to the three problems above specifically, not a finished product. It still has real, honest gaps. The target URLs are hardcoded in the script, ingestion only re-runs when the collection is completely empty so swapping pages requires manual cleanup, answers don't show which chunks or URLs they came from, and the whole system depends on external services being reachable with no offline fallback. The sections immediately below go through each of these gaps in detail and lay out concrete next steps for closing them.

---

## ⚠️ System Limitations

### 🏗️ Architectural Limitations
* **Hardcoded target pages.** The URL(s) to ingest are set by editing the `urls` list directly in the script, not passed in as an argument. Switching to a different page means opening the code, not just running a command. This is addressed by the "CLI arguments for URL input" item under Future Work.
* **One-time ingestion gate.** Scraping and indexing only run when the `website_docs` collection is empty, as a way to avoid re-processing the same pages on every run. The downside is that changing the `urls` list without first manually clearing the collection doesn't trigger re-ingestion at all, so the app will silently keep answering from the old pages. This is what the "collection versioning" item under Future Work is meant to fix.
* **Single shared collection and session.** All pages go into one collection, and the memory uses a fixed `session_id`, so every run shares the same chat history. Switching to a different page means the old conversation still sits in memory, which can blend unrelated topics into new answers.
* **Any error ends the session.** The whole pipeline, including the chat loop, sits inside one top-level `try` block. A transient failure on a single turn, such as an API rate limit, is reported clearly but still terminates the program instead of letting the user retry.
* **No source display.** The current version prints only the final answer. A user can't see which chunks or URLs a response was grounded in, which makes it harder to verify an answer against the original page.
* **CLI-only interface.** All interaction happens through a terminal input loop with plain-text prompts and responses. There's no web page and no visual chat history. See the "lightweight web UI" item under Future Work.
* **Minimal startup validation.** Only `GOOGLE_API_KEY` is checked before the pipeline starts. A missing or malformed Chroma key or database URL isn't caught up front and only surfaces later, when the corresponding client is first used.

### 🔬 Model & Domain Limitations
* **Dependence on external, metered services.** The pipeline needs a live connection to the Gemini API (for both the LLM and the embeddings), ChromaDB Cloud, and a PostgreSQL database. There's currently no offline or local-only mode, so the app won't run if any one of those services is unreachable or its credentials are invalid.
* **Static HTML extraction only.** Trafilatura works on the HTML a page serves. Pages that build their content with JavaScript, sit behind a login, or block automated requests may come back empty or only partially extracted, and the model can only answer from what was captured.
* **Grounding relies on the prompt.** Staying within the page context is enforced by the system prompt and the retrieval setup, not by a hard check on the output. The model could still go beyond the retrieved chunks, and the current version has no automated way to detect that.
* **Fixed retrieval settings.** Chunk size, overlap, `top_k`, and the reranker's `top_n` are fixed values chosen up front. A very broad question that needs information from many parts of a long page can be limited by only three chunks reaching the LLM.
* **Local reranking and first-run download.** The cross-encoder runs locally rather than through a hosted API. The chosen model is small, but it still needs PyTorch, a one-time weight download from Hugging Face, and a bit of local compute on every chat turn.
* **No quantitative evaluation yet.** Retrieval and answer quality have not been measured against a labeled question set, so there is currently no number for how often the pipeline retrieves the right chunk or answers correctly.
* **Dormant import.** `SimpleDirectoryReader` is imported at the top of the script but never used in the current pipeline, so it can be removed or put to use in a future local-file ingestion path.

---

## 🚀 Future Work
* **CLI arguments for URL input.** Right now the target pages are a hardcoded list inside the script. Accepting one or more URLs as a command-line argument or a config value would let anyone point the pipeline at new pages without touching the code at all.
* **Collection versioning.** Because ingestion only runs when the collection is empty, switching pages today means manually deleting the old collection first. Namespacing collections (and memory sessions) per URL, or auto-detecting and clearing stale data, would make swapping pages a one-command operation.
* **Show sources with every answer.** Print the retrieved chunks, their similarity or rerank scores, and the originating URL after each response, so a user can verify what an answer was grounded in and jump straight back to the source page.
* **Resilient chat loop.** Move error handling inside the loop so a single failed turn, like a rate limit, prints the categorized error and lets the user try again instead of ending the session.
* **JavaScript-rendered page support.** Add a headless-browser fallback for pages whose content isn't present in the raw HTML, so single-page apps and dynamically loaded documentation can be ingested too.
* **Retrieval and answer evaluation.** Build a small labeled question set for a few pages and measure retrieval hit rate and answer faithfulness (for example with a RAG evaluation framework), then use the results to tune chunk size, `top_k`, and `top_n` rather than relying on fixed defaults.
* **Lightweight web UI.** A simple Streamlit or Gradio front end would make chat history and source citations easier to read at a glance than scrolling terminal output.

---

## 📄 License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---
**Author:** [Silvio Christian, Joe](https://github.com/viochris)

*"Answering from what a page actually says, not from what a model remembers."*
