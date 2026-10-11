"""Add a complete Kafka-specific question bank to the shared CSV."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "subtopics-catalog.csv"
OUTPUT = ROOT / "docs" / "topic-questions.csv"

PROMPTS = {
1: [
 "Каква е основната роля на {name} в Kafka? Дай кратък пример.",
 "Кои два Kafka термина трябва да различаваш при {name}?",
 "Как изглежда най-простият работещ пример с {name} в Kafka поток?",
 "Коя е честа грешка при използване на {name} и как я избягваш?",
 "Какво ограничение на {name} трябва да знаеш преди да го използваш в продукция?"],
2: [
 "В система за събития трябва да приложиш {name}. Какви настройки и проверки ще направиш първо?",
 "Дай практичен сценарий за {name} и обясни как ще провериш резултата.",
 "Как ще обработиш нормалния неуспешен случай при {name}, без да загубиш информация за събитието?",
 "Как ще избереш topic, partition и consumer поведение когато използваш {name}?",
 "Как ще измериш дали {name} изпълнява очакваната гаранция за потока?"],
3: [
 "Kafka поток около {name} работи при малък товар но се проваля при конкуренция. Как ще възпроизведеш и разследваш проблема?",
 "След промяна в {name} latency или consumer lag се влошава. Какви метрики ще сравниш?",
 "Какъв граничен случай при {name} може да доведе до дублиране или загуба на събитие и как ще го тестваш?",
 "Две конфигурации за {name} изглеждат еквивалентни. Как ще сравниш ordering, throughput и поведение при отказ?",
 "Потребител получава неочакван резултат при {name}. Как ще провериш producer, broker, consumer и offset състоянието?"],
4: [
 "Проектираш продукционен Kafka поток с {name}. Какви компромиси между ordering, throughput, latency и надеждност ще обсъдиш?",
 "Как ще проектираш {name} при рестарт на broker, мрежова грешка и повторно доставяне?",
 "Сравни два подхода за {name} по коректност, оперативна сложност и възстановяване.",
 "Какви инварианти, метрики и аларми ще заложиш около {name}?",
 "Как ще мигрираш съществуващ Kafka поток към {name} без да нарушиш договора с producer-и и consumer-и?"],
5: [
 "В продукция възниква инцидент свързан с {name}. Как ще ограничиш ефекта, докажеш причината и предотвратиш повторение?",
 "Как ще въведеш нова схема или конфигурация за {name} с паралелна работа и безопасен rollback?",
 "При голямо натоварване {name} има tail latency или растящ lag. Как ще намериш тесния участък и ще избереш корекция?",
 "Как ще проектираш {name} при отказ на broker, непълна репликация и възстановяване на потока?",
 "Как ще докажеш с тестове и наблюдение, че критичен Kafka компонент с {name} запазва гаранциите си?"],
}

def main():
    with CATALOG.open(encoding="utf-8-sig", newline="") as source:
        kafka = [r for r in csv.DictReader(source) if r["topic_slug"] == "kafka"]
    with OUTPUT.open(encoding="utf-8-sig", newline="") as source:
        existing = list(csv.DictReader(source)) if OUTPUT.exists() else []
    existing_keys = {(r["topic_slug"], r["subtopic_slug"], r["difficulty"], r["text"].casefold()) for r in existing}
    added = 0
    with OUTPUT.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["topic_slug", "subtopic_slug", "difficulty", "text"])
        writer.writerows([[r["topic_slug"], r["subtopic_slug"], r["difficulty"], r["text"]] for r in existing])
        for row in kafka:
            for difficulty, prompts in PROMPTS.items():
                for prompt in prompts:
                    text = prompt.format(name=f'„{row["subtopic_name"]}“')
                    key = ("kafka", row["subtopic_slug"], str(difficulty), text.casefold())
                    if key not in existing_keys:
                        writer.writerow(["kafka", row["subtopic_slug"], difficulty, text])
                        existing_keys.add(key)
                        added += 1
    print(f"Added {added} Kafka questions")

if __name__ == "__main__":
    main()
