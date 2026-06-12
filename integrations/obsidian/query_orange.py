#!/usr/bin/env python3
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

def query_orange(note_title, note_path, content, query_text, server_url):
    # If content is not explicitly provided, try to read it from the note_path
    if not content and note_path:
        try:
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading note file '{note_path}': {e}", file=sys.stderr)
            sys.exit(1)
            
    # If title is not provided, derive it from the note path
    if not note_title and note_path:
        note_title = os.path.splitext(os.path.basename(note_path))[0]
        
    # Prepare payload
    payload = {
        "note_title": note_title or "",
        "content": content or "",
        "query": query_text or ""
    }
    
    # Ensure server_url ends without a trailing slash for cleanliness
    if server_url.endswith("/"):
        server_url = server_url[:-1]
        
    # Send request
    req = urllib.request.Request(
        f"{server_url}/query",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if "answer" in res_data:
                return res_data["answer"]
            else:
                print(f"Server returned error: {res_data.get('message', 'Unknown error')}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode('utf-8'))
            err_msg = err_data.get("message", err_data.get("error", str(e)))
        except Exception:
            err_msg = str(e)
        print(f"HTTP Error {e.code}: {err_msg}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Failed to connect to Orange server: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error executing query: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Query Orange Core agent with Obsidian note context")
    parser.add_argument("--title", "-t", help="Title of the active Obsidian note")
    parser.add_argument("--path", "-p", "--file", "-f", dest="path", help="Path to the active Obsidian note file on disk")
    parser.add_argument("--content", "-c", help="Direct text content of the note (optional)")
    parser.add_argument("--query", "-q", required=False, help="Query / question for the Pydantic AI agent")
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="Orange server URL (default: http://127.0.0.1:8080)")
    
    args = parser.parse_args()
    
    query_text = args.query if args.query else "PING_ORANGE"
    
    response = query_orange(
        note_title=args.title,
        note_path=args.path,
        content=args.content,
        query_text=query_text,
        server_url=args.url
    )
    
    print(response)

if __name__ == "__main__":
    main()
