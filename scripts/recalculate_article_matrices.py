import ast
import csv
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "comparison_coded_sample.csv"
EVENTS_OUTPUT = ROOT / "data" / "article_crosspromo_events_2024H1_2026H1.csv"
MATRIX_OUTPUT = ROOT / "data" / "article_matrix_2024H1_2026H1.csv"

CTA = re.compile(
    r"подпис|переход|подробнее|чита(?:й|йте)|смотр(?:и|ите)|слуш(?:ай|айте)|"
    r"скач|голос|открыва(?:й|йте)|заход|ищите|доступн|на нашем сайте|в приложении",
    re.I,
)


def host_path(url):
    parsed = urlparse(url if "://" in url else "https://" + url)
    return parsed.netloc.lower().removeprefix("www."), parsed.path.strip("/")


def classify(station, url, text):
    host, path = host_path(url)
    handle = path.split("/")[0]
    if host in {"bfm.ru", "radio1.ru", "radio1.news", "dorognoe.ru"}:
        return 1, host

    approved_social = {
        "Business FM": {("max.ru", "bfm")},
        "Маяк": {
            ("max.ru", "mayakfm"), ("vk.com", "mayakfm"),
            ("vk.com", "audios-35744422"),
        },
        "Радио 1": {
            ("max.ru", "Radio1"), ("vk.com", "radio1_news"),
            ("ok.ru", "group"),
        },
        "Дорожное радио": {("ok.ru", "dorognoe")},
    }
    if (host, handle) in approved_social.get(station, set()):
        return 2, f"{host}/{handle}"

    if host in {"t.me", "telegram.me"}:
        self_handles = {
            "Business FM": {"BFMnews"},
            "Маяк": {"mayak_fm"},
            "Радио 1": {"radio1_ru"},
            "Дорожное радио": {"dorognoe_radio"},
        }
        related = {
            "Business FM": set(),
            "Маяк": {"FckngTeens", "FreakingTeens", "WordsAndMusic", "tvrussia1"},
            "Радио 1": {"R1News1_bot", "radio1news", "Radio_R1", "studiorrr1"},
            "Дорожное радио": set(),
        }
        if handle in self_handles.get(station, set()):
            return None
        if handle in related.get(station, set()):
            return 2, f"t.me/{handle}"
        return None

    if host in {
        "music.yandex.ru", "music.yandex.com", "podcasts.apple.com", "apple.co",
        "podcast.ru", "podster.fm", "youtube.com", "youtu.be", "rutube.ru",
    }:
        return 3, host

    if host == "smotrim.ru":
        return 4, host
    if host in {
        "apps.apple.com", "play.google.com", "rustore.ru", "appgallery.huawei.com",
        "6273241.redirect.appmetrica.yandex.com",
    }:
        return 4, host
    if host == "clck.ru" and "radiohub" in text.lower():
        return 4, "RadioHub"
    return None


def main():
    records = []
    with INPUT.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                urls = ast.literal_eval(row["hrefs"])
            except (ValueError, SyntaxError):
                urls = []
            destinations = {}
            for url in urls:
                result = classify(row["station"], url, row["text"])
                if result:
                    destinations[result] = True
            if not destinations:
                continue
            if len(destinations) >= 2:
                intensity = 4
            elif CTA.search(row["text"]):
                intensity = 3
            elif len(row["text"].strip()) > 40:
                intensity = 2
            else:
                intensity = 1
            for x in sorted({x for x, _ in destinations}):
                records.append({
                    "station": row["station"],
                    "period": row["profile"],
                    "message_id": row["message_id"],
                    "x": x,
                    "y": int(row["y"]) + 1,
                    "a": intensity,
                    "resources": "; ".join(
                        sorted(resource for xx, resource in destinations if xx == x)
                    ),
                })

    with EVENTS_OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    sums = defaultdict(int)
    for row in records:
        sums[(row["station"], row["period"], row["x"], row["y"])] += row["a"]

    stations = ["Business FM", "Маяк", "Радио 1", "Дорожное радио"]
    matrix_rows = []
    for station in stations:
        for period in ["2024H1", "2026H1"]:
            for y in range(1, 5):
                for x in range(1, 5):
                    score = sums[(station, period, x, y)]
                    matrix_rows.append({
                        "station": station,
                        "period": period,
                        "x": x,
                        "y": y,
                        "sum_a": score,
                        "n_posts": 100,
                        "m_xy": f"{score / 4:.2f}",
                    })
    with MATRIX_OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=matrix_rows[0].keys())
        writer.writeheader()
        writer.writerows(matrix_rows)

    print(f"events={len(records)}; matrix_cells={len(matrix_rows)}")


if __name__ == "__main__":
    main()
