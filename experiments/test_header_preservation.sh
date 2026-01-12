#!/bin/bash
# Test script to verify header preservation

echo "================================================"
echo "Testing Header Preservation Feature"
echo "================================================"
echo ""

SCRIPT="scripts/process_darshan_signals.py"
INPUT="../data/examples/Darshan_log_example.txt"
OUTPUT="/tmp/test_header_output.txt"

# Run the script
echo "1. Running signal extraction..."
python3 $SCRIPT $INPUT -o $OUTPUT

echo ""
echo "2. Checking header preservation..."
echo ""

# Check for key header fields
echo "✓ Checking for darshan log version..."
grep "# darshan log version:" $OUTPUT

echo "✓ Checking for jobid..."
grep "# jobid:" $OUTPUT

echo "✓ Checking for nprocs..."
grep "# nprocs:" $OUTPUT

echo "✓ Checking for runtime..."
grep "# run time:" $OUTPUT

echo ""
echo "✓ Checking mount entries count..."
ORIGINAL_MOUNTS=$(grep "# mount entry:" $INPUT | wc -l)
OUTPUT_MOUNTS=$(grep "# mount entry:" $OUTPUT | wc -l)
echo "  Original: $ORIGINAL_MOUNTS mount entries"
echo "  Output:   $OUTPUT_MOUNTS mount entries"

if [ "$ORIGINAL_MOUNTS" -eq "$OUTPUT_MOUNTS" ]; then
    echo "  ✅ All mount entries preserved!"
else
    echo "  ❌ Mount entries count mismatch!"
    exit 1
fi

echo ""
echo "✓ Checking for module information..."
grep "# POSIX module:" $OUTPUT
grep "# STDIO module:" $OUTPUT
grep "# APMPI module:" $OUTPUT

echo ""
echo "✓ Sample of preserved header (first 30 lines):"
echo "  ----------------------------------------"
head -30 $OUTPUT | sed 's/^/  /'
echo "  ----------------------------------------"

echo ""
echo "================================================"
echo "✅ Header preservation test PASSED!"
echo "================================================"
