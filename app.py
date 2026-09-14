import random


def choose_level():
	levels = {
		"1": (50, 8, "ひよこ"),
		"2": (100, 7, "ねこ"),
		"3": (300, 9, "ドラゴン"),
	}

	print("\n難易度を選んでください")
	print("1. ひよこ   1〜50 / 8回")
	print("2. ねこ     1〜100 / 7回")
	print("3. ドラゴン 1〜300 / 9回")

	while True:
		choice = input("> ").strip()
		if choice in levels:
			return levels[choice]
		print("1〜3のどれかを入力してください。")


def play_round():
	maximum, attempts, level_name = choose_level()
	answer = random.randint(1, maximum)
	hints = []

	print(f"\n{level_name}級スタート！ 1〜{maximum}の数字を当ててください。")
	print("ヒントは少しずつ近くなります。")

	for turn in range(1, attempts + 1):
		while True:
			raw_guess = input(f"\n{turn}/{attempts}回目 > ").strip()
			try:
				guess = int(raw_guess)
			except ValueError:
				print("数字を入力してください。")
				continue
			if 1 <= guess <= maximum:
				break
			print(f"1〜{maximum}の範囲で入力してください。")

		if guess == answer:
			score = (attempts - turn + 1) * 100
			print(f"\n正解！ {turn}回目で当たりました。スコア: {score}")
			return

		direction = "もっと大きい" if guess < answer else "もっと小さい"
		distance = abs(answer - guess)
		if distance <= max(3, maximum // 20):
			temperature = "かなり近い！"
		elif distance <= maximum // 5:
			temperature = "近いです。"
		else:
			temperature = "まだ遠いです。"
		hints.append(f"{guess} → {direction}、{temperature}")
		print(hints[-1])

	print(f"\n今回は残念。正解は {answer} でした。")


def main():
	print("=== ひらめき数当てゲーム ===")
	print("数字を読んで、直感で当てよう。")

	while True:
		play_round()
		again = input("\nもう一度遊びますか？ [y/N] > ").strip().lower()
		if again not in {"y", "yes"}:
			print("遊んでくれてありがとう！")
			break


if __name__ == "__main__":
	main()
