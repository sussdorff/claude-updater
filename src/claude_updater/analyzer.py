import subprocess
import sys


def resolve_api_key(config: dict) -> str | None:
    if config.get("api_key"):
        return config["api_key"]

    if config.get("api_key_env"):
        import os
        return os.environ.get(config["api_key_env"])

    if config.get("api_key_cmd"):
        result = subprocess.run(
            config["api_key_cmd"],
            shell=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None

    return None


def analyze_changelogs(changelogs: dict[str, str], config: dict) -> str | None:
    try:
        import openai
    except ImportError:
        print("Warning: openai package not installed, skipping AI analysis", file=sys.stderr)
        return None

    api_key = resolve_api_key(config)
    if not api_key:
        print("Warning: no API key configured for AI analysis", file=sys.stderr)
        return None

    user_prompt_parts = []
    for tool_name, changelog_text in changelogs.items():
        user_prompt_parts.append(f"=== {tool_name} ===\n{changelog_text}")
    user_prompt = "\n\n".join(user_prompt_parts)
    user_prompt += (
        "\n\nFor each tool above: list the top 3 changes, any breaking changes, "
        "and new features worth using. Keep the total response under 20 lines."
    )

    try:
        client = openai.OpenAI(
            base_url=config.get("api_base"),
            api_key=api_key,
            timeout=30,
        )
        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {
                    "role": "system",
                    "content": "You analyze tool changelogs for a Claude Code power user.",
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Warning: AI analysis failed: {e}", file=sys.stderr)
        return None
