#!/bin/bash
# Test script for Darshan signal extraction tool

echo "================================================"
echo "Darshan Signal Extraction Tool - Test Script"
echo "================================================"
echo ""

# Set paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SCRIPT_DIR}/scripts/process_darshan_signals.py"
EXAMPLE_FILE="${SCRIPT_DIR}/../data/examples/Darshan_log_example.txt"

# Test 1: Check if script exists
echo "Test 1: Checking if script exists..."
if [ -f "$SCRIPT" ]; then
    echo "  ✓ Script found: $SCRIPT"
else
    echo "  ✗ Script not found: $SCRIPT"
    exit 1
fi
echo ""

# Test 2: Check if example file exists
echo "Test 2: Checking if example file exists..."
if [ -f "$EXAMPLE_FILE" ]; then
    echo "  ✓ Example file found: $EXAMPLE_FILE"
else
    echo "  ✗ Example file not found: $EXAMPLE_FILE"
    echo "  Please ensure the example file is in the correct location"
    exit 1
fi
echo ""

# Test 3: Process single file
echo "Test 3: Processing single example file..."
python3 "$SCRIPT" "$EXAMPLE_FILE"
if [ $? -eq 0 ]; then
    echo "  ✓ Single file processing completed successfully"
else
    echo "  ✗ Single file processing failed"
    exit 1
fi
echo ""

# Check output file
OUTPUT_FILE="${SCRIPT_DIR}/../data/examples/Darshan_log_example_signals_v1.txt"
echo "Test 4: Verifying output file..."
if [ -f "$OUTPUT_FILE" ]; then
    echo "  ✓ Output file created: $OUTPUT_FILE"
    echo ""
    echo "  Output file preview (first 30 lines):"
    echo "  ----------------------------------------"
    head -n 30 "$OUTPUT_FILE" | sed 's/^/  /'
    echo "  ----------------------------------------"
    echo ""
    echo "  File size: $(wc -c < "$OUTPUT_FILE") bytes"
    echo "  Line count: $(wc -l < "$OUTPUT_FILE") lines"
else
    echo "  ✗ Output file not found: $OUTPUT_FILE"
    exit 1
fi
echo ""

# Test 5: Show help
echo "Test 5: Displaying help information..."
python3 "$SCRIPT" --help
echo ""

echo "================================================"
echo "All tests completed successfully!"
echo "================================================"
echo ""
echo "You can now use the tool with the following commands:"
echo ""
echo "  # Process a single file:"
echo "  python3 $SCRIPT input.txt"
echo ""
echo "  # Process a directory:"
echo "  python3 $SCRIPT /path/to/logs/"
echo ""
echo "  # Process with custom output:"
echo "  python3 $SCRIPT input.txt -o output.txt"
echo ""
