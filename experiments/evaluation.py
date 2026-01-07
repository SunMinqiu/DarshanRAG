"""Evaluation functions for LightRAG experiment harness."""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

logger = logging.getLogger("lightrag_experiment.evaluation")


def evaluate_retrieval(
    retrieved_entities: List[str],
    retrieved_relations: List[Tuple[str, str]],
    expected_entities: Optional[List[str]] = None,
    expected_relations: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """Evaluate retrieval performance.
    
    Args:
        retrieved_entities: List of retrieved entity names
        retrieved_relations: List of (src, tgt) tuples for retrieved relations
        expected_entities: List of expected entity names (optional)
        expected_relations: List of (src, tgt) tuples for expected relations (optional)
    
    Returns:
        Dictionary with retrieval metrics
    """
    metrics = {
        "num_retrieved_entities": len(retrieved_entities),
        "num_retrieved_relations": len(retrieved_relations),
    }
    
    # Entity evaluation
    if expected_entities is not None:
        expected_set = set(expected_entities)
        retrieved_set = set(retrieved_entities)
        
        true_positives = len(expected_set & retrieved_set)
        false_positives = len(retrieved_set - expected_set)
        false_negatives = len(expected_set - retrieved_set)
        
        precision = true_positives / len(retrieved_set) if len(retrieved_set) > 0 else 0.0
        recall = true_positives / len(expected_set) if len(expected_set) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        metrics.update({
            "entity_precision": precision,
            "entity_recall": recall,
            "entity_f1": f1,
            "entity_true_positives": true_positives,
            "entity_false_positives": false_positives,
            "entity_false_negatives": false_negatives,
            "num_expected_entities": len(expected_set),
        })
    else:
        metrics.update({
            "entity_precision": None,
            "entity_recall": None,
            "entity_f1": None,
        })
    
    # Relation evaluation
    if expected_relations is not None:
        # Normalize relations to handle undirected edges
        def normalize_rel(src: str, tgt: str) -> Tuple[str, str]:
            return tuple(sorted([src, tgt]))
        
        expected_set = {normalize_rel(src, tgt) for src, tgt in expected_relations}
        retrieved_set = {normalize_rel(src, tgt) for src, tgt in retrieved_relations}
        
        true_positives = len(expected_set & retrieved_set)
        false_positives = len(retrieved_set - expected_set)
        false_negatives = len(expected_set - retrieved_set)
        
        precision = true_positives / len(retrieved_set) if len(retrieved_set) > 0 else 0.0
        recall = true_positives / len(expected_set) if len(expected_set) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        metrics.update({
            "relation_precision": precision,
            "relation_recall": recall,
            "relation_f1": f1,
            "relation_true_positives": true_positives,
            "relation_false_positives": false_positives,
            "relation_false_negatives": false_negatives,
            "num_expected_relations": len(expected_set),
        })
    else:
        metrics.update({
            "relation_precision": None,
            "relation_recall": None,
            "relation_f1": None,
        })
    
    return metrics


def extract_retrieved_entities_and_relations(query_result: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Extract retrieved entities and relations from query result.
    
    Args:
        query_result: Query result dictionary from LightRAG
    
    Returns:
        (retrieved_entities, retrieved_relations) tuple
    """
    retrieved_entities = []
    retrieved_relations = []
    
    # First check retrieved_data field (from aquery_data or aquery_complete)
    retrieved_data = query_result.get("retrieved_data", {})
    
    if "entities" in retrieved_data:
        for entity in retrieved_data["entities"]:
            if isinstance(entity, dict) and "entity_name" in entity:
                entity_name = entity["entity_name"]
                if entity_name not in retrieved_entities:
                    retrieved_entities.append(entity_name)
            elif isinstance(entity, str):
                if entity not in retrieved_entities:
                    retrieved_entities.append(entity)
    
    if "relations" in retrieved_data:
        for rel in retrieved_data["relations"]:
            if isinstance(rel, dict):
                src = rel.get("src_id") or rel.get("source") or rel.get("src")
                tgt = rel.get("tgt_id") or rel.get("target") or rel.get("tgt")
                if src and tgt:
                    rel_tuple = (str(src), str(tgt))
                    if rel_tuple not in retrieved_relations:
                        retrieved_relations.append(rel_tuple)
            elif isinstance(rel, (list, tuple)) and len(rel) >= 2:
                rel_tuple = (str(rel[0]), str(rel[1]))
                if rel_tuple not in retrieved_relations:
                    retrieved_relations.append(rel_tuple)
    
    # Also check context field (for backward compatibility)
    if "context" in query_result:
        context = query_result["context"]
        
        # Extract entities
        if "entities" in context:
            for entity in context["entities"]:
                if isinstance(entity, dict) and "entity_name" in entity:
                    entity_name = entity["entity_name"]
                    if entity_name not in retrieved_entities:
                        retrieved_entities.append(entity_name)
                elif isinstance(entity, str):
                    if entity not in retrieved_entities:
                        retrieved_entities.append(entity)
        
        # Extract relations
        if "relations" in context:
            for rel in context["relations"]:
                if isinstance(rel, dict):
                    src = rel.get("src_id") or rel.get("source") or rel.get("src")
                    tgt = rel.get("tgt_id") or rel.get("target") or rel.get("tgt")
                    if src and tgt:
                        rel_tuple = (str(src), str(tgt))
                        if rel_tuple not in retrieved_relations:
                            retrieved_relations.append(rel_tuple)
                elif isinstance(rel, (list, tuple)) and len(rel) >= 2:
                    rel_tuple = (str(rel[0]), str(rel[1]))
                    if rel_tuple not in retrieved_relations:
                        retrieved_relations.append(rel_tuple)
    
    return retrieved_entities, retrieved_relations


def evaluate_generation(
    generated_answer: str,
    expected_answer: str,
    judge_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate generation quality.
    
    Currently implements simple string-based metrics.
    Can be extended with LLM-based evaluation if judge_model is provided.
    
    Args:
        generated_answer: Generated answer text
        expected_answer: Expected answer text
        judge_model: Optional LLM model for evaluation (not implemented yet)
    
    Returns:
        Dictionary with generation metrics
    """
    metrics = {
        "generated_length": len(generated_answer),
        "expected_length": len(expected_answer),
    }
    
    # Simple string-based metrics
    generated_lower = generated_answer.lower().strip()
    expected_lower = expected_answer.lower().strip()
    
    # Exact match
    exact_match = (generated_lower == expected_lower)
    metrics["exact_match"] = exact_match
    
    # Token overlap (simple word-based)
    gen_tokens = set(generated_lower.split())
    exp_tokens = set(expected_lower.split())
    
    if len(exp_tokens) > 0:
        overlap = len(gen_tokens & exp_tokens)
        token_precision = overlap / len(gen_tokens) if len(gen_tokens) > 0 else 0.0
        token_recall = overlap / len(exp_tokens)
        token_f1 = 2 * token_precision * token_recall / (token_precision + token_recall) if (token_precision + token_recall) > 0 else 0.0
        
        metrics.update({
            "token_overlap": overlap,
            "token_precision": token_precision,
            "token_recall": token_recall,
            "token_f1": token_f1,
        })
    else:
        metrics.update({
            "token_overlap": 0,
            "token_precision": 0.0,
            "token_recall": 0.0,
            "token_f1": 0.0,
        })
    
    # LLM-based evaluation (placeholder for future implementation)
    if judge_model is not None:
        logger.warning("LLM-based evaluation not yet implemented, using string-based metrics only")
        metrics["llm_evaluation"] = None
    
    return metrics


def compute_summary_metrics(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate metrics across all queries.
    
    Args:
        all_results: List of result dictionaries (one per query/mode combination)
    
    Returns:
        Dictionary with summary metrics
    """
    summary = {
        "total_queries": len(all_results),
        "modes": list(set(r.get("mode", "unknown") for r in all_results)),
    }
    
    # Aggregate retrieval metrics
    entity_f1_scores = [r.get("retrieval_metrics", {}).get("entity_f1") for r in all_results if r.get("retrieval_metrics", {}).get("entity_f1") is not None]
    relation_f1_scores = [r.get("retrieval_metrics", {}).get("relation_f1") for r in all_results if r.get("retrieval_metrics", {}).get("relation_f1") is not None]
    token_f1_scores = [r.get("generation_metrics", {}).get("token_f1") for r in all_results if r.get("generation_metrics", {}).get("token_f1") is not None]
    
    if entity_f1_scores:
        summary["mean_entity_f1"] = sum(entity_f1_scores) / len(entity_f1_scores)
        summary["std_entity_f1"] = (sum((x - summary["mean_entity_f1"]) ** 2 for x in entity_f1_scores) / len(entity_f1_scores)) ** 0.5
    
    if relation_f1_scores:
        summary["mean_relation_f1"] = sum(relation_f1_scores) / len(relation_f1_scores)
        summary["std_relation_f1"] = (sum((x - summary["mean_relation_f1"]) ** 2 for x in relation_f1_scores) / len(relation_f1_scores)) ** 0.5
    
    if token_f1_scores:
        summary["mean_token_f1"] = sum(token_f1_scores) / len(token_f1_scores)
        summary["std_token_f1"] = (sum((x - summary["mean_token_f1"]) ** 2 for x in token_f1_scores) / len(token_f1_scores)) ** 0.5
    
    # Per-mode summaries
    mode_summaries = {}
    for mode in summary["modes"]:
        mode_results = [r for r in all_results if r.get("mode") == mode]
        mode_summaries[mode] = compute_summary_metrics(mode_results)
    
    summary["per_mode"] = mode_summaries
    
    return summary
