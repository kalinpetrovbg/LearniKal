"""Fill every missing non-Python catalog combination with topic-specific questions."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "subtopics-catalog.csv"
OUTPUT = ROOT / "docs" / "topic-questions.csv"

DOMAIN = {
 "ai":"AI система", "airflow":"Airflow DAG", "clickhouse":"ClickHouse аналитичен клъстер",
 "data_engineering":"data engineering pipeline", "design_patterns":"Python софтуерна архитектура",
 "docker":"Docker контейнерна среда", "pandas_polars":"Pandas/Polars обработка на данни",
 "postgresql":"PostgreSQL приложение", "rest_api":"REST API", "testing":"тестова стратегия",
}
PROMPTS = {
1:["Каква е основната цел на „{sub}“ в {domain}? Дай кратък пример.","Кои два термина трябва да различаваш при „{sub}“?","Как изглежда най-простият работещ пример за „{sub}“?","Коя е честа грешка при „{sub}“ и как я избягваш?","Какво основно ограничение на „{sub}“ трябва да знаеш?"],
2:["В {domain} трябва да приложиш „{sub}“. Какви стъпки ще направиш първо?","Дай практичен сценарий за „{sub}“ и обясни как ще провериш резултата.","Как ще обработиш нормалния неуспешен случай при „{sub}“?","Какви настройки, входове и зависимости ще провериш преди „{sub}“?","Как ще измериш дали „{sub}“ изпълнява очакваната си роля?"],
3:["„{sub}“ работи при малък товар, но се проваля при конкуренция. Как ще възпроизведеш и разследваш проблема?","След промяна в „{sub}“ latency или ресурсите се влошават. Какви метрики ще сравниш?","Какъв граничен случай при „{sub}“ може да даде грешен резултат и как ще го тестваш?","Две реализации на „{sub}“ изглеждат еквивалентни. Как ще сравниш поведението им при отказ?","Получаваш неочакван резултат около „{sub}“. Как ще локализираш причината?"],
4:["Проектираш продукционен {domain} с „{sub}“. Какви компромиси ще обсъдиш?","Как ще осигуриш надеждност, наблюдаемост и тестируемост на решение с „{sub}“?","Сравни два подхода за „{sub}“ по производителност, цена и поддръжка.","Какви инварианти, метрики и аларми ще заложиш около „{sub}“?","Как ще мигрираш съществуващ код или конфигурация към „{sub}“ без прекъсване?"],
5:["В продукция възниква инцидент около „{sub}“. Как ще ограничиш ефекта и докажеш причината?","Как ще въведеш нова версия на „{sub}“ с паралелна работа и rollback?","При голямо натоварване „{sub}“ има tail latency. Как ще намериш тесния участък?","Как ще проектираш „{sub}“ при отказ на компонент и последващо възстановяване?","Как ще докажеш с тестове и наблюдение, че критично решение с „{sub}“ запазва гаранциите си?"],
}

def main():
    with CATALOG.open(encoding="utf-8-sig", newline="") as source:
        catalog = list(csv.DictReader(source))
    with OUTPUT.open(encoding="utf-8-sig", newline="") as source:
        existing = list(csv.DictReader(source)) if OUTPUT.exists() else []
    # Keep at most five rows per catalog/difficulty pair if a previous attempt
    # appended a second generated set.
    kept=[]; counts={}
    for row in existing:
        pair=(row["topic_slug"],row["subtopic_slug"],row["difficulty"])
        if counts.get(pair,0) < 5:
            kept.append(row); counts[pair]=counts.get(pair,0)+1
    existing=kept
    keys={(r["topic_slug"],r["subtopic_slug"],r["difficulty"],r["text"].casefold()) for r in existing}
    added=0
    with OUTPUT.open("w",encoding="utf-8",newline="") as target:
        writer=csv.writer(target); writer.writerow(["topic_slug","subtopic_slug","difficulty","text"])
        writer.writerows([[r["topic_slug"],r["subtopic_slug"],r["difficulty"],r["text"]] for r in existing])
        for row in catalog:
            topic=row["topic_slug"]
            if topic not in DOMAIN or topic=="python": continue
            for difficulty, prompts in PROMPTS.items():
                for prompt in prompts:
                    text=prompt.format(domain=DOMAIN[topic],sub=row["subtopic_name"])
                    key=(topic,row["subtopic_slug"],str(difficulty),text.casefold())
                    pair=(topic,row["subtopic_slug"],str(difficulty))
                    if counts.get(pair, 0) < 5 and key not in keys:
                        writer.writerow([topic,row["subtopic_slug"],difficulty,text]); keys.add(key); added+=1
                        counts[pair]=counts.get(pair,0)+1
    print(f"Added {added} questions for remaining topics")

if __name__=="__main__": main()
