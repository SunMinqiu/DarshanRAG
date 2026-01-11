#!/bin/bash
#
# DarshanRAG Data Management Script
#
# This script helps manage experimental data, logs, and knowledge graphs
# for the DarshanRAG project.
#
# Usage:
#   ./scripts/organize_data.sh <command> [arguments]
#
# Commands:
#   help         - Show this help message
#   check        - Check disk usage of data directories
#   clean        - Clean temporary files and old experiments
#   parse <date> - Parse darshan logs for a specific date
#   compress     - Compress large JSON files
#   init         - Initialize directory structure
#

set -e  # Exit on error

# ============================================================
# Configuration
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Import paths from config_paths.py
DATA_ROOT="$PROJECT_ROOT/data"
KG_ROOT="$PROJECT_ROOT/knowledge_graphs"
EXPERIMENTS_ROOT="$PROJECT_ROOT/experiments"
RESULTS_ROOT="$EXPERIMENTS_ROOT/results"
STORAGE_ROOT="$EXPERIMENTS_ROOT/storage"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================
# Helper Functions
# ============================================================

print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================================
# Commands
# ============================================================

show_help() {
    cat << EOF
DarshanRAG Data Management Script

Usage:
  ./scripts/organize_data.sh <command> [arguments]

Commands:
  help              - Show this help message
  check             - Check disk usage of data directories
  clean [--force]   - Clean temporary files and old experiments
  parse <date>      - Parse darshan logs for a specific date (e.g., 2025-1-1)
  compress          - Compress large JSON files in knowledge_graphs/
  init              - Initialize/ensure directory structure exists
  list              - List all experiments and their sizes
  backup <name>     - Create a backup of knowledge graphs

Examples:
  ./scripts/organize_data.sh check
  ./scripts/organize_data.sh parse 2025-1-1
  ./scripts/organize_data.sh clean --force
  ./scripts/organize_data.sh compress

EOF
}

check_disk_usage() {
    print_header "Disk Usage Check"

    echo ""
    print_info "Project Root: $PROJECT_ROOT"
    du -sh "$PROJECT_ROOT" 2>/dev/null || echo "N/A"

    echo ""
    print_info "Data Directories:"
    for dir in "$DATA_ROOT" "$KG_ROOT" "$RESULTS_ROOT" "$STORAGE_ROOT"; do
        if [ -d "$dir" ]; then
            size=$(du -sh "$dir" 2>/dev/null | cut -f1)
            echo "  $(basename $dir): $size"
        else
            echo "  $(basename $dir): (not exist)"
        fi
    done

    echo ""
    print_info "Large files in knowledge_graphs/ (>10MB):"
    if [ -d "$KG_ROOT" ]; then
        find "$KG_ROOT" -type f -size +10M -exec ls -lh {} \; | awk '{print "  " $9 " - " $5}'
    else
        echo "  (directory not found)"
    fi

    echo ""
    print_info "Storage directories:"
    if [ -d "$STORAGE_ROOT" ]; then
        find "$STORAGE_ROOT" -maxdepth 1 -type d ! -path "$STORAGE_ROOT" -exec du -sh {} \; | sort -hr | head -10
    else
        echo "  (directory not found)"
    fi
}

clean_data() {
    local force=false

    if [ "$1" == "--force" ]; then
        force=true
    fi

    print_header "Clean Temporary Files"

    if [ "$force" == false ]; then
        print_warning "This will clean temporary files. Use --force to proceed."
        print_info "The following will be cleaned:"
        echo "  - Jupyter notebook checkpoints"
        echo "  - Python cache files"
        echo "  - Temporary experiment files (older than 7 days)"
        echo ""
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Cancelled."
            return
        fi
    fi

    # Clean Jupyter checkpoints
    print_info "Cleaning Jupyter checkpoints..."
    find "$EXPERIMENTS_ROOT" -type d -name ".ipynb_checkpoints" -exec rm -rf {} + 2>/dev/null || true

    # Clean Python cache
    print_info "Cleaning Python cache..."
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true

    # Clean old temporary files in results
    if [ -d "$RESULTS_ROOT" ]; then
        print_info "Cleaning old results (>7 days)..."
        find "$RESULTS_ROOT" -type f -mtime +7 -delete 2>/dev/null || true
    fi

    print_success "Cleanup complete!"
}

parse_logs() {
    local date="$1"

    if [ -z "$date" ]; then
        print_error "Date argument required! Usage: parse <date>"
        echo "Example: parse 2025-1-1"
        return 1
    fi

    print_header "Parse Darshan Logs for $date"

    local raw_dir="$DATA_ROOT/raw/$date"
    local parsed_dir="$DATA_ROOT/parsed/parsed-logs-$date"

    if [ ! -d "$raw_dir" ]; then
        print_error "Raw log directory not found: $raw_dir"
        print_info "Please place raw darshan logs in: $raw_dir"
        return 1
    fi

    # Check if darshan-parser is available
    if ! command -v darshan-parser &> /dev/null; then
        print_error "darshan-parser not found in PATH"
        print_info "Please install Darshan or add it to your PATH"
        return 1
    fi

    # Create parsed directory
    mkdir -p "$parsed_dir"

    # Find all darshan log files
    print_info "Searching for darshan logs in $raw_dir..."
    local log_files=$(find "$raw_dir" -type f \( -name "*.darshan" -o -name "*.darshan.*" \))
    local count=$(echo "$log_files" | wc -l)

    print_info "Found $count log files"

    # Parse each log file
    local i=0
    while IFS= read -r log_file; do
        if [ -z "$log_file" ]; then
            continue
        fi

        i=$((i + 1))
        local basename=$(basename "$log_file" | sed 's/\.darshan.*//')
        local output_file="$parsed_dir/${basename}.txt"

        echo -ne "\r[$i/$count] Parsing: $basename"
        darshan-parser "$log_file" > "$output_file" 2>/dev/null
    done <<< "$log_files"

    echo ""
    print_success "Parsed $count log files to: $parsed_dir"
}

compress_kgs() {
    print_header "Compress Knowledge Graphs"

    if [ ! -d "$KG_ROOT" ]; then
        print_warning "Knowledge graphs directory not found"
        return
    fi

    # Find large uncompressed JSON files (>10MB)
    local json_files=$(find "$KG_ROOT" -type f -name "*.json" -size +10M ! -name "*.gz")

    if [ -z "$json_files" ]; then
        print_info "No large JSON files found to compress"
        return
    fi

    print_info "Compressing large JSON files..."

    while IFS= read -r json_file; do
        if [ -z "$json_file" ]; then
            continue
        fi

        local size_before=$(du -h "$json_file" | cut -f1)
        echo "  Compressing $(basename $json_file) ($size_before)..."

        gzip -f "$json_file"

        local size_after=$(du -h "${json_file}.gz" | cut -f1)
        echo "    → ${size_after} (compressed)"
    done <<< "$json_files"

    print_success "Compression complete!"
}

init_dirs() {
    print_header "Initialize Directory Structure"

    # Use Python config_paths to create directories
    cd "$PROJECT_ROOT"
    python3 -c "from experiments.config_paths import ensure_dirs; ensure_dirs()"

    print_success "Directory structure initialized!"
}

list_experiments() {
    print_header "Experiments Overview"

    echo ""
    print_info "Knowledge Graphs:"
    if [ -d "$KG_ROOT" ]; then
        find "$KG_ROOT" -type f \( -name "*.json" -o -name "*.json.gz" \) -exec ls -lh {} \; | \
            awk '{print "  " $9 " - " $5}'
    fi

    echo ""
    print_info "Results Directories:"
    if [ -d "$RESULTS_ROOT" ]; then
        find "$RESULTS_ROOT" -maxdepth 1 -type d ! -path "$RESULTS_ROOT" -exec du -sh {} \; | sort -hr
    fi

    echo ""
    print_info "Storage Directories:"
    if [ -d "$STORAGE_ROOT" ]; then
        find "$STORAGE_ROOT" -maxdepth 1 -type d ! -path "$STORAGE_ROOT" -exec du -sh {} \; | sort -hr
    fi
}

backup_kgs() {
    local name="$1"

    if [ -z "$name" ]; then
        print_error "Backup name required! Usage: backup <name>"
        return 1
    fi

    print_header "Backup Knowledge Graphs"

    local backup_dir="$KG_ROOT/backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$backup_dir/kg_backup_${name}_${timestamp}.tar.gz"

    mkdir -p "$backup_dir"

    print_info "Creating backup: $backup_file"
    tar -czf "$backup_file" -C "$KG_ROOT" \
        --exclude="backups" \
        --exclude="*.tar.gz" \
        . 2>/dev/null || true

    local size=$(du -h "$backup_file" | cut -f1)
    print_success "Backup created: $backup_file ($size)"
}

# ============================================================
# Main
# ============================================================

main() {
    local command="${1:-help}"

    case "$command" in
        help)
            show_help
            ;;
        check)
            check_disk_usage
            ;;
        clean)
            clean_data "$2"
            ;;
        parse)
            parse_logs "$2"
            ;;
        compress)
            compress_kgs
            ;;
        init)
            init_dirs
            ;;
        list)
            list_experiments
            ;;
        backup)
            backup_kgs "$2"
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
