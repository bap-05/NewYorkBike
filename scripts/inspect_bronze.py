"""Verify archived response bytes offline. Never calls APIs or writes Silver/Gold."""
import argparse
import hashlib
import json
from pathlib import Path


def verify_manifest(path):
    path = Path(path).resolve()
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("format_version") != "bronze-v1":
        raise ValueError("Unsupported Bronze manifest version")
    body_count = 0
    json_count = 0
    for entry in document["responses"]:
        if "body_file" not in entry:
            if entry.get("body_omitted") != "proxy_authentication_error":
                raise ValueError("Response body reference missing")
            continue
        body_path = (path.parent / entry["body_file"]).resolve()
        if not body_path.is_relative_to(path.parent):
            raise ValueError("Body path escapes the manifest directory")
        body = body_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["sha256"] or len(body) != entry["size_bytes"]:
            raise ValueError("Bronze body integrity verification failed")
        body_count += 1
        try:
            json.loads(body)
            json_count += 1
        except (ValueError, UnicodeError):
            pass  # Non-JSON source errors are still valid raw evidence.
    return {"collection_run_id": document["collection_run_id"],
            "collection_attempt": document["collection_attempt"],
            "capture_status": document["capture_status"], "response_count": len(document["responses"]),
            "verified_bodies": body_count, "json_bodies": json_count,
            "network_failures": len(document["network_failures"]),
            "weather_reuse": len(document["weather_reuse"])}


def main():
    parser = argparse.ArgumentParser(description="Verify Bronze manifest and SHA-256 without network or database writes")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_manifest(args.manifest), indent=2))
    except (OSError, ValueError, KeyError, TypeError):
        print("Bronze verification failed; check manifest, file paths, body sizes and SHA-256.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
