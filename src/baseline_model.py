#!/usr/bin/env python3
"""Baseline-модель для истории игр с 8 умениями и выбором последних 4."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Record:
    game_id: int
    all_skills: list[int]
    selected_skills: tuple[int, int, int, int]
    result: int
    hero: str | None = None


class SkillWinModel:
    def __init__(self, alpha: float = 2.0, beta: float = 2.0, skill_weight: float = 0.35) -> None:
        self.alpha = alpha
        self.beta = beta
        self.skill_weight = skill_weight

        self.global_wins = 0
        self.global_total = 0
        self.combo_stats: dict[tuple[int, int, int, int], list[int]] = {}
        self.skill_stats: dict[int, list[int]] = {}

    def fit(self, records: Iterable[Record]) -> None:
        for rec in records:
            win = rec.result
            self.global_wins += win
            self.global_total += 1

            combo = rec.selected_skills
            combo_wins, combo_total = self.combo_stats.get(combo, [0, 0])
            self.combo_stats[combo] = [combo_wins + win, combo_total + 1]

            for skill in combo:
                s_wins, s_total = self.skill_stats.get(skill, [0, 0])
                self.skill_stats[skill] = [s_wins + win, s_total + 1]

    @property
    def global_rate(self) -> float:
        if self.global_total == 0:
            return 0.5
        return self.global_wins / self.global_total

    def _smoothed_rate(self, wins: int, total: int) -> float:
        return (wins + self.alpha) / (total + self.alpha + self.beta)

    def predict_proba(self, selected_skills: tuple[int, int, int, int]) -> float:
        combo_wins, combo_total = self.combo_stats.get(selected_skills, [0, 0])
        combo_rate = self._smoothed_rate(combo_wins, combo_total)

        skill_rates: list[float] = []
        for s in selected_skills:
            wins, total = self.skill_stats.get(s, [0, 0])
            if total == 0:
                skill_rates.append(self.global_rate)
            else:
                skill_rates.append(self._smoothed_rate(wins, total))
        avg_skill_rate = sum(skill_rates) / len(skill_rates)

        p = (1.0 - self.skill_weight) * combo_rate + self.skill_weight * avg_skill_rate
        return max(0.0, min(1.0, p))

    def predict(self, selected_skills: tuple[int, int, int, int], threshold: float = 0.5) -> int:
        return 1 if self.predict_proba(selected_skills) >= threshold else 0


def parse_record(raw: object) -> Record:
    if isinstance(raw, list):
        if len(raw) < 10:
            raise ValueError(f"Ожидался список длиной >= 10, получено {len(raw)}")
        game_id = int(raw[0])
        all_skills = [int(x) for x in raw[1:9]]
        result = int(raw[9])
        hero = str(raw[10]) if len(raw) >= 11 else None
        return Record(
            game_id=game_id,
            all_skills=all_skills,
            selected_skills=tuple(all_skills[-4:]),
            result=result,
            hero=hero,
        )

    if isinstance(raw, dict):
        game_id = int(raw["game_id"])
        all_skills = [int(x) for x in raw["all_skills"]]
        if len(all_skills) != 8:
            raise ValueError("Поле all_skills должно содержать ровно 8 умений")
        result = int(raw["result"])
        hero = str(raw["hero"]) if "hero" in raw and raw["hero"] is not None else None
        return Record(
            game_id=game_id,
            all_skills=all_skills,
            selected_skills=tuple(all_skills[-4:]),
            result=result,
            hero=hero,
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


def train_test_split(records: list[Record], test_size: float, seed: int = 42) -> tuple[list[Record], list[Record]]:
    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size должен быть в диапазоне (0, 1)")
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    border = int(len(shuffled) * (1.0 - test_size))
    return shuffled[:border], shuffled[border:]


def evaluate(model: SkillWinModel, test: list[Record]) -> dict[str, float]:
    if not test:
        return {"accuracy": 0.0, "avg_pred": 0.0}
    correct = 0
    preds = []
    for rec in test:
        p = model.predict_proba(rec.selected_skills)
        y = 1 if p >= 0.5 else 0
        preds.append(p)
        correct += int(y == rec.result)
    return {
        "accuracy": correct / len(test),
        "avg_pred": sum(preds) / len(preds),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline для прогнозирования победы по 4 выбранным умениям")
    parser.add_argument("--input", required=True, type=Path, help="Путь к JSONL файлу с историей")
    parser.add_argument("--test-size", type=float, default=0.2, help="Доля теста (по умолчанию 0.2)")
    parser.add_argument("--predict", nargs=4, type=int, metavar=("S1", "S2", "S3", "S4"), help="Сделать прогноз для 4 умений")
    args = parser.parse_args()

    records = load_records(args.input)
    if len(records) < 5:
        print(f"Предупреждение: мало данных ({len(records)} игр), метрики могут быть шумными")

    train, test = train_test_split(records, test_size=args.test_size)
    model = SkillWinModel()
    model.fit(train)

    metrics = evaluate(model, test)
    print(f"Всего игр: {len(records)} | train: {len(train)} | test: {len(test)}")
    print(f"Global winrate (train): {model.global_rate:.3f}")
    print(f"Accuracy (test): {metrics['accuracy']:.3f}")

    if args.predict:
        combo = tuple(args.predict)
        proba = model.predict_proba(combo)
        pred = 1 if proba >= 0.5 else 0
        print(f"Прогноз для {combo}: p(win)={proba:.3f}, pred={pred}")


if __name__ == "__main__":
    main()
