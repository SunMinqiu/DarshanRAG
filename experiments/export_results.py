#!/usr/bin/env python3
"""Export experiment results to CSV format for analysis."""

import json
import csv
import argparse
from pathlib import Path
from typing import Dict, Any, List


def export_results_to_csv(results_file: str, output_file: str = None) -> None:
    """Export experiment results to CSV.
    
    Args:
        results_file: Path to results JSON file
        output_file: Path to output CSV file (auto-generated if not provided)
    """
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    if output_file is None:
        output_file = results_file.replace('.json', '.csv')
    
    # Extract all results
    all_results = results.get("results", [])
    
    # Prepare CSV rows
    rows = []
    for result in all_results:
        row = {
            "query_id": result.get("query_id", ""),
            "mode": result.get("mode", ""),
            "query": result.get("query", ""),
            "num_retrieved_entities": len(result.get("retrieved_entities", [])),
            "num_retrieved_relations": len(result.get("retrieved_relations", [])),
            "generated_answer": result.get("generated_answer", "")[:200] + "..." if len(result.get("generated_answer", "")) > 200 else result.get("generated_answer", ""),
        }
        
        # Add retrieval metrics
        retrieval_metrics = result.get("retrieval_metrics", {})
        row.update({
            "entity_precision": retrieval_metrics.get("entity_precision"),
            "entity_recall": retrieval_metrics.get("entity_recall"),
            "entity_f1": retrieval_metrics.get("entity_f1"),
            "relation_precision": retrieval_metrics.get("relation_precision"),
            "relation_recall": retrieval_metrics.get("relation_recall"),
            "relation_f1": retrieval_metrics.get("relation_f1"),
        })
        
        # Add generation metrics
        generation_metrics = result.get("generation_metrics", {})
        if generation_metrics:
            row.update({
                "token_f1": generation_metrics.get("token_f1"),
                "token_precision": generation_metrics.get("token_precision"),
                "token_recall": generation_metrics.get("token_recall"),
                "exact_match": generation_metrics.get("exact_match"),
            })
        else:
            row.update({
                "token_f1": None,
                "token_precision": None,
                "token_recall": None,
                "exact_match": None,
            })
        
        rows.append(row)
    
    # Write CSV
    if rows:
        fieldnames = rows[0].keys()
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"Exported {len(rows)} rows to {output_file}")
    else:
        print("No results to export")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export experiment results to CSV")
    parser.add_argument("results_file", help="Path to results JSON file")
    parser.add_argument("-o", "--output", help="Output CSV file path")
    args = parser.parse_args()
    
    export_results_to_csv(args.results_file, args.output)
