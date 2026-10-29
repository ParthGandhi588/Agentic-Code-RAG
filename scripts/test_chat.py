"""Script to test end-to-end chat queries via SSE streaming and analyze answers."""

import json
import sys
import time
import urllib.request

# Ensure immediate unbuffered console output
sys.stdout.reconfigure(line_buffering=True)


def run_chat_query(repo_id: str, query: str):
    print("\n" + "=" * 80)
    print(f"QUERY: {query}")
    print("=" * 80)

    url = "http://127.0.0.1:8000/api/chat"
    payload = json.dumps({"repo_id": repo_id, "message": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    start_time = time.time()
    tools_called = []
    tokens = []

    try:
        with urllib.request.urlopen(req, timeout=360) as response:
            current_event = None
            for line in response:
                decoded = line.decode("utf-8").strip()
                if not decoded:
                    continue
                if decoded.startswith("event:"):
                    current_event = decoded[6:].strip()
                elif decoded.startswith("data:"):
                    data_str = decoded[5:].strip()
                    try:
                        data_json = json.loads(data_str)
                    except Exception:
                        data_json = data_str

                    if current_event == "tool_start":
                        tools_called.append(data_json)
                        print(f"  [TOOL_START] {data_json.get('tool')}({data_json.get('input')})")
                    elif current_event == "tool_end":
                        print(f"  [TOOL_END] {data_json.get('tool')} -> {str(data_json.get('output_preview'))[:100]}...")
                    elif current_event == "token":
                        t = data_json.get("content", "")
                        tokens.append(t)
                        print(t, end="", flush=True)
                    elif current_event == "final_answer":
                        print("\n[EVENT: final_answer received]")
                    elif current_event == "done":
                        print("\n[EVENT: done received]")
                    elif current_event == "error":
                        print(f"\n[ERROR EVENT]: {data_json}")

    except Exception as e:
        print(f"Request exception: {e}")

    elapsed = time.time() - start_time
    full_text = "".join(tokens)
    print(f"\nElapsed: {elapsed:.2f}s | Tools called: {len(tools_called)}")
    print("-" * 80)
    return {
        "query": query,
        "elapsed": elapsed,
        "tools_called": tools_called,
        "answer": full_text,
    }


if __name__ == "__main__":
    target_repo = "Agentic-Code-RAG"
    if len(sys.argv) > 1:
        custom_query = " ".join(sys.argv[1:])
        run_chat_query(target_repo, custom_query)
    else:
        run_chat_query(
            target_repo,
            "Where is the JobManager class defined and what are its main methods?",
        )
        run_chat_query(
            target_repo,
            "Explain how the AST symbol extractor works for Python files and what model it outputs.",
        )
