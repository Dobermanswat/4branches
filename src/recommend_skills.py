#!/usr/bin/env python3
"""Рекомендация 4 навыков и героя по истории матчей (точные совпадения 4/4)."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

NUM_SKILLS = 13


@dataclass
class Record:
    game_id: int
    selected_skills: tuple[int, int, int, int]
    result: int
    hero: str


def parse_record(raw: object) -> Record:
    """Поддерживает формат списка и словаря."""
    if isinstance(raw, list):
        if len(raw) < 11:
            raise ValueError(f"Ожидалась запись длиной >= 11, получено {len(raw)}")
        all_skills = [int(x) for x in raw[1:9]]
        if len(all_skills) != 8:
            raise ValueError("В записи-списке должно быть ровно 8 навыков")
        return Record(
            game_id=int(raw[0]),
            selected_skills=tuple(all_skills[-4:]),
            result=int(raw[9]),
            hero=str(raw[10]),
        )

    if isinstance(raw, dict):
        all_skills = [int(x) for x in raw["all_skills"]]
        if len(all_skills) != 8:
            raise ValueError("Поле all_skills должно содержать ровно 8 навыков")
        hero = raw.get("hero")
        if hero is None:
            raise ValueError("Поле hero обязательно для рекомендаций")
        return Record(
            game_id=int(raw["game_id"]),
            selected_skills=tuple(all_skills[-4:]),
            result=int(raw["result"]),
            hero=str(hero),
        )

    raise ValueError(f"Неподдерживаемый формат записи: {type(raw)}")


def load_records(path: Path) -> list[Record]:
    records: list[Record] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            try:
                records.append(parse_record(raw))
            except Exception as e:
                raise ValueError(f"Ошибка в строке {i}: {e}") from e
    return records


def recommend_skills_exact_4of4(
    records: list[Record],
    blocked: list[int],
    min_games: int = 2,
    top_k: int = 5,
) -> list[dict[str, object]]:
    all_skills = set(range(1, NUM_SKILLS + 1))
    blocked_set = set(blocked)
    unknown = blocked_set - all_skills
    if unknown:
        raise ValueError(f"Некорректные номера заблокированных навыков: {sorted(unknown)}")

    available = all_skills - blocked_set

    # combo -> hero -> [wins, games]
    stats: dict[tuple[int, int, int, int], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )

    skipped_invalid_combo = 0
    for rec in records:
        combo = tuple(sorted(rec.selected_skills))
        # В ряде строк бывают дубли навыков, такие комбинации отбрасываем для режима "точные 4/4".
        if len(set(combo)) != 4:
            skipped_invalid_combo += 1
            continue
        if not set(combo).issubset(available):
            continue

        stats[combo][rec.hero][0] += rec.result
        stats[combo][rec.hero][1] += 1

    results: list[dict[str, object]] = []
    for combo, hero_stats in stats.items():
        best_hero = None
        best_winrate = -1.0
        best_games = 0

        for hero, (wins, games) in hero_stats.items():
            games_int = int(games)
            if games_int < min_games:
                continue
            winrate = wins / games
            if winrate > best_winrate or (winrate == best_winrate and games_int > best_games):
                best_winrate = winrate
                best_hero = hero
                best_games = games_int

        if best_hero is not None:
            results.append(
                {
                    "combo": combo,
                    "hero": best_hero,
                    "winrate": best_winrate,
                    "games": best_games,
                }
            )

    results_sorted = sorted(results, key=lambda x: (x["winrate"], x["games"]), reverse=True)

    print(
        f"\nТоп-{top_k} четверок по винрейту "
        f"(от {min_games} игр у героя на комбо, только точные 4/4 совпадения):"
    )
    print("Навыки         | Винрейт % | Игр | Лучший герой")
    print("-" * 65)
    for res in results_sorted[:top_k]:
        print(f"{res['combo']}  | {res['winrate']*100:7.1f}% | {res['games']:3d} | {res['hero']}")
    print("-" * 65)

    if skipped_invalid_combo:
        print(f"Пропущено записей с дубликатами в выбранных 4 навыках: {skipped_invalid_combo}")

    return results_sorted[:top_k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Рекомендация связки 4 навыков + лучшего героя")
    parser.add_argument("--input", required=True, type=Path, help="Путь к JSONL файлу с историей")
    parser.add_argument("--blocked", nargs="*", type=int, default=None, help="Заблокированные навыки")
    parser.add_argument("--min-games", type=int, default=2, help="Минимум игр по герою/комбо")
    parser.add_argument("--top-k", type=int, default=5, help="Сколько топ-комбо показать")
    args = parser.parse_args()

    records = load_records(args.input)

    blocked = args.blocked
    if blocked is None:
        print("Введите заблокированные навыки через пробел (например: 9 10 11 12 13):")
        blocked = [int(x) for x in input().strip().split()]

    available = sorted(set(range(1, NUM_SKILLS + 1)) - set(blocked))
    print(f"Доступные навыки: {available}")

    recommend_skills_exact_4of4(records, blocked, min_games=args.min_games, top_k=args.top_k)


if __name__ == "__main__":
    main()
