"""
Demo script for LightRAG with Darshan parsed logs.
This script reads all txt files from /users/Minqiu/parsed-logs-2025-1 and inserts them into LightRAG.
Then provides an interactive query interface for testing.
"""

import os
import asyncio
import logging
import logging.config
from pathlib import Path
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed
from lightrag.utils import logger, set_verbose_debug

# Working directory for LightRAG storage
WORKING_DIR = "./darshan_rag_storage"

# Source directory containing parsed logs
LOGS_DIR = "/users/Minqiu/parsed-logs-2025-1"


def configure_logging():
    """Configure logging for the application"""
    
    # Reset any existing handlers to ensure clean configuration
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "lightrag"]:
        logger_instance = logging.getLogger(logger_name)
        logger_instance.handlers = []
        logger_instance.filters = []

    # Get log directory path from environment variable or use current directory
    log_dir = os.getenv("LOG_DIR", os.getcwd())
    log_file_path = os.path.abspath(os.path.join(log_dir, "darshan_rag_demo.log"))

    print(f"\nLog file: {log_file_path}\n")
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # Get log file max size and backup count from environment variables
    log_max_bytes = int(os.getenv("LOG_MAX_BYTES", 10485760))  # Default 10MB
    log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", 5))  # Default 5 backups

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(levelname)s: %(message)s",
                },
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
                "file": {
                    "formatter": "detailed",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": log_file_path,
                    "maxBytes": log_max_bytes,
                    "backupCount": log_backup_count,
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "lightrag": {
                    "handlers": ["console", "file"],
                    "level": "INFO",
                    "propagate": False,
                },
            },
        }
    )

    # Set the logger level to INFO
    logger.setLevel(logging.INFO)
    # Enable verbose debug if needed
    set_verbose_debug(os.getenv("VERBOSE_DEBUG", "false").lower() == "true")


def collect_txt_files(directory: str) -> list[tuple[str, str]]:
    """
    Recursively collect all txt files from the directory and its subdirectories.
    Returns a list of tuples: (file_path, file_content)
    """
    txt_files = []
    dir_path = Path(directory)
    
    if not dir_path.exists():
        print(f"Error: Directory {directory} does not exist!")
        return txt_files
    
    # Recursively find all .txt files
    for txt_file in dir_path.rglob("*.txt"):
        try:
            with open(txt_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if content.strip():  # Only add non-empty files
                    txt_files.append((str(txt_file), content))
        except Exception as e:
            print(f"Error reading {txt_file}: {e}")
    
    return txt_files


async def initialize_rag():
    """Initialize LightRAG instance"""
    rag = LightRAG(
        working_dir=WORKING_DIR,
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete,
    )

    await rag.initialize_storages()
    return rag


async def insert_logs(rag: LightRAG, logs_dir: str, batch_size: int = 10):
    """
    Insert all txt files from logs directory into LightRAG.
    Uses batch insertion for better performance.
    """
    print(f"\nCollecting txt files from {logs_dir}...")
    txt_files = collect_txt_files(logs_dir)
    
    if not txt_files:
        print("No txt files found!")
        return 0
    
    print(f"Found {len(txt_files)} txt files.")
    
    # Extract contents and file paths
    file_paths = [fp for fp, _ in txt_files]
    contents = [content for _, content in txt_files]
    
    # Insert in batches
    total_inserted = 0
    for i in range(0, len(contents), batch_size):
        batch_contents = contents[i:i + batch_size]
        batch_paths = file_paths[i:i + batch_size]
        
        print(f"Inserting batch {i // batch_size + 1}/{(len(contents) + batch_size - 1) // batch_size} ({len(batch_contents)} files)...")
        
        try:
            # Insert with file paths for citation functionality
            await rag.ainsert(batch_contents, file_paths=batch_paths)
            total_inserted += len(batch_contents)
            print(f"  Successfully inserted {len(batch_contents)} files. Total: {total_inserted}/{len(contents)}")
        except Exception as e:
            print(f"  Error inserting batch: {e}")
    
    return total_inserted


async def interactive_query(rag: LightRAG):
    """Interactive query interface"""
    print("\n" + "=" * 60)
    print("Interactive Query Mode")
    print("=" * 60)
    print("Available query modes: naive, local, global, hybrid, mix")
    print("Commands:")
    print("  - Type your query to search")
    print("  - Type 'mode <mode_name>' to change query mode (e.g., 'mode hybrid')")
    print("  - Type 'quit' or 'exit' to exit")
    print("=" * 60)
    
    current_mode = "hybrid"  # Default mode
    
    while True:
        try:
            user_input = input(f"\n[{current_mode}] Query> ").strip()
            
            if not user_input:
                continue
            
            # Check for exit command
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Exiting...")
                break
            
            # Check for mode change command
            if user_input.lower().startswith("mode "):
                new_mode = user_input[5:].strip().lower()
                if new_mode in ["naive", "local", "global", "hybrid", "mix"]:
                    current_mode = new_mode
                    print(f"Query mode changed to: {current_mode}")
                else:
                    print(f"Invalid mode '{new_mode}'. Available modes: naive, local, global, hybrid, mix")
                continue
            
            # Perform query
            print(f"\nSearching with mode '{current_mode}'...")
            result = await rag.aquery(
                user_input,
                param=QueryParam(mode=current_mode)
            )
            print("\n" + "-" * 40)
            print("Result:")
            print("-" * 40)
            print(result)
            print("-" * 40)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error during query: {e}")


async def main():
    """Main function"""
    # Check if OPENAI_API_KEY environment variable exists
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Error: OPENAI_API_KEY environment variable is not set. Please set this variable before running the program."
        )
        print("You can set the environment variable by running:")
        print("  export OPENAI_API_KEY='your-openai-api-key'")
        return

    # Create working directory if it doesn't exist
    if not os.path.exists(WORKING_DIR):
        os.makedirs(WORKING_DIR)
        print(f"Created working directory: {WORKING_DIR}")

    rag = None
    try:
        # Initialize RAG instance
        print("Initializing LightRAG...")
        rag = await initialize_rag()
        print("LightRAG initialized successfully!")

        # Check if data already exists
        graph_file = os.path.join(WORKING_DIR, "graph_chunk_entity_relation.graphml")
        if os.path.exists(graph_file):
            print(f"\nExisting data found in {WORKING_DIR}")
            response = input("Do you want to skip insertion and go directly to query mode? (y/n): ").strip().lower()
            if response != 'y':
                # Clear old data and re-insert
                print("Clearing old data...")
                files_to_delete = [
                    "graph_chunk_entity_relation.graphml",
                    "kv_store_doc_status.json",
                    "kv_store_full_docs.json",
                    "kv_store_text_chunks.json",
                    "kv_store_entity_chunks.json",
                    "kv_store_relation_chunks.json",
                    "kv_store_full_entities.json",
                    "kv_store_full_relations.json",
                    "vdb_chunks.json",
                    "vdb_entities.json",
                    "vdb_relationships.json",
                ]
                for file in files_to_delete:
                    file_path = os.path.join(WORKING_DIR, file)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"  Deleted: {file}")
                
                # Re-initialize after clearing
                rag = await initialize_rag()
                
                # Insert logs
                inserted = await insert_logs(rag, LOGS_DIR)
                print(f"\nTotal files inserted: {inserted}")
        else:
            # Insert logs
            inserted = await insert_logs(rag, LOGS_DIR)
            print(f"\nTotal files inserted: {inserted}")

        # Start interactive query mode
        await interactive_query(rag)

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if rag:
            await rag.finalize_storages()
            print("LightRAG storages finalized.")


if __name__ == "__main__":
    # Configure logging before running the main function
    configure_logging()
    asyncio.run(main())
    print("\nDone!")

