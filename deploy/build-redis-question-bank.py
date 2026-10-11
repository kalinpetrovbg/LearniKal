"""Add a complete, Redis-specific question bank to the shared CSV."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "subtopics-catalog.csv"
OUTPUT = ROOT / "docs" / "topic-questions.csv"

PROMPTS = {
1: [
 "Каква е основната роля на {name} в Redis? Дай кратък пример.",
 "Кои два Redis термина трябва да различаваш при {name}?",
 "Как изглежда най-простият работещ пример с {name} през Redis клиент?",
 "Коя е честа грешка при използване на {name} и как я избягваш?",
 "Какво ограничение на {name} трябва да знаеш преди да го използваш в приложение?"],
2: [
 "В уеб приложение трябва да приложиш {name}. Какви команди и проверки ще направиш първо?",
 "Дай практичен сценарий за {name} и обясни как ще провериш резултата.",
 "Как ще обработиш нормалния неуспешен случай при {name}, без да скриеш проблема?",
 "Как ще избереш ключове, типове и TTL когато използваш {name}?",
 "Как ще измериш дали {name} подобрява поведението на приложението?"],
3: [
 "Redis операция около {name} работи локално но се проваля при конкурентни заявки. Как ще възпроизведеш и разследваш проблема?",
 "След промяна в {name} latency или memory usage се влошава. Какви метрики ще сравниш?",
 "Какъв граничен случай при {name} може да доведе до загуба или остаряване на данни и как ще го тестваш?",
 "Две реализации на {name} изглеждат еквивалентни. Как ще сравниш атомарност, производителност и поведение при отказ?",
 "Приложението получава неочакван Redis отговор при {name}. Как ще провериш клиента, командата и състоянието на сървъра?"],
4: [
 "Проектираш продукционна услуга с {name}. Какви компромиси между latency, памет, надеждност и сложност ще обсъдиш?",
 "Как ще проектираш {name} при рестарт на Redis, мрежова грешка и повторно изпълнение на заявка?",
 "Сравни два подхода за {name} по коректност при конкуренция и оперативна поддръжка.",
 "Какви инварианти, метрики и аларми ще заложиш около {name}?",
 "Как ще мигрираш съществуващо приложение към {name} без да нарушиш текущия Redis договор?"],
5: [
 "В продукция възниква инцидент свързан с {name}. Как ще ограничиш ефекта, докажеш причината и предотвратиш повторение?",
 "Как ще въведеш нова схема за {name} с dual-read или dual-write и безопасен rollback?",
 "При голямо натоварване {name} има tail latency. Как ще намериш тесния участък и ще избереш корекция?",
 "Как ще проектираш {name} при отказ на възел, failover и възстановяване на данните?",
 "Как ще докажеш с тестове и наблюдение, че критичен Redis компонент с {name} запазва гаранциите си?"],
}

def main():
    with CATALOG.open(encoding="utf-8-sig", newline="") as source:
        redis = [r for r in csv.DictReader(source) if r["topic_slug"] == "redis"]
    with OUTPUT.open(encoding="utf-8-sig", newline="") as source:
        existing = list(csv.DictReader(source)) if OUTPUT.exists() else []
    existing_keys = {(r["topic_slug"], r["subtopic_slug"], r["difficulty"], r["text"].casefold()) for r in existing}
    added = 0
    with OUTPUT.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["topic_slug", "subtopic_slug", "difficulty", "text"])
        writer.writerows([[r["topic_slug"], r["subtopic_slug"], r["difficulty"], r["text"]] for r in existing])
        for row in redis:
            for difficulty, prompts in PROMPTS.items():
                for prompt in prompts:
                    text = prompt.format(name=f'„{row["subtopic_name"]}“')
                    key = ("redis", row["subtopic_slug"], str(difficulty), text.casefold())
                    if key not in existing_keys:
                        writer.writerow(["redis", row["subtopic_slug"], difficulty, text])
                        existing_keys.add(key)
                        added += 1
    print(f"Added {added} Redis questions")

if __name__ == "__main__":
    main()
