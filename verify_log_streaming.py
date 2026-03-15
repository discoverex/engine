from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

# Add src to sys.path to import local modules
sys.path.append(str(Path.cwd() / "src"))
sys.path.append(str(Path.cwd()))

import pytest
from infra.prefect.dispatch import dispatch_engine_job

def test_real_log_streaming():
    print("\n--- Starting Real-time Log Streaming Verification ---")
    
    # 1. Setup a dummy environment with a fake python that emits logs
    cwd = Path.cwd() / ".tmp_verify_logs"
    cwd.mkdir(parents=True, exist_ok=True)
    
    bin_dir = cwd / ".venv" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    
    fake_python = bin_dir / "python"
    # This fake python will print lines with delays to test streaming
    script_content = """
import sys
import time
print("LOG_LINE_1: Starting engine job...")
sys.stdout.flush()
time.sleep(0.5)
print("LOG_LINE_2: Processing stage A...")
sys.stdout.flush()
time.sleep(0.5)
print("LOG_LINE_3: Progress 50%")
sys.stdout.flush()
print("ERR_LINE_1: Potential issue detected", file=sys.stderr)
sys.stderr.flush()
time.sleep(0.5)
# Emit final JSON payload required by dispatch_engine_job
print('{"status": "completed", "scene_id": "test-123"}')
sys.stdout.flush()
"""
    fake_python.write_text(f"#!{sys.executable}\n{script_content}")
    fake_python.chmod(0o755)

    # 2. Mock Prefect Logger to capture streamed logs
    mock_logger = MagicMock()
    # We need to patch get_run_logger in the module where it's used
    import infra.prefect.dispatch
    infra.prefect.dispatch.get_run_logger = lambda: mock_logger

    # 3. Execute dispatch_engine_job
    payload = {"command": "generate", "args": {}}
    
    print("Executing dispatch_engine_job...")
    result = dispatch_engine_job(payload, cwd=cwd, env={})
    
    print("\nVerification Results:")
    print(f"Status: {result.payload['status']}")
    
    # 4. Assert logs were captured by the logger
    log_calls = [call.args[0] for call in mock_logger.info.call_args_list]
    err_calls = [call.args[0] for call in mock_logger.error.call_args_list]
    
    print(f"Captured INFO logs: {len(log_calls)}")
    for log in log_calls:
        print(f"  [INFO] {log}")
        
    print(f"Captured ERROR logs: {len(err_calls)}")
    for log in err_calls:
        print(f"  [ERROR] {log}")

    assert "LOG_LINE_1: Starting engine job..." in log_calls
    assert "LOG_LINE_2: Processing stage A..." in log_calls
    assert "[stderr] ERR_LINE_1: Potential issue detected" in err_calls
    assert result.payload["scene_id"] == "test-123"
    
    print("\n--- Verification Successful: Log streaming works! ---")

if __name__ == "__main__":
    try:
        test_real_log_streaming()
    except Exception as e:
        print(f"\nVerification Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(Path.cwd() / ".tmp_verify_logs", ignore_errors=True)
