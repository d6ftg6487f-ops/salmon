import os
import random

from flask import Flask, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-key")

LEVELS = {
    "1": {"maximum": 50, "attempts": 8, "name": "ひよこ"},
    "2": {"maximum": 100, "attempts": 7, "name": "ねこ"},
    "3": {"maximum": 300, "attempts": 9, "name": "ドラゴン"},
}


def start_game(level_key):
    level = LEVELS[level_key]
    session["game"] = {
        "level": level_key,
        "answer": random.randint(1, level["maximum"]),
        "turn": 0,
        "hints": [],
        "result": None,
        "finished": False,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "start" and request.form.get("level") in LEVELS:
            start_game(request.form["level"])
        elif action == "guess" and session.get("game"):
            submit_guess(request.form.get("guess", ""))
        elif action == "reset":
            session.pop("game", None)

    game = session.get("game")
    level = LEVELS[game["level"]] if game else None
    return render_template("index.html", game=game, level=level, levels=LEVELS)


def submit_guess(raw_guess):
    game = session["game"]
    level = LEVELS[game["level"]]
    try:
        guess = int(raw_guess)
    except (TypeError, ValueError):
        game["result"] = "数字を入力してください。"
        session.modified = True
        return

    if not 1 <= guess <= level["maximum"]:
        game["result"] = f"1〜{level['maximum']}の範囲で入力してください。"
        session.modified = True
        return

    game["turn"] += 1
    if guess == game["answer"]:
        game["result"] = f"正解！ {game['turn']}回目で当たりました。"
        game["finished"] = True
    elif game["turn"] >= level["attempts"]:
        game["result"] = f"今回は残念。正解は {game['answer']} でした。"
        game["finished"] = True
    else:
        direction = "もっと大きい" if guess < game["answer"] else "もっと小さい"
        distance = abs(game["answer"] - guess)
        if distance <= max(3, level["maximum"] // 20):
            temperature = "かなり近い！"
        elif distance <= level["maximum"] // 5:
            temperature = "近いです。"
        else:
            temperature = "まだ遠いです。"
        game["hints"].append(f"{guess} → {direction}、{temperature}")
        game["result"] = None
    session.modified = True


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
