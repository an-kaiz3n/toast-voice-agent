import json
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# Load knowledge base
with open("toast_kb.json") as f:
    KB = json.load(f)


def score_article(article: dict, query: str) -> float:
    query_lower = query.lower()
    query_words = set(re.findall(r'\w+', query_lower))
    score = 0.0

    title_words = set(re.findall(r'\w+', article["title"].lower()))
    score += len(query_words & title_words) * 3

    for kw in article["keywords"]:
        if kw.lower() in query_lower:
            score += 2
        kw_words = set(re.findall(r'\w+', kw.lower()))
        score += len(query_words & kw_words) * 1

    summary_words = set(re.findall(r'\w+', article["summary"].lower()))
    score += len(query_words & summary_words) * 0.5

    cat_words = set(re.findall(r'\w+', article["category"].lower()))
    score += len(query_words & cat_words) * 1

    return score


def search_kb(query: str, top_k: int = 2) -> list:
    scored = [(score_article(a, query), a) for a in KB]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for score, a in scored[:top_k] if score > 0]


def format_for_voice(articles: list) -> str:
    if not articles:
        return (
            "I don't have a specific article for that in my knowledge base. "
            "I'll connect you with a specialist who can help."
        )

    parts = []
    for i, article in enumerate(articles):
        header = "Here's what I found" if i == 0 else "Also"
        steps_text = " ".join(
            f"Step {j+1}: {step}" for j, step in enumerate(article["steps"])
        )
        escalate = ""
        if article.get("escalate_if"):
            escalate = f" If that doesn't work: {article['escalate_if']}"
        warning = ""
        if article.get("critical_warning"):
            warning = f" Important warning: {article['critical_warning']}"

        parts.append(
            f"{header}: for {article['title']}. {article['summary']} "
            f"{steps_text}{escalate}{warning}"
        )

    return " ".join(parts)


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json(force=True, silent=True) or {}
    print("VAPI PAYLOAD:", json.dumps(data, indent=2))

    try:
        tool_calls = data.get("message", {}).get("toolCallList", [])
        if tool_calls:
            args = tool_calls[0]["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            # Clean any accidental newlines from key names
            args = {k.strip(): v for k, v in args.items()}
            query = args.get("query", "")
            call_id = tool_calls[0].get("id", "call_unknown")
        else:
            query = data.get("query", "")
            call_id = "test_call"
    except Exception as e:
        print("PARSE ERROR:", str(e))
        return jsonify({"error": str(e)}), 400

    if not query:
        print("NO QUERY FOUND IN PAYLOAD")
        return jsonify({"error": "No query provided"}), 400

    print(f"SEARCHING FOR: {query}")
    results = search_kb(query, top_k=2)
    voice_response = format_for_voice(results)
    print(f"RETURNING: {voice_response[:100]}...")

    return jsonify({
        "results": [
            {
                "toolCallId": call_id,
                "result": voice_response
            }
        ]
    })


@app.route("/search_raw", methods=["POST"])
def search_raw():
    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query", "")
    results = search_kb(query, top_k=3)
    return jsonify({"query": query, "results": results, "count": len(results)})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "articles_loaded": len(KB)})


if __name__ == "__main__":
    print(f"Toast KB loaded: {len(KB)} articles")
    print("Endpoints:")
    print("  POST /search      — Vapi tool call format")
    print("  POST /search_raw  — Direct test (returns full JSON)")
    print("  GET  /health      — Health check")
    app.run(host="0.0.0.0", port=5000, debug=True)