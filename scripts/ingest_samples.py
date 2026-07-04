"""Ingest the two task files and run validation queries against the running API.

Usage (with the stack running via `docker compose up`):

    python scripts/ingest_samples.py \
        --pdf "Knowledge_Base_Sample (2).pdf" \
        --code "Source_Code_Sample (2).py"

If paths are omitted the script auto-discovers sample files in the current
directory. It uploads each file, polls until processing completes, then runs a
few semantic queries and prints the top results as proof of execution.
"""
from __future__ import annotations

import argparse
import glob
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:8000"


def _discover(pattern: str) -> str | None:
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


def upload(base_url: str, path: str) -> str:
    with open(path, "rb") as fh:
        response = requests.post(f"{base_url}/documents", files={"file": (path, fh)})
    response.raise_for_status()
    data = response.json()
    print(f"  uploaded {path!r} -> id={data['id']} ({data['source_type']})")
    return data["id"]


def wait_for_completion(base_url: str, document_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = requests.get(f"{base_url}/documents/{document_id}")
        response.raise_for_status()
        data = response.json()
        status = data["status"]
        if status == "completed":
            print(f"  {document_id} completed: {data['chunk_count']} chunks")
            return data
        if status == "failed":
            raise RuntimeError(f"Processing failed: {data.get('error')}")
        print(f"  {document_id} status={status} ... waiting")
        time.sleep(3)
    raise TimeoutError(f"Timed out waiting for {document_id}")


def run_query(base_url: str, query: str, top_k: int = 3, filters: dict | None = None) -> None:
    payload = {"query": query, "top_k": top_k, "filters": filters or {}}
    response = requests.post(f"{base_url}/query", json=payload)
    response.raise_for_status()
    data = response.json()
    print(f"\nQ: {query}  (latency {data['latency_ms']} ms, {data['count']} hits)")
    for i, item in enumerate(data["results"], start=1):
        snippet = " ".join(item["content"].split())[:160]
        symbol = item["metadata"].get("symbol")
        page = item["metadata"].get("page")
        loc = f" symbol={symbol}" if symbol else (f" page={page}" if page else "")
        print(f"  {i}. score={item['score']:.3f} [{item['filename']}]{loc}")
        print(f"     {snippet}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest sample files and run validation queries.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--pdf", default=None, help="Path to the Knowledge Base PDF.")
    parser.add_argument("--code", default=None, help="Path to the source code sample.")
    args = parser.parse_args()

    pdf_path = args.pdf or _discover("Knowledge_Base_Sample*.pdf")
    code_path = args.code or _discover("Source_Code_Sample*.py")

    if not pdf_path or not code_path:
        print("Could not locate sample files. Provide --pdf and --code.", file=sys.stderr)
        return 1

    print("== Ingesting task files ==")
    pdf_id = upload(args.base_url, pdf_path)
    code_id = upload(args.base_url, code_path)

    print("\n== Waiting for processing ==")
    wait_for_completion(args.base_url, pdf_id)
    wait_for_completion(args.base_url, code_id)

    print("\n== Validation queries: code file ==")
    run_query(
        args.base_url,
        "How does the proxy scoring recover over time and how are failures penalized?",
        filters={"source_type": "code"},
    )
    run_query(
        args.base_url,
        "How is a user agent selected and burned when used?",
        filters={"source_type": "code"},
    )

    print("\n== Validation queries: knowledge base PDF ==")
    run_query(
        args.base_url,
        "Summarize the key topic described in the knowledge base document.",
        filters={"source_type": "pdf"},
    )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
