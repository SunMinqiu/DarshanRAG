#!/usr/bin/env python3
"""
Test script for Darshan KG Builder

This script creates a mock Darshan log and tests the KG building pipeline.
"""

import json
import os
import tempfile
from pathlib import Path

# Import the KG builder modules
from build_darshan_kg import DarshanLogParser, KnowledgeGraphBuilder, find_log_files


def create_mock_darshan_log(output_path: str):
    """Create a mock Darshan log file for testing."""

    mock_log_content = """# darshan log version: 3.40
# compression method: ZLIB
# exe: /home/user/app/simulation.exe
# uid: 1001
# jobid: test_job_12345
# start_time: 1704067200
# start_time_asci: Mon Jan  1 00:00:00 2024
# end_time: 1704070800
# end_time_asci: Mon Jan  1 01:00:00 2024
# nprocs: 4
# run time: 3600

# mount table:
# mount[0] = lustre://scratch1
# mount[1] = nfs://home

# Module: POSIX

# <rank>	<file_id>	<counter>	<value>
0	hash_001	POSIX_OPENS	10
0	hash_001	POSIX_BYTES_READ	1048576000
0	hash_001	POSIX_BYTES_WRITTEN	524288000
0	hash_001	POSIX_READ_START_TIMESTAMP	1704067300
0	hash_001	POSIX_READ_END_TIMESTAMP	1704067600
0	hash_001	POSIX_WRITE_START_TIMESTAMP	1704067700
0	hash_001	POSIX_WRITE_END_TIMESTAMP	1704068000
0	hash_001	POSIX_FILE	/scratch1/data/output_rank0.h5

1	hash_002	POSIX_OPENS	8
1	hash_002	POSIX_BYTES_READ	1048576000
1	hash_002	POSIX_BYTES_WRITTEN	524288000
1	hash_002	POSIX_READ_START_TIMESTAMP	1704067305
1	hash_002	POSIX_READ_END_TIMESTAMP	1704067605
1	hash_002	POSIX_FILE	/scratch1/data/output_rank1.h5

-1	hash_shared	POSIX_OPENS	4
-1	hash_shared	POSIX_BYTES_READ	2097152000
-1	hash_shared	POSIX_BYTES_WRITTEN	0
-1	hash_shared	POSIX_READ_START_TIMESTAMP	1704067200
-1	hash_shared	POSIX_READ_END_TIMESTAMP	1704067500
-1	hash_shared	POSIX_FILE	/scratch1/checkpoint/ckpt_00100.h5

# Module: STDIO

0	stdio_001	STDIO_OPENS	5
0	stdio_001	STDIO_BYTES_READ	1024000
0	stdio_001	STDIO_BYTES_WRITTEN	2048000
0	stdio_001	STDIO_FILE	/home/user/app/log_rank0.txt

# Module: MPIIO

-1	mpiio_shared	MPIIO_OPENS	1
-1	mpiio_shared	MPIIO_BYTES_READ	4194304000
-1	mpiio_shared	MPIIO_BYTES_WRITTEN	4194304000
-1	mpiio_shared	MPIIO_FILE	/scratch1/restart/restart.mpi
"""

    with open(output_path, 'w') as f:
        f.write(mock_log_content)

    print(f"✅ Created mock Darshan log: {output_path}")


def test_log_parser():
    """Test the DarshanLogParser."""

    print("\n" + "="*70)
    print("TEST 1: DarshanLogParser")
    print("="*70)

    # Create temporary log file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_log_path = f.name

    try:
        # Create mock log
        create_mock_darshan_log(temp_log_path)

        # Parse the log
        parser = DarshanLogParser(temp_log_path)
        parsed_data = parser.parse()

        # Verify header
        print("\n📋 Header Information:")
        print(f"   Job ID: {parsed_data['header'].get('job_id')}")
        print(f"   Exe: {parsed_data['header'].get('exe')}")
        print(f"   Nprocs: {parsed_data['header'].get('nprocs')}")
        print(f"   Runtime: {parsed_data['header'].get('run_time')} seconds")

        assert parsed_data['header'].get('job_id') == 'test_job_12345', "Job ID mismatch"
        assert parsed_data['header'].get('nprocs') == 4, "Nprocs mismatch"

        # Verify modules
        print("\n📦 Modules Found:")
        for module_name, module_data in parsed_data['modules'].items():
            print(f"   - {module_name}: {module_data['record_count']} records")

        assert 'POSIX' in parsed_data['modules'], "POSIX module not found"
        assert 'STDIO' in parsed_data['modules'], "STDIO module not found"
        assert 'MPIIO' in parsed_data['modules'], "MPIIO module not found"

        # Verify POSIX records
        posix_records = parsed_data['modules']['POSIX']['records']
        print(f"\n📄 POSIX Records: {len(posix_records)}")

        # Check for shared file
        shared_records = [r for r in posix_records if r['is_shared']]
        print(f"   - Shared records: {len(shared_records)}")

        assert len(shared_records) > 0, "No shared records found"

        # Check counters_blob
        sample_record = posix_records[0]
        print(f"\n🔢 Sample Record Counters:")
        print(f"   Record ID: {sample_record['record_id']}")
        print(f"   File Path: {sample_record['file_path']}")
        print(f"   Counters: {len(sample_record['counters_blob'])} items")

        for key, value in list(sample_record['counters_blob'].items())[:5]:
            print(f"      - {key}: {value}")

        assert 'counters_blob' in sample_record, "counters_blob missing"
        assert len(sample_record['counters_blob']) > 0, "counters_blob is empty"

        print("\n✅ TEST 1 PASSED: DarshanLogParser works correctly")

    finally:
        # Cleanup
        if os.path.exists(temp_log_path):
            os.remove(temp_log_path)


def test_kg_builder():
    """Test the KnowledgeGraphBuilder."""

    print("\n" + "="*70)
    print("TEST 2: KnowledgeGraphBuilder")
    print("="*70)

    # Create temporary log file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_log_path = f.name

    try:
        # Create and parse mock log
        create_mock_darshan_log(temp_log_path)

        parser = DarshanLogParser(temp_log_path)
        parsed_data = parser.parse()

        # Build KG
        kg_builder = KnowledgeGraphBuilder()
        kg = kg_builder.build_from_logs([parsed_data])

        # Verify KG structure
        print("\n📊 KG Statistics:")
        print(f"   Chunks: {len(kg['chunks'])}")
        print(f"   Entities: {len(kg['entities'])}")
        print(f"   Relationships: {len(kg['relationships'])}")

        assert len(kg['chunks']) > 0, "No chunks created"
        assert len(kg['entities']) > 0, "No entities created"
        assert len(kg['relationships']) > 0, "No relationships created"

        # Check entity types
        entity_types = {}
        for entity in kg['entities']:
            etype = entity['entity_type']
            entity_types[etype] = entity_types.get(etype, 0) + 1

        print("\n📋 Entity Types:")
        for etype, count in entity_types.items():
            print(f"   - {etype}: {count}")

        assert 'Job' in entity_types, "Job entity not created"
        assert 'Module' in entity_types, "Module entity not created"
        assert 'FileRecord' in entity_types, "FileRecord entity not created"

        # Check relationships
        rel_types = set()
        for rel in kg['relationships']:
            # Extract relationship type from keywords
            rel_types.add(rel['keywords'].split()[0])

        print("\n🔗 Relationship Types:")
        for rtype in rel_types:
            print(f"   - {rtype}")

        # Sample entities
        print("\n📝 Sample Entities:")
        for i, entity in enumerate(kg['entities'][:3]):
            print(f"\n   Entity {i+1}:")
            print(f"      Name: {entity['entity_name']}")
            print(f"      Type: {entity['entity_type']}")
            print(f"      Description: {entity['description'][:100]}...")

        # Check for FileRecord with counters_blob
        file_records = [e for e in kg['entities'] if e['entity_type'] == 'FileRecord']
        if file_records:
            sample_fr = file_records[0]
            print(f"\n🔍 Sample FileRecord Properties:")
            props = sample_fr.get('properties', {})

            print(f"   File Path: {props.get('file_path')}")
            print(f"   Rank: {props.get('rank')}")
            print(f"   Is Shared: {props.get('is_shared')}")
            print(f"   File Role: {props.get('file_role_hint')}")

            counters = props.get('counters_blob', {})
            print(f"   Counters: {len(counters)} items")

            assert 'counters_blob' in props, "counters_blob missing in FileRecord"
            assert len(counters) > 0, "counters_blob is empty"

        print("\n✅ TEST 2 PASSED: KnowledgeGraphBuilder works correctly")

    finally:
        # Cleanup
        if os.path.exists(temp_log_path):
            os.remove(temp_log_path)


def test_kg_format():
    """Test that the KG format matches LightRAG custom_kg requirements."""

    print("\n" + "="*70)
    print("TEST 3: LightRAG custom_kg Format Validation")
    print("="*70)

    # Create temporary log file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_log_path = f.name

    try:
        # Create and parse mock log
        create_mock_darshan_log(temp_log_path)

        parser = DarshanLogParser(temp_log_path)
        parsed_data = parser.parse()

        # Build KG
        kg_builder = KnowledgeGraphBuilder()
        kg = kg_builder.build_from_logs([parsed_data])

        # Validate top-level structure
        required_keys = ['chunks', 'entities', 'relationships']
        for key in required_keys:
            assert key in kg, f"Missing required key: {key}"
            print(f"✅ Has '{key}' field")

        # Validate chunks format
        if kg['chunks']:
            chunk = kg['chunks'][0]
            required_chunk_fields = ['content', 'source_id']

            for field in required_chunk_fields:
                assert field in chunk, f"Chunk missing required field: {field}"

            print(f"✅ Chunks have required fields: {required_chunk_fields}")

        # Validate entities format
        if kg['entities']:
            entity = kg['entities'][0]
            required_entity_fields = ['entity_name', 'entity_type', 'description', 'source_id']

            for field in required_entity_fields:
                assert field in entity, f"Entity missing required field: {field}"

            print(f"✅ Entities have required fields: {required_entity_fields}")

        # Validate relationships format
        if kg['relationships']:
            rel = kg['relationships'][0]
            required_rel_fields = ['src_id', 'tgt_id', 'description', 'keywords', 'source_id']

            for field in required_rel_fields:
                assert field in rel, f"Relationship missing required field: {field}"

            print(f"✅ Relationships have required fields: {required_rel_fields}")

        # Test JSON serialization
        try:
            json_str = json.dumps(kg, indent=2)
            print(f"✅ KG is JSON serializable ({len(json_str)} bytes)")
        except Exception as e:
            raise AssertionError(f"KG is not JSON serializable: {e}")

        print("\n✅ TEST 3 PASSED: KG format matches LightRAG requirements")

    finally:
        # Cleanup
        if os.path.exists(temp_log_path):
            os.remove(temp_log_path)


def test_file_discovery():
    """Test file discovery functionality."""

    print("\n" + "="*70)
    print("TEST 4: File Discovery")
    print("="*70)

    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create subdirectories
        (temp_path / "subdir1").mkdir()
        (temp_path / "subdir2").mkdir()
        (temp_path / "subdir1" / "nested").mkdir()

        # Create log files
        log_files = [
            temp_path / "log1.txt",
            temp_path / "subdir1" / "log2.txt",
            temp_path / "subdir1" / "nested" / "log3.txt",
            temp_path / "subdir2" / "log4.txt",
            temp_path / "not_a_log.dat"  # Should be ignored
        ]

        for log_file in log_files:
            create_mock_darshan_log(str(log_file))

        # Test directory traversal
        found_logs = find_log_files(str(temp_path))

        print(f"\n📂 Created {len(log_files)} files")
        print(f"🔍 Found {len(found_logs)} .txt files")

        # Should find 4 .txt files (excluding .dat)
        assert len(found_logs) == 4, f"Expected 4 .txt files, found {len(found_logs)}"

        print("\n✅ TEST 4 PASSED: File discovery works correctly")


def main():
    """Run all tests."""

    print("\n" + "="*70)
    print("🧪 DARSHAN KG BUILDER TEST SUITE")
    print("="*70)

    tests = [
        ("Log Parser", test_log_parser),
        ("KG Builder", test_kg_builder),
        ("KG Format Validation", test_kg_format),
        ("File Discovery", test_file_discovery)
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {test_name}")
            print(f"   Error: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ TEST ERROR: {test_name}")
            print(f"   Exception: {e}")
            failed += 1

    # Summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)
    print(f"   Total Tests: {len(tests)}")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {failed} TEST(S) FAILED")
        return 1


if __name__ == '__main__':
    exit(main())
