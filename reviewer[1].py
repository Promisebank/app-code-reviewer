"""Core review logic: prompt building, OpenAI call, response parsing, annotation."""
import json
import time

CRITERIA = {
    "security": "Injection flaws, hardcoded secrets, XSS, unsafe deserialization, unvalidated input, insecure defaults.",
    "efficiency": "Needless nested loops, repeated work, wrong data structures, avoidable memory use, blocking calls.",
    "readability": "Unclear names, missing docstrings where needed, deep nesting, overly clever code.",
    "best_practices": "Idiomatic language use, error handling, resource cleanup, testability, language-specific pitfalls.",
}
BUG_DESCRIPTION = "Logic errors, crashes, wrong results, unhandled edge cases (empty input, None/null, off-by-one, async mistakes)."
ALL_CATEGORIES = ["bugs"] + list(CRITERIA)
SEVERITIES = ["critical", "high", "medium", "low"]
DEFAULT_MODEL = "gpt-4o-mini"
MAX_CHARS = 20000


def number_lines(code: str) -> str:
    return "\n".join(f"{i}: {line}" for i, line in enumerate(code.splitlines(), start=1))


def build_system_prompt(language: str, criteria: list) -> str:
    crit_lines = [f"- bugs: {BUG_DESCRIPTION} (always checked)"]
    crit_lines += [f"- {c}: {CRITERIA[c]}" for c in criteria if c in CRITERIA]
    return f"""You are a senior {language} engineer doing a strict, honest code review.

Review the code against these criteria:
{chr(10).join(crit_lines)}

Rules:
- Report only REAL issues you can point to in the code. Never invent problems to look thorough.
- If the code is fine, return an empty "issues" list and say so in the summary.
- Every line in the code is prefixed with its line number ("12: ..."). Use those numbers for line_start and line_end.
- Severity: critical = exploitable or data loss; high = likely bug or serious flaw; medium = real but limited impact; low = minor or stylistic.
- Be specific: explain WHY it is a problem, then give a concrete fix.
- Respond with JSON only, no markdown fences, in exactly this shape:
{{
  "summary": "2-3 sentence overall assessment",
  "overall_score": <integer 1-10, 10 = excellent>,
  "issues": [
    {{
      "line_start": <int>,
      "line_end": <int>,
      "category": "bugs|{'|'.join(criteria)}",
      "severity": "critical|high|medium|low",
      "title": "short title",
      "explanation": "why this is a problem",
      "suggestion": "how to fix it",
      "fixed_code": "corrected code for just the affected lines, or empty string"
    }}
  ],
  "improved_code": "the full code with all fixes applied, WITHOUT line-number prefixes"
}}"""


def parse_review(raw: str, total_lines: int) -> dict:
    """Parse and normalise the model's JSON so the UI never crashes on odd output."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    data = json.loads(text)

    issues = []
    for item in data.get("issues", []) or []:
        try:
            start = int(item.get("line_start", 1))
            end = int(item.get("line_end", start))
        except (TypeError, ValueError):
            start, end = 1, 1
        start = max(1, min(start, max(total_lines, 1)))
        end = max(start, min(end, max(total_lines, 1)))
        category = item.get("category", "best_practices")
        if category not in ALL_CATEGORIES:
            category = "best_practices"
        severity = item.get("severity", "medium")
        if severity not in SEVERITIES:
            severity = "medium"
        issues.append({
            "line_start": start,
            "line_end": end,
            "category": category,
            "severity": severity,
            "title": str(item.get("title", "Issue")),
            "explanation": str(item.get("explanation", "")),
            "suggestion": str(item.get("suggestion", "")),
            "fixed_code": str(item.get("fixed_code", "") or ""),
        })
    issues.sort(key=lambda i: (SEVERITIES.index(i["severity"]), i["line_start"]))

    try:
        score = max(1, min(10, int(data.get("overall_score", 5))))
    except (TypeError, ValueError):
        score = 5
    return {
        "summary": str(data.get("summary", "")),
        "overall_score": score,
        "issues": issues,
        "improved_code": str(data.get("improved_code", "") or ""),
    }


def review_code(code: str, language: str, api_key: str, model: str = DEFAULT_MODEL,
                criteria: list = None) -> dict:
    """Send code to the LLM and return a normalised review dict with _meta."""
    from openai import OpenAI  # imported lazily so parsing/tests work without the package

    criteria = criteria if criteria is not None else list(CRITERIA)
    code = code.strip("\n")
    if not code.strip():
        raise ValueError("No code provided.")
    if len(code) > MAX_CHARS:
        raise ValueError(f"Code is too long ({len(code)} chars). Limit is {MAX_CHARS}.")

    client = OpenAI(api_key=api_key)
    start = time.time()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_system_prompt(language, criteria)},
            {"role": "user", "content": f"Review this {language} code:\n\n{number_lines(code)}"},
        ],
    )
    elapsed = time.time() - start
    review = parse_review(resp.choices[0].message.content, len(code.splitlines()))
    review["_meta"] = {
        "seconds": round(elapsed, 2),
        "model": model,
        "tokens": getattr(resp.usage, "total_tokens", None),
    }
    return review


def annotate_code(code: str, issues: list) -> str:
    """Return line-numbered code with markers pointing at flagged lines."""
    lines = code.strip("\n").splitlines()
    marks = {}
    for n, issue in enumerate(issues, start=1):
        for ln in range(issue["line_start"], issue["line_end"] + 1):
            marks.setdefault(ln, []).append(n)
    out = []
    for i, line in enumerate(lines, start=1):
        tag = ""
        if i in marks:
            tag = "   <-- " + ", ".join(f"[{n}]" for n in marks[i])
        flag = ">" if i in marks else " "
        out.append(f"{i:>3} {flag} {line}{tag}")
    return "\n".join(out)


def review_to_markdown(review: dict, language: str) -> str:
    parts = [f"# Code review ({language})", "", f"**Score:** {review['overall_score']}/10", "", review["summary"], ""]
    for n, i in enumerate(review["issues"], start=1):
        parts += [
            f"## [{n}] {i['title']} ({i['severity']}, {i['category']})",
            f"Lines {i['line_start']}-{i['line_end']}", "",
            i["explanation"], "", f"**Fix:** {i['suggestion']}", "",
        ]
    return "\n".join(parts)
