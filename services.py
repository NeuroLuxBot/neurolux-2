from typing import List, Tuple

def make_test_report(stats_rows: List[Tuple]) -> str:
    if not stats_rows:
        return "Статистика не найдена. Введи данные по 1–3 дням."

    views = [int(r[2] or 0) for r in stats_rows]
    avg_views = sum(views) / max(1, len(views))

    best_idx = max(range(len(views)), key=lambda i: views[i])
    best_day = stats_rows[best_idx][0]
    best_views = views[best_idx]

    if avg_views >= 10000:
        verdict = "Формат выглядит сильным. Имеет смысл масштабировать серией."
    elif avg_views >= 2000:
        verdict = "Формат нормальный. Нужны вариации хуков и продолжение серии."
    else:
        verdict = "Слабые сигналы. Нужны правки хуков/темпа и серия тестов."

    return (
        f"📊 *Отчёт по 3-дневному тесту*\n\n"
        f"• Видео: {len(views)}\n"
        f"• Средние просмотры: *{int(avg_views)}*\n"
        f"• Лучший день: *{best_day}* (просмотры: *{best_views}*)\n\n"
        f"Вывод: {verdict}"
    )
