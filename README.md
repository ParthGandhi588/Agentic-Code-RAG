# Agentic-Code-RAG

> **Next-Generation Autonomous Code Intelligence & Repository Q&A Engine**  
> *Built with FastAPI, LangGraph, Tree-sitter AST, PostgreSQL 17 (pgvector + tsvector), and React.*

---

## 🚀 Key Highlights

* **Agent-as-an-IDE Architecture:** Discards naive chunking in favor of an autonomous LangGraph agent equipped with an IDE toolbelt (`repo_map`, `symbol_definitions`, `call_hierarchy`, `ripgrep`, `read_code_range`).
* **Centrality-Ranked Repo Map:** Computes PageRank over AST symbol definitions and references to provide a compact, token-budgeted architectural map.
* **Deterministic Symbol Graph:** Indexes classes, methods, imports, and call hierarchies via Tree-sitter for 100% precision code navigation.
* **Hybrid Search with RRF:** Merges `pgvector` semantic vectors with PostgreSQL `tsvector` lexical BM25 search via Reciprocal Rank Fusion and local cross-encoder reranking.
* **PostgreSQL 17 Unified Storage:** Vectors, lexical indexes, relational call graphs, and LangGraph thread checkpoints in a single database.
* **Enterprise Lifecycle Standards:** 100% typed configuration with Pydantic v2, Ruff linting/formatting, Mypy strict typing, Pytest test harness, and GitHub Actions CI.

---

## 🛠️ Quick Start

### 1. Prerequisites
* Python 3.12+
* Docker & Docker Compose
* [`uv`](https://docs.astral.sh/uv/) package manager

### 2. Setup Environment
```bash
# Clone or navigate to the repository
cd Agentic-Code-RAG

# Install dependencies with dev tooling
make install

# Start PostgreSQL 17 with pgvector
make docker-up
```

### 3. Run Development Server
```bash
make dev
```
Access the interactive API docs at [http://localhost:8000/docs](http://localhost:8000/docs).

### 4. Run Quality Checks
```bash
# Run tests with coverage
make test

# Run Ruff linter and Mypy type-checker
make lint

# Auto-format codebase
make format
```

---

## 📐 Architecture Roadmap

For the detailed 8-stage architectural specification, see [`docs/roadmap.md`](docs/roadmap.md).
