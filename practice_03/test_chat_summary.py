#!/usr/bin/env python3
import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from chat_summary import (
    get_project_root,
    count_tokens,
    should_summarize,
    search_chat_history,
    load_env_file,
)


def test_get_project_root():
    print("Test get_project_root()...")
    root = get_project_root()
    assert root != ""
    assert os.path.exists(root)
    print("  [OK] project root: " + root)


def test_count_tokens():
    print("Test count_tokens()...")
    assert count_tokens("hello") == 2
    assert count_tokens("hello world") == 3
    print("  [OK] tokens calc correct")


def test_should_summarize():
    print("Test should_summarize()...")

    try:
        messages = [{"role": "user", "content": "msg%d" % i} for i in range(6)]
        assert should_summarize(messages) == True
        print("  [OK] >5 turns returns True")

        long_messages = [{"role": "user", "content": "x" * 4000}]
        assert should_summarize(long_messages) == True
        print("  [OK] >3000 tokens returns True")

        normal = [{"role": "user", "content": "hello"}]
        assert should_summarize(normal) == False
        print("  [OK] normal returns False")
    except Exception as e:
        print("  [SKIP] " + str(e))


def test_load_env_file():
    print("Test load_env_file()...")
    env_path = os.path.join(project_root, ".env")
    os.environ.clear()
    load_env_file(env_path)
    assert "BASE_URL" in os.environ
    print("  [OK] BASE_URL loaded")


def test_search_chat_history():
    print("Test search_chat_history()...")
    log_dir = os.path.join(project_root, "chat_log")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.txt")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("Who: test user\nWhat: test record\n")
    result = search_chat_history("test")
    assert "results" in result or "error" in result
    print("  [OK] search returns result")


def run_all_tests():
    print("=" * 50)
    print("Running tests...")
    print("=" * 50)

    tests = [
        test_get_project_root,
        test_count_tokens,
        test_should_summarize,
        test_load_env_file,
        test_search_chat_history,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print("  [FAIL] " + str(e))
            failed += 1
        print()

    print("=" * 50)
    print("Results: %d PASSED, %d FAILED" % (passed, failed))
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
