#!/usr/bin/env python3
"""LightRAG Experiment Harness for Darshan Logs Evaluation.

This script loads a custom knowledge graph, runs queries in hybrid and mix modes,
and evaluates retrieval and generation performance.
"""

import os
import sys
import json
import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Add parent directory to path to import lightrag
sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import (
    openai_complete_if_cache,
    openai_embed,
)
from lightrag.utils import EmbeddingFunc, setup_logger as setup_lightrag_logger
import numpy as np

# Import local modules
from utils_experiment import (
    setup_logging,
    load_config,
    save_config,
    load_custom_kg,
    load_queries,
    load_ground_truth,
    get_run_id,
    get_working_dir,
    save_results,
    validate_custom_kg,
    create_synthetic_chunks,
    merge_configs,
)
from evaluation import (
    evaluate_retrieval,
    extract_retrieved_entities_and_relations,
    evaluate_generation,
    compute_summary_metrics,
)


class ExperimentHarness:
    """Main experiment harness for evaluating LightRAG."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """Initialize experiment harness.
        
        Args:
            config: Configuration dictionary
            logger: Logger instance
        """
        self.config = config
        self.logger = logger
        self.rag: Optional[LightRAG] = None
        
        # Extract configuration sections
        self.models_config = config.get("models", {})
        self.retrieval_config = config.get("retrieval", {})
        self.storage_config = config.get("storage", {})
        self.generation_config = config.get("generation", {})
        self.inputs_config = config.get("inputs", {})
        self.chunks_config = config.get("chunks", {})
        self.eval_config = config.get("evaluation", {})
        
        # Get API key
        self.api_key = self.models_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY env var or config.models.api_key")
    
    async def initialize_lightrag(self) -> None:
        """Initialize LightRAG instance."""
        self.logger.info("Initializing LightRAG...")
        
        # Get working directory
        working_dir = get_working_dir(self.config)
        self.logger.info(f"Working directory: {working_dir}")
        
        # Setup embedding function
        embed_model = self.models_config.get("embed_model", "text-embedding-3-large")
        self.logger.info(f"Using embedding model: {embed_model}")
        
        # Determine embedding dimension based on model
        if "3-large" in embed_model:
            embedding_dim = 3072
        elif "3-small" in embed_model:
            embedding_dim = 1536
        else:
            embedding_dim = 1536  # Default fallback
        
        async def embedding_func_impl(texts: List[str]) -> np.ndarray:
            return await openai_embed.func(
                texts,
                model=embed_model,
                api_key=self.api_key,
                base_url=self.models_config.get("base_url"),
            )
        
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            max_token_size=8192,
            func=embedding_func_impl
        )
        
        # Setup LLM function
        gen_model = self.models_config.get("gen_model", "gpt-4o")
        self.logger.info(f"Using generation model: {gen_model}")
        
        async def llm_model_func(
            prompt: str,
            system_prompt: Optional[str] = None,
            history_messages: List[Dict[str, str]] = [],
            **kwargs
        ) -> str:
            # Build kwargs from generation config
            llm_kwargs = {
                "temperature": self.generation_config.get("temperature", 0.1),
                "max_tokens": self.generation_config.get("max_output_tokens", 2000),
            }
            
            # Add seed if provided
            seed = self.generation_config.get("seed")
            if seed is not None:
                llm_kwargs["seed"] = int(seed)
            
            # Merge with any additional kwargs
            llm_kwargs.update(kwargs)
            
            return await openai_complete_if_cache(
                model=gen_model,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=self.api_key,
                base_url=self.models_config.get("base_url"),
                **llm_kwargs
            )
        
        # Initialize LightRAG
        self.rag = LightRAG(
            working_dir=working_dir,
            embedding_func=embedding_func,
            llm_model_func=llm_model_func,
            graph_storage=self.storage_config.get("graph_storage", "NetworkXStorage"),
            vector_storage=self.storage_config.get("vector_storage", "NanoVectorDBStorage"),
            kv_storage=self.storage_config.get("kv_storage", "JsonKVStorage"),
            workspace=self.storage_config.get("workspace", ""),
            top_k=self.retrieval_config.get("top_k", 60),
            chunk_top_k=self.retrieval_config.get("chunk_top_k", 20),
            max_entity_tokens=self.retrieval_config.get("max_entity_tokens", 6000),
            max_relation_tokens=self.retrieval_config.get("max_relation_tokens", 8000),
            max_total_tokens=self.retrieval_config.get("max_total_tokens", 30000),
            cosine_threshold=self.retrieval_config.get("cosine_better_than_threshold", 0.2),
            enable_llm_cache=self.storage_config.get("enable_llm_cache", True),
            enable_llm_cache_for_entity_extract=self.storage_config.get("enable_llm_cache_for_extract", True),
            max_parallel_insert=self.storage_config.get("max_parallel_insert", 2),
        )
        
        # IMPORTANT: Initialize storages
        await self.rag.initialize_storages()
        self.logger.info("LightRAG initialized successfully")
    
    async def load_knowledge_graph(self) -> None:
        """Load custom knowledge graph into LightRAG."""
        if self.rag is None:
            raise RuntimeError("LightRAG not initialized. Call initialize_lightrag() first.")
        
        kg_path = self.inputs_config.get("kg_path")
        if not kg_path:
            raise ValueError("kg_path not specified in config.inputs.kg_path")
        
        self.logger.info(f"Loading knowledge graph from: {kg_path}")
        
        # Load and validate KG
        kg = load_custom_kg(kg_path)
        is_valid, error_msg = validate_custom_kg(kg)
        if not is_valid:
            raise ValueError(f"Invalid custom_kg schema: {error_msg}")
        
        # Check for chunks
        has_chunks = "chunks" in kg and len(kg.get("chunks", [])) > 0
        self.logger.info(f"Chunks provided: {has_chunks}")
        
        if not has_chunks:
            if self.chunks_config.get("synthetic_chunks", False):
                template = self.chunks_config.get("synthetic_chunk_template", "Summary for source_id: {source_id}")
                self.logger.warning("Creating synthetic chunks (chunks_provided=false)")
                kg = create_synthetic_chunks(kg, template)
            else:
                self.logger.info("No chunks provided, proceeding with entities and relations only")
        
        # Insert KG
        self.logger.info(f"Inserting KG: {len(kg.get('entities', []))} entities, {len(kg.get('relationships', []))} relationships, {len(kg.get('chunks', []))} chunks")
        await self.rag.ainsert_custom_kg(kg)
        self.logger.info("Knowledge graph loaded successfully")
    
    async def run_query(
        self,
        query: str,
        mode: str,
        query_id: str,
        retrieval_only: bool = False,
    ) -> Dict[str, Any]:
        """Run a single query.
        
        Args:
            query: Query text
            mode: Query mode ("hybrid", "mix", etc.)
            query_id: Query identifier
            retrieval_only: If True, only retrieve context without generation
        
        Returns:
            Query result dictionary
        """
        if self.rag is None:
            raise RuntimeError("LightRAG not initialized")
        
        self.logger.info(f"Running query {query_id} in mode '{mode}'")
        
        # Build QueryParam
        query_param = QueryParam(
            mode=mode,
            top_k=self.retrieval_config.get("top_k", 60),
            chunk_top_k=self.retrieval_config.get("chunk_top_k", 20),
            max_entity_tokens=self.retrieval_config.get("max_entity_tokens", 6000),
            max_relation_tokens=self.retrieval_config.get("max_relation_tokens", 8000),
            max_total_tokens=self.retrieval_config.get("max_total_tokens", 30000),
            enable_rerank=self.retrieval_config.get("enable_rerank", False),
            only_need_context=retrieval_only,
        )
        
        # Run query
        if retrieval_only:
            # Only retrieve context
            result_data = await self.rag.aquery_data(query, param=query_param)
            result = {
                "mode": mode,
                "query_id": query_id,
                "query": query,
                "retrieved_data": result_data.get("data", {}),
                "generated_answer": None,
            }
        else:
            # Full query with generation
            result_data = await self.rag.aquery_complete(query, param=query_param)
            # Extract response from llm_response.content
            llm_response = result_data.get("llm_response", {})
            generated_answer = llm_response.get("content") if isinstance(llm_response, dict) else None
            
            result = {
                "mode": mode,
                "query_id": query_id,
                "query": query,
                "retrieved_data": result_data.get("data", {}),
                "generated_answer": generated_answer or "",
                "context": result_data.get("context", {}),
            }
        
        # Extract retrieved entities and relations
        retrieved_entities, retrieved_relations = extract_retrieved_entities_and_relations(result)
        result["retrieved_entities"] = retrieved_entities
        result["retrieved_relations"] = retrieved_relations
        
        self.logger.info(f"Query {query_id} ({mode}): Retrieved {len(retrieved_entities)} entities, {len(retrieved_relations)} relations")
        
        return result
    
    async def evaluate_query(
        self,
        query_result: Dict[str, Any],
        ground_truth: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate a single query result against ground truth.
        
        Args:
            query_result: Query result dictionary
            ground_truth: Ground truth dictionary for this query
        
        Returns:
            Evaluation result dictionary
        """
        query_id = query_result["query_id"]
        mode = query_result["mode"]
        
        eval_result = {
            "query_id": query_id,
            "mode": mode,
            "query": query_result["query"],
        }
        
        # Get ground truth for this query
        gt = ground_truth.get(query_id, {})
        
        # Retrieval evaluation
        expected_entities = gt.get("expected_entities")
        expected_relations = gt.get("expected_relations")
        
        retrieved_entities = query_result.get("retrieved_entities", [])
        retrieved_relations = query_result.get("retrieved_relations", [])
        
        # Convert expected_relations to tuples if needed
        if expected_relations and len(expected_relations) > 0:
            if isinstance(expected_relations[0], list):
                expected_relations = [tuple(r) for r in expected_relations]
        
        retrieval_metrics = evaluate_retrieval(
            retrieved_entities=retrieved_entities,
            retrieved_relations=retrieved_relations,
            expected_entities=expected_entities,
            expected_relations=expected_relations,
        )
        eval_result["retrieval_metrics"] = retrieval_metrics
        
        # Generation evaluation (if not retrieval_only)
        if query_result.get("generated_answer") is not None:
            expected_answer = gt.get("expected_answer")
            if expected_answer:
                judge_model = self.models_config.get("judge_model")
                generation_metrics = evaluate_generation(
                    generated_answer=query_result["generated_answer"],
                    expected_answer=expected_answer,
                    judge_model=judge_model,
                )
                eval_result["generation_metrics"] = generation_metrics
            else:
                self.logger.warning(f"No expected_answer in ground truth for query {query_id}")
                eval_result["generation_metrics"] = None
        else:
            eval_result["generation_metrics"] = None
        
        return eval_result
    
    async def run_experiment(self) -> Dict[str, Any]:
        """Run complete experiment.
        
        Returns:
            Experiment results dictionary
        """
        self.logger.info("=" * 80)
        self.logger.info("Starting LightRAG Experiment")
        self.logger.info("=" * 80)
        
        # Initialize LightRAG
        await self.initialize_lightrag()
        
        # Load knowledge graph
        await self.load_knowledge_graph()
        
        # Load queries
        queries_path = self.inputs_config.get("queries_path")
        if not queries_path:
            raise ValueError("queries_path not specified in config.inputs.queries_path")
        
        queries = load_queries(queries_path)
        self.logger.info(f"Loaded {len(queries)} queries")
        
        # Load ground truth
        ground_truth_path = self.inputs_config.get("ground_truth_path")
        ground_truth = {}
        if ground_truth_path:
            ground_truth = load_ground_truth(ground_truth_path)
            self.logger.info(f"Loaded ground truth for {len(ground_truth)} queries")
        
        # Get modes to run
        modes = self.retrieval_config.get("modes", ["hybrid", "mix"])
        self.logger.info(f"Running queries in modes: {modes}")
        
        # Run queries
        all_results = []
        retrieval_only = self.eval_config.get("retrieval_only", False)
        
        for query_item in queries:
            query_id = query_item.get("query_id", "unknown")
            query = query_item["query"]
            
            for mode in modes:
                try:
                    # Run query
                    query_result = await self.run_query(
                        query=query,
                        mode=mode,
                        query_id=query_id,
                        retrieval_only=retrieval_only,
                    )
                    
                    # Evaluate if ground truth available
                    if ground_truth:
                        eval_result = await self.evaluate_query(query_result, ground_truth)
                        query_result.update(eval_result)
                    
                    all_results.append(query_result)
                    
                except Exception as e:
                    self.logger.error(f"Error running query {query_id} in mode {mode}: {e}", exc_info=True)
                    all_results.append({
                        "query_id": query_id,
                        "mode": mode,
                        "query": query,
                        "error": str(e),
                    })
        
        # Compute summary metrics
        summary = compute_summary_metrics(all_results)
        
        # Finalize results
        experiment_results = {
            "config": self.config,
            "run_id": get_run_id(self.config),
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "results": all_results,
        }
        
        self.logger.info("=" * 80)
        self.logger.info("Experiment completed")
        self.logger.info("=" * 80)
        
        return experiment_results
    
    async def finalize(self) -> None:
        """Cleanup and finalize."""
        if self.rag is not None:
            await self.rag.finalize_storages()
            self.logger.info("LightRAG storages finalized")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LightRAG Experiment Harness for Darshan Logs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Config file
    parser.add_argument(
        "--config",
        type=str,
        default="./experiments/config.yaml",
        help="Path to configuration YAML file",
    )
    
    # Common overrides
    parser.add_argument("--kg-path", type=str, help="Override kg_path")
    parser.add_argument("--queries-path", type=str, help="Override queries_path")
    parser.add_argument("--ground-truth-path", type=str, help="Override ground_truth_path")
    parser.add_argument("--gen-model", type=str, help="Override generation model")
    parser.add_argument("--embed-model", type=str, help="Override embedding model")
    parser.add_argument("--run-id", type=str, help="Override run_id (creates subdirectory)")
    parser.add_argument("--working-dir", type=str, help="Override working_dir")
    parser.add_argument("--temperature", type=float, help="Override temperature")
    parser.add_argument("--top-k", type=int, help="Override top_k")
    parser.add_argument("--modes", type=str, nargs="+", help="Override query modes (e.g., hybrid mix)")
    parser.add_argument("--retrieval-only", action="store_true", help="Run retrieval-only evaluation")
    
    args = parser.parse_args()
    
    # Load base config
    config = load_config(args.config)
    
    # Apply CLI overrides
    override_config = {}
    if args.kg_path:
        override_config.setdefault("inputs", {})["kg_path"] = args.kg_path
    if args.queries_path:
        override_config.setdefault("inputs", {})["queries_path"] = args.queries_path
    if args.ground_truth_path:
        override_config.setdefault("inputs", {})["ground_truth_path"] = args.ground_truth_path
    if args.gen_model:
        override_config.setdefault("models", {})["gen_model"] = args.gen_model
    if args.embed_model:
        override_config.setdefault("models", {})["embed_model"] = args.embed_model
    if args.run_id:
        override_config.setdefault("storage", {})["run_id"] = args.run_id
    if args.working_dir:
        override_config.setdefault("storage", {})["working_dir"] = args.working_dir
    if args.temperature is not None:
        override_config.setdefault("generation", {})["temperature"] = args.temperature
    if args.top_k:
        override_config.setdefault("retrieval", {})["top_k"] = args.top_k
    if args.modes:
        override_config.setdefault("retrieval", {})["modes"] = args.modes
    if args.retrieval_only:
        override_config.setdefault("evaluation", {})["retrieval_only"] = True
    
    config = merge_configs(config, override_config)
    
    # Setup logging
    run_id = get_run_id(config)
    log_file_template = config.get("evaluation", {}).get("log_file", "./experiments/logs/experiment_{timestamp}.log")
    log_file = log_file_template.format(timestamp=run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    log_level = config.get("evaluation", {}).get("log_level", "INFO")
    
    logger = setup_logging(log_file=log_file, log_level=log_level)
    
    # Save merged config
    output_dir = config.get("evaluation", {}).get("output_dir", "./experiments/results")
    os.makedirs(output_dir, exist_ok=True)
    config_save_path = os.path.join(output_dir, f"config_{run_id or 'latest'}.yaml")
    save_config(config, config_save_path)
    logger.info(f"Saved configuration to: {config_save_path}")
    
    # Run experiment
    harness = ExperimentHarness(config, logger)
    
    try:
        results = await harness.run_experiment()
        
        # Save results
        results_file = os.path.join(output_dir, f"results_{run_id or 'latest'}.json")
        save_results(results, results_file)
        logger.info(f"Saved results to: {results_file}")
        
        # Print summary
        summary = results.get("summary", {})
        logger.info("\n" + "=" * 80)
        logger.info("EXPERIMENT SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total queries: {summary.get('total_queries', 0)}")
        logger.info(f"Modes: {summary.get('modes', [])}")
        if "mean_entity_f1" in summary:
            logger.info(f"Mean Entity F1: {summary['mean_entity_f1']:.4f} ± {summary.get('std_entity_f1', 0):.4f}")
        if "mean_relation_f1" in summary:
            logger.info(f"Mean Relation F1: {summary['mean_relation_f1']:.4f} ± {summary.get('std_relation_f1', 0):.4f}")
        if "mean_token_f1" in summary:
            logger.info(f"Mean Token F1: {summary['mean_token_f1']:.4f} ± {summary.get('std_token_f1', 0):.4f}")
        
    finally:
        await harness.finalize()


if __name__ == "__main__":
    asyncio.run(main())
