import ast
import csv
import math
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "comparison_coded_sample.csv"
EVENTS_OUTPUT = ROOT / "data" / "article_crosspromo_events_2024H1_2026H1.csv"
MATRIX_OUTPUT = ROOT / "data" / "article_matrix_2024H1_2026H1.csv"
OIPA_OUTPUT = ROOT / "data" / "article_oipa_2024H1_2026H1.csv"

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


def balanced_round(values, target):
    """Round cells to integers while preserving their required total."""
    result = [math.floor(value) for value in values]
    remainder = target - sum(result)
    order = sorted(
        range(len(values)),
        key=lambda index: (
            values[index] - math.floor(values[index]),
            values[index],
            -index,
        ),
        reverse=True,
    )
    for index in order[:remainder]:
        result[index] += 1
    return result


def main():
    source_rows = []
    sample_sizes = defaultdict(int)
    with INPUT.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            source_rows.append(row)
            sample_sizes[(row["station"], row["profile"])] += 1

    records = []
    for row in source_rows:
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
            link_type = 4
        elif CTA.search(row["text"]):
            link_type = 3
        elif len(row["text"].strip()) > 40:
            link_type = 2
        else:
            link_type = 1

        for x in sorted({x for x, _ in destinations}):
            records.append({
                "station": row["station"],
                "period": row["profile"],
                "message_id": row["message_id"],
                "x": x,
                "y": int(row["y"]) + 1,
                "a": link_type,
                "resources": "; ".join(
                    sorted(resource for xx, resource in destinations if xx == x)
                ),
            })

    with EVENTS_OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    by_post = {}
    for row in records:
        key = (row["station"], row["period"], row["message_id"])
        if key not in by_post:
            by_post[key] = {"y": row["y"], "xs": set()}
        by_post[key]["xs"].add(row["x"])

    stations = ["Business FM", "Маяк", "Радио 1", "Дорожное радио"]
    periods = ["2024H1", "2026H1"]
    matrix_rows = []
    oipa_rows = []

    for station in stations:
        for period in periods:
            n_posts = sample_sizes[(station, period)]
            posts = [
                value for (st, pe, _), value in by_post.items()
                if st == station and pe == period
            ]
            contributions = defaultdict(float)
            for post in posts:
                share = 1.0 / len(post["xs"])
                for x in post["xs"]:
                    contributions[(x, post["y"])] += share

            raw_cells = [
                contributions[(x, y)]
                for y in range(1, 5)
                for x in range(1, 5)
            ]
            oipa = len(posts) / n_posts * 100 if n_posts else 0.0
            display_cells = balanced_round(
                [value / n_posts * 100 for value in raw_cells],
                round(oipa),
            )

            for index, (y, x) in enumerate(
                (y, x) for y in range(1, 5) for x in range(1, 5)
            ):
                matrix_rows.append({
                    "station": station,
                    "period": period,
                    "x": x,
                    "y": y,
                    "normalized_contribution": f"{raw_cells[index]:.6f}",
                    "n_posts": n_posts,
                    "m_xy": f"{raw_cells[index] / n_posts * 100:.6f}",
                    "display_points": display_cells[index],
                })

            oipa_rows.append({
                "station": station,
                "period": period,
                "active_posts": len(posts),
                "n_posts": n_posts,
                "oipa": f"{oipa:.2f}",
                "display_points": round(oipa),
            })

    with MATRIX_OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=matrix_rows[0].keys())
        writer.writeheader()
        writer.writerows(matrix_rows)

    with OIPA_OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=oipa_rows[0].keys())
        writer.writeheader()
        writer.writerows(oipa_rows)

    assert sum(row["active_posts"] for row in oipa_rows) == len(by_post)
    for row in oipa_rows:
        cells = [
            cell for cell in matrix_rows
            if cell["station"] == row["station"] and cell["period"] == row["period"]
        ]
        assert sum(cell["display_points"] for cell in cells) == row["display_points"]

    print(
        f"events={len(records)}; active_posts={len(by_post)}; "
        f"matrix_cells={len(matrix_rows)}; oipa_rows={len(oipa_rows)}"
    )


if __name__ == "__main__":
    main()
