#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import boto3

from discoverex.domain.scene import Scene


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate scene bundle registration and retrieval from MinIO."
    )
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--bucket", default="discoverex-artifacts")
    parser.add_argument("--endpoint-url", default="http://127.0.0.1:9000")
    parser.add_argument("--access-key", default="minioadmin")
    parser.add_argument("--secret-key", default="minioadmin")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--artifacts-root", default="artifacts")
    args = parser.parse_args()

    prefix = f"scenes/{args.scene_id}/{args.version_id}/"
    required = [
        prefix + "scene.json",
        prefix + "verification.json",
        prefix + "composite.png",
    ]

    s3 = boto3.client(
        "s3",
        endpoint_url=args.endpoint_url,
        aws_access_key_id=args.access_key,
        aws_secret_access_key=args.secret_key,
        region_name=args.region,
    )

    list_resp = s3.list_objects_v2(Bucket=args.bucket, Prefix=prefix)
    keys = sorted([obj["Key"] for obj in list_resp.get("Contents", [])])
    print(json.dumps({"listed_keys": keys}, ensure_ascii=False))

    missing = [key for key in required if key not in keys]
    if missing:
        print(json.dumps({"missing_keys": missing}, ensure_ascii=False))
        return 1

    local_root = Path(args.artifacts_root) / "scenes" / \
        args.scene_id / args.version_id
    if not local_root.exists():
        print(json.dumps(
            {"error": f"local scene dir not found: {local_root}"}))
        return 1

    mismatch: list[str] = []
    for name in ("scene.json", "verification.json", "composite.png"):
        remote_key = prefix + name
        head = s3.head_object(Bucket=args.bucket, Key=remote_key)
        if int(head["ContentLength"]) <= 0:
            print(json.dumps({"error": f"empty object: {remote_key}"}))
            return 1

        remote_bytes = s3.get_object(Bucket=args.bucket, Key=remote_key)[
            "Body"].read()
        local_bytes = (local_root / name).read_bytes()
        if _sha256(remote_bytes) != _sha256(local_bytes):
            mismatch.append(name)

    if mismatch:
        print(json.dumps({"hash_mismatch": mismatch}, ensure_ascii=False))
        return 1

    scene_json = s3.get_object(
        Bucket=args.bucket, Key=prefix + "scene.json")["Body"].read()
    scene = Scene.model_validate_json(scene_json.decode("utf-8"))
    print(
        json.dumps(
            {
                "scene_loaded": {
                    "scene_id": scene.meta.scene_id,
                    "version_id": scene.meta.version_id,
                    "status": scene.meta.status.value,
                },
                "result": "ok",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
