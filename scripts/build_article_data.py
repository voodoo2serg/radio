#!/usr/bin/env python3
"""Build the publication-facing dataset and the X-axis resource audit."""

from __future__ import annotations

import ast
import csv
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TARGET_PERIODS = {"2024H1", "2026H1"}
THRESHOLD_POSTS = 10
THRESHOLD_MONTHS = 2

Y_LABELS = {
    0: "репликация или анонс эфирного материала",
    1: "адаптация эфирного материала для Telegram",
    2: "специальный платформенный формат",
    3: "самостоятельный завершённый медиатекст",
}

STATION_DIRS = {
    "Business FM": "BFM",
    "Маяк": "Mayak",
    "Радио 1": "Radio1",
    "Дорожное радио": "Dorozhnoe",
}


class TelegramExportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.message_depth = 0
        self.text_depth = 0
        self.current: dict | None = None
        self.messages: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attr = dict(attrs)
        classes = set(attr.get("class", "").split())
        if tag == "div" and "message" in classes and self.message_depth == 0:
            self.message_depth = 1
            self.current = {"id": attr.get("id", ""), "date": None, "hrefs": []}
            return
        if self.message_depth and tag == "div":
            self.message_depth += 1
        if self.current is None:
            return
        if tag == "div" and {"date", "details"}.issubset(classes):
            match = re.search(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b", attr.get("title", ""))
            if match:
                self.current["date"] = (match.group(3), match.group(2))
        if tag == "div" and "text" in classes:
            self.text_depth = 1
        elif self.text_depth and tag == "div":
            self.text_depth += 1
        if tag == "a" and self.text_depth:
            href = attr.get("href", "").strip()
            if href and not href.startswith(("#", "mailto:", "javascript:")):
                self.current["hrefs"].append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or not self.message_depth:
            return
        if self.text_depth:
            self.text_depth -= 1
        self.message_depth -= 1
        if self.message_depth == 0 and self.current is not None:
            if self.current["date"]:
                self.messages.append(self.current)
            self.current = None
            self.text_depth = 0


def normalized_url(url: str) -> tuple[str, str, str]:
    if re.match(r"^[\w.-]+\.[a-zа-я]{2,}(/|$)", url, re.I):
        url = "https://" + url
    parsed = urlparse(url.replace("&amp;", "&"))
    return (
        parsed.netloc.lower().removeprefix("www."),
        parsed.path.lower(),
        parsed.query.lower(),
    )


def classify_resource(station: str, url: str) -> tuple[str, str, str] | None:
    host, path, query = normalized_url(url)
    joined = path + "?" + query

    if station == "Business FM":
        if host == "bfm.ru" or host.endswith(".bfm.ru"):
            return "website", "Официальный сайт Business FM", "bfm.ru"
        if host == "max.ru" and path.startswith("/bfm"):
            return "max", "Официальный канал Business FM в MAX", "max.ru/bfm"
        if "id1482608536" in joined or "com.radio.bfm" in joined:
            return "app", "Мобильное приложение Business FM", "com.radio.bfm"

    if station == "Маяк":
        if host == "smotrim.ru":
            return "smotrim", "Платформа ВГТРК «Смотрим»", "smotrim.ru"
        if host in {"radiomayak.ru", "pro.radiomayak.ru"}:
            return "website", "Сайт и специальные проекты «Маяка»", "radiomayak.ru"
        if host in {"vk.com", "m.vk.com"} and (
            path.startswith("/mayakfm") or path.startswith("/audios-35744422")
        ):
            return "vk", "Официальная площадка «Маяка» во ВКонтакте", "vk.com/mayakfm"
        if host in {"music.yandex.ru", "music.yandex.com"}:
            return "yandex_music", "Программы «Маяка» в Яндекс Музыке", "music.yandex.ru"
        if host == "podcasts.apple.com":
            return "apple_podcasts", "Подкасты «Маяка» в Apple Podcasts", "podcasts.apple.com"
        if host == "max.ru" and path.startswith("/mayakfm"):
            return "max", "Официальный канал «Маяка» в MAX", "max.ru/mayakfm"
        if host in {"dzen.ru", "zen.yandex.ru"} and "radiomayak" in path:
            return "dzen", "Официальный канал «Маяка» в Дзене", "dzen.ru/radiomayak"

    if station == "Радио 1":
        if host in {"radio1.ru", "radio1.news"}:
            return "website", "Официальный сайт «Радио 1»", "radio1.ru / radio1.news"
        if host == "vk.com" and (
            path.startswith("/radio1_news") or path.startswith("/radio1_ru")
        ):
            return "vk", "Официальная площадка «Радио 1» во ВКонтакте", "vk.com/radio1_ru"
        if host == "podcast.ru":
            return "podcast_ru", "Подкасты «Радио 1» на podcast.ru", "podcast.ru"
        if host == "podster.fm":
            return "podster", "Подкасты «Радио 1» на Podster", "podster.fm"
        if host == "max.ru" and path.startswith("/radio1"):
            return "max", "Официальный канал «Радио 1» в MAX", "max.ru/Radio1"
        if host in {"dzen.ru", "zen.yandex.ru"} and path.startswith("/radio1"):
            return "dzen", "Официальный канал «Радио 1» в Дзене", "dzen.ru/radio1"
        if host in {"youtube.com", "m.youtube.com"} and (
            "radio1" in path or "%d0%a0%d0%b0%d0%b4%d0%b8%d0%be1" in path
        ):
            return "youtube", "Официальный YouTube-канал «Радио 1»", "youtube.com/@_Radio1"
        if host == "rutube.ru" and path.startswith("/channel/25615139"):
            return "rutube", "Официальный RuTube-канал «Радио 1»", "rutube.ru/channel/25615139"
        if host == "ok.ru" and path.startswith("/radio1.news"):
            return "ok", "Площадка «Радио 1» в Одноклассниках", "ok.ru/radio1.news"

    if station == "Дорожное радио":
        if host == "dorognoe.ru" or host.endswith(".dorognoe.ru"):
            return "website", "Официальный сайт «Дорожного радио»", "dorognoe.ru"
        if host == "ok.ru" and path.startswith("/dorognoe"):
            return "ok", "Площадка «Дорожного радио» в Одноклассниках", "ok.ru/dorognoe"
        if host == "vk.com" and path.startswith("/dorognoe"):
            return "vk", "Площадка «Дорожного радио» во ВКонтакте", "vk.com/dorognoe"
        if "ru.roadradio.europa" in joined or host == "6273241.redirect.appmetrica.yandex.com":
            return "app", "Мобильное приложение «Дорожного радио»", "ru.roadradio.europa"
    return None


def period(year: str, month: str) -> str:
    return year + ("H1" if int(month) <= 6 else "H2")


def build_x_audit() -> list[dict]:
    observations = defaultdict(lambda: {"posts": set(), "months": set()})
    labels: dict[tuple[str, str], tuple[str, str]] = {}
    for station, dirname in STATION_DIRS.items():
        for source in sorted((ROOT / dirname).glob("messages*.html")):
            parser = TelegramExportParser()
            parser.feed(source.read_text(encoding="utf-8", errors="ignore"))
            for message in parser.messages:
                year, month = message["date"]
                profile = period(year, month)
                if profile not in TARGET_PERIODS:
                    continue
                resources = set()
                for href in message["hrefs"]:
                    resource = classify_resource(station, href)
                    if resource:
                        resources.add(resource)
                for resource_id, label, locator in resources:
                    key = (station, profile, resource_id)
                    observations[key]["posts"].add((source.name, message["id"]))
                    observations[key]["months"].add(month)
                    labels[(station, resource_id)] = (label, locator)

    rows = []
    for (station, profile, resource_id), data in sorted(observations.items()):
        posts = len(data["posts"])
        months = len(data["months"])
        qualifies = posts >= THRESHOLD_POSTS and months >= THRESHOLD_MONTHS
        label, locator = labels[(station, resource_id)]
        rows.append(
            {
                "station": station,
                "profile": profile,
                "resource_id": resource_id,
                "resource_label": label,
                "resource_locator": locator,
                "posts_with_link": posts,
                "months_present": months,
                "threshold_posts": THRESHOLD_POSTS,
                "threshold_months": THRESHOLD_MONTHS,
                "qualifies_for_x": "yes" if qualifies else "no",
            }
        )

    qualified = defaultdict(int)
    for row in rows:
        if row["qualifies_for_x"] == "yes":
            qualified[(row["station"], row["profile"])] += 1
    for row in rows:
        count = qualified[(row["station"], row["profile"])]
        row["qualified_resource_count"] = count
        row["x_level"] = "X0" if count == 0 else f"X{min(count, 3)}"
    return rows


def read_comparison_sample() -> list[dict]:
    with (DATA / "comparison_coded_sample.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_article_sample(source_rows: list[dict]) -> list[dict]:
    rows = []
    for row in source_rows:
        y = int(row["y"])
        hrefs = ast.literal_eval(row["hrefs"]) if row["hrefs"] else []
        rows.append(
            {
                "station": row["station"],
                "profile": row["profile"],
                "message_id": row["message_id"],
                "datetime": row["datetime"],
                "source_file": row["source_file"],
                "text": row["text"],
                "hrefs": " | ".join(hrefs),
                "y_code": f"Y{y}",
                "y_category": Y_LABELS[y],
                "y_reason": row["y_reason"],
            }
        )
    return rows


def build_results(sample: list[dict], audit: list[dict]) -> list[dict]:
    counts = defaultdict(lambda: defaultdict(int))
    for row in sample:
        counts[(row["station"], row["profile"])][row["y_code"]] += 1

    qualified_resources = defaultdict(list)
    x_levels = {}
    for row in audit:
        key = (row["station"], row["profile"])
        x_levels[key] = row["x_level"]
        if row["qualifies_for_x"] == "yes":
            qualified_resources[key].append(row["resource_label"])

    rows = []
    for key in sorted(counts):
        station, profile = key
        values = counts[key]
        majority = next((code for code in ("Y0", "Y1", "Y2", "Y3") if values[code] > 50), None)
        most_frequent = max(("Y0", "Y1", "Y2", "Y3"), key=lambda code: values[code])
        content_profile = majority if majority else "mixed"
        rows.append(
            {
                "station": station,
                "profile": profile,
                "x_level": x_levels.get(key, "X0"),
                "qualified_resources": " | ".join(qualified_resources[key]),
                "Y0": values["Y0"],
                "Y1": values["Y1"],
                "Y2": values["Y2"],
                "Y3": values["Y3"],
                "content_profile": content_profile,
                "most_frequent_y": most_frequent,
                "article_characteristic": (
                    f"{x_levels.get(key, 'X0')}{majority}" if majority else f"{x_levels.get(key, 'X0')}; mixed Y profile"
                ),
            }
        )
    return rows


def main() -> None:
    source = read_comparison_sample()
    if len(source) != 800:
        raise SystemExit(f"Expected 800 comparison rows, found {len(source)}")
    article_sample = build_article_sample(source)
    audit = build_x_audit()
    results = build_results(article_sample, audit)

    write_csv(
        DATA / "platform_x_audit.csv",
        [
            "station", "profile", "resource_id", "resource_label", "resource_locator",
            "posts_with_link", "months_present", "threshold_posts", "threshold_months",
            "qualifies_for_x", "qualified_resource_count", "x_level",
        ],
        audit,
    )
    write_csv(
        DATA / "article_xy_results.csv",
        [
            "station", "profile", "x_level", "qualified_resources", "Y0", "Y1", "Y2", "Y3",
            "content_profile", "most_frequent_y", "article_characteristic",
        ],
        results,
    )


if __name__ == "__main__":
    main()
