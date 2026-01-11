#!/usr/bin/env python3
"""Interactive query interface for LightRAG.
Allows you to query the loaded knowledge graph interactively.
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_embed, openai_complete_if_cache
from lightrag.utils import EmbeddingFunc
import numpy as np


async def interactive_query(
    working_dir: str = "./experiments/rag_storage",
    workspace: str = "",
    gen_model: str = "gpt-4o",
    embed_model: str = "text-embedding-3-large",
    api_key: str = None,
    base_url: str = None,
    temperature: float = 0.1,
    default_mode: str = "hybrid",
):
    """Interactive query interface.
    
    Args:
        working_dir: Working directory for LightRAG storage
        workspace: Workspace name
        gen_model: Generation model name
        embed_model: Embedding model name
        api_key: OpenAI API key
        base_url: OpenAI API base URL
        temperature: Generation temperature
        default_mode: Default query mode
    """
    # Get API key
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY env var")
    
    if base_url is None:
        base_url = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    
    print(f"Loading LightRAG from: {working_dir}")
    print(f"Workspace: {workspace or '(default)'}")
    print(f"Models: {gen_model} (gen), {embed_model} (embed)")
    print(f"Default mode: {default_mode}")
    print("\n" + "="*60)
    
    # Setup embedding function
    if "3-large" in embed_model:
        embedding_dim = 3072
    elif "3-small" in embed_model:
        embedding_dim = 1536
    else:
        embedding_dim = 1536
    
    async def embedding_func_impl(texts):
        return await openai_embed.func(
            texts,
            model=embed_model,
            api_key=api_key,
            base_url=base_url,
        )
    
    embedding_func = EmbeddingFunc(
        embedding_dim=embedding_dim,
        max_token_size=8192,
        func=embedding_func_impl
    )
    
    # Setup LLM function
    async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        return await openai_complete_if_cache(
            model=gen_model,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            **kwargs
        )
    
    # Initialize LightRAG
    print("Initializing LightRAG...")
    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=embedding_func,
        llm_model_func=llm_model_func,
        workspace=workspace,
    )
    
    await rag.initialize_storages()
    print("✅ LightRAG loaded successfully!\n")
    
    # Interactive loop
    current_mode = default_mode
    print("Commands:")
    print("  - Type your query to search")
    print("  - Type 'mode <mode_name>' to change query mode (hybrid, mix, local, global, naive)")
    print("  - Type 'quit' or 'exit' to exit")
    print("="*60 + "\n")
    
    try:
        while True:
            try:
                user_input = input(f"[{current_mode}] Query> ").strip()
                
                if not user_input:
                    continue
                
                # Check for exit
                if user_input.lower() in ["quit", "exit", "q"]:
                    print("Exiting...")
                    break
                
                # Check for mode change
                if user_input.lower().startswith("mode "):
                    new_mode = user_input[5:].strip().lower()
                    valid_modes = ["hybrid", "mix", "local", "global", "naive", "bypass"]
                    if new_mode in valid_modes:
                        current_mode = new_mode
                        print(f"Query mode changed to: {current_mode}")
                    else:
                        print(f"Invalid mode '{new_mode}'. Available: {', '.join(valid_modes)}")
                    continue
                
                # Run query
                print(f"\n[Searching in {current_mode} mode...]")
                
                query_param = QueryParam(mode=current_mode)
                result = await rag.aquery(user_input, param=query_param)
                
                print("\n" + "-"*60)
                print("Answer:")
                print("-"*60)
                print(result)
                print("-"*60 + "\n")
                
            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            except Exception as e:
                print(f"\nError: {e}\n")
                import traceback
                traceback.print_exc()
                print()
    
    finally:
        await rag.finalize_storages()


def main():
    parser = argparse.ArgumentParser(description="Interactive query interface for LightRAG")
    parser.add_argument("--working-dir", default="./experiments/rag_storage", help="Working directory")
    parser.add_argument("--workspace", default="", help="Workspace name")
    parser.add_argument("--gen-model", default="gpt-4o", help="Generation model")
    parser.add_argument("--embed-model", default="text-embedding-3-large", help="Embedding model")
    parser.add_argument("--api-key", help="OpenAI API key (or set OPENAI_API_KEY)")
    parser.add_argument("--base-url", help="OpenAI API base URL (or set OPENAI_API_BASE)")
    parser.add_argument("--temperature", type=float, default=0.1, help="Generation temperature")
    parser.add_argument("--mode", default="hybrid", help="Default query mode (hybrid, mix, local, global, naive)")
    
    args = parser.parse_args()
    
    asyncio.run(interactive_query(
        working_dir=args.working_dir,
        workspace=args.workspace,
        gen_model=args.gen_model,
        embed_model=args.embed_model,
        api_key=args.api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        default_mode=args.mode,
    ))


if __name__ == "__main__":
    main()
