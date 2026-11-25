"""Command line: `uv run research-assistant "question"` (or `uv run python -m research_assistant ...`)."""
import argparse
import json
import logging

from pydantic import ValidationError

from research_assistant.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="research-assistant")
    parser.add_argument("question", nargs="?", help="the question to answer")
    parser.add_argument("--show-config", action="store_true", help="print the settings (keys masked) and exit")
    args = parser.parse_args()

    try:
        settings = get_settings()
    except ValidationError as exc:  # stop at start-up, naming each bad or missing variable
        names = ", ".join(str(e["loc"][0]).upper() for e in exc.errors())
        raise SystemExit(f"Invalid settings: {names}. Set them in .env (see .env.example) or as environment variables.")
    logging.basicConfig(level=settings.log_level, format="%(levelname)s | %(name)s | %(message)s")
    for noisy in ("httpx", "httpx2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from research_assistant.core.langfuse import init_langfuse
    init_langfuse(settings)  # the agent loads its pinned prompt from Langfuse
    if args.show_config:
        print(json.dumps(settings.model_dump(mode="json"), indent=2))  # SecretStr prints as "**********"
    elif args.question:
        from research_assistant.agent.agent import ask
        result = ask(args.question, settings)
        print(result["answer"])
        print(f"\n[{settings.app_env}] model={result['served_model']} {result['metrics']}")
    else:
        parser.print_help()


if __name__ == "__main__":  # runs on `python -m research_assistant`, not when the module is imported
    main()
