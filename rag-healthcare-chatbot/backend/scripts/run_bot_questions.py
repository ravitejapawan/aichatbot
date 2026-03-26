#!/usr/bin/env python3
"""Run one or more questions against the local chatbot API.

Examples:
  python backend/scripts/run_bot_questions.py --question "What is therapy gap?"
  python backend/scripts/run_bot_questions.py --file questions.txt --app nx2meapp
  type questions.txt | python backend/scripts/run_bot_questions.py --stdin
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "bot_answers.txt"

DEFAULT_QUESTIONS = [
    "What warnings should I follow while using the Nx2me app?",
    "Can I rely only on the Nx2me app for alarms?",
    "What happens if the app shows different data than the cycler?",
    "What are the risks of using incorrect treatment data?",
    "When should I contact a doctor during treatment?",
    "What safety precautions should I follow while using the iPad?",
    "What happens if alerts exceed the threshold?",
    "How do I start a new treatment session?",
    "What is a flowsheet and why is it important?",
    "What happens if my iPad battery dies during treatment?",
    "How do I complete pre-treatment and post-treatment steps?",
    "How can I monitor my treatment during dialysis?",
    "What data is recorded during a treatment session?",
    "How do I submit a flowsheet?",
    "What is the purpose of Nx2me Connected Health?",
    "What kind of data does the system collect?",
    "Can the Nx2me app control the cycler?",
    "What is ultrafiltration (UFR)?",
    "How is blood pressure recorded in the app?",
    "How does the system help healthcare providers?",
    "What is the role of prescriptions in treatment?",
    "Why does the app show 'Looking for Cycler'?",
    "What does 'Connected, no Cycler data' mean?",
    "What should I do if sync fails?",
    "Why can't I create an account?",
    "What if I forget my username or password?",
    "Why is my Bluetooth device not working?",
    "What happens if the app is not compatible with my device?",
    "How do I connect the iPad to Wi-Fi?",
    "How do I pair a Bluetooth device?",
    "What devices are supported by the Nx2me app?",
    "Can I use the app without internet?",
    "Why should I not update iOS without approval?",
    "Explain the complete workflow of Nx2me system",
    "How does data flow from patient to doctor?",
    "What are the limitations of the Nx2me system?",
    "How does the system ensure patient safety?",
    "What happens if incorrect data is submitted?",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send questions to the chatbot streaming API and print answers.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="FastAPI base URL. Default: http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--question",
        action="append",
        default=[],
        help="A single question to ask. Repeat to ask multiple questions.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Path to a UTF-8 text file with one question per line.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read questions from standard input, one per line.",
    )
    parser.add_argument(
        "--app",
        choices=["kinexushhd", "nx2meapp"],
        help="Optional app scope to send with the request.",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        help="Optional file path to save question/answer results as JSONL.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="HTTP timeout in seconds. Default: 180",
    )
    parser.add_argument(
        "--use-default-set",
        action="store_true",
        help="Run the built-in chatbot evaluation question set.",
    )
    return parser.parse_args()


def load_questions(args: argparse.Namespace) -> list[str]:
    questions: list[str] = []

    questions.extend(clean_lines(args.question))

    if args.file:
        questions.extend(clean_lines(args.file.read_text(encoding="utf-8").splitlines()))

    if args.stdin:
        questions.extend(clean_lines(sys.stdin.read().splitlines()))

    if not questions:
        if args.use_default_set or not any([args.question, args.file, args.stdin]):
            questions.extend(DEFAULT_QUESTIONS)

    if not questions:
        raise SystemExit("No questions provided. Use --question, --file, --stdin, or --use-default-set.")

    return questions


def clean_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in lines:
        line = str(raw or "").strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        cleaned.append(line)
    return cleaned


def ask_question(
    api_base_url: str,
    question: str,
    app: str | None,
    timeout: int,
) -> dict:
    payload: dict[str, object] = {
        "question": question,
        "history": [],
    }
    if app:
        payload["app"] = app

    request = urllib.request.Request(
        url=f"{api_base_url.rstrip('/')}/chat/stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    answer_parts: list[str] = []
    meta: dict[str, object] = {}

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue

                event = json.loads(line)
                event_type = event.get("type")

                if event_type == "meta":
                    meta = event
                elif event_type == "token":
                    answer_parts.append(str(event.get("text") or ""))
                elif event_type == "error":
                    raise RuntimeError(str(event.get("detail") or "Unknown API error"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection failed: {exc.reason}") from exc

    answer = "".join(answer_parts).strip()
    sources = meta.get("sources") if isinstance(meta.get("sources"), list) else []

    return {
        "question": question,
        "answer": answer,
        "collection": meta.get("collection"),
        "app": meta.get("app"),
        "routing": meta.get("routing"),
        "sources": sources,
    }


def format_result(result: dict, index: int, total: int) -> str:
    answer = result.get("answer") or "(no answer returned)"
    sources = result.get("sources") or []
    source_label = "Knowledge base"
    if sources:
        first = sources[0] or {}
        section = str(first.get("section") or "").strip()
        page = first.get("page")
        if section and page:
            source_label = f"{section} (page {page})"
        elif section:
            source_label = section
        elif page:
            source_label = f"Page {page}"

    return textwrap.dedent(
        f"""
        [{index}/{total}] Question
        {result['question']}

        Answer
        {answer}

        Source
        {source_label}
        """
    ).strip()


def main() -> int:
    args = parse_args()
    questions = load_questions(args)
    output_path = args.output_jsonl or DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_handle = output_path.open("w", encoding="utf-8")

    try:
        for index, question in enumerate(questions, start=1):
            result = ask_question(
                api_base_url=args.api_base_url,
                question=question,
                app=args.app,
                timeout=args.timeout,
            )
            print(format_result(result, index=index, total=len(questions)))
            print()

            output_handle.write(format_result(result, index=index, total=len(questions)))
            output_handle.write("\n\n" + ("-" * 80) + "\n\n")
    finally:
        output_handle.close()

    print(f"Saved answers to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
