# Каталог с подтеми

715 subtopics: по 55 за всеки от текущите 13 topics. Авторски учебен каталог, подготвен на 28.09.2026.

Каноничният файл за импорт е [deploy/subtopics-catalog.csv](../deploy/subtopics-catalog.csv). Имената са кратки английски термини; slug е стабилен ключ само в рамките на съответния topic.

## Обхват

| Topic | Общо | Съществуващи | Нови |
| --- | ---: | ---: | ---: |
| AI | 55 | 1 | 54 |
| Airflow | 55 | 2 | 53 |
| ClickHouse | 55 | 0 | 55 |
| Data Engineering | 55 | 2 | 53 |
| Design Patterns | 55 | 4 | 51 |
| Docker | 55 | 0 | 55 |
| Kafka | 55 | 2 | 53 |
| Pandas / Polars | 55 | 0 | 55 |
| PostgreSQL | 55 | 3 | 52 |
| Python | 55 | 3 | 52 |
| Redis | 55 | 1 | 54 |
| REST API | 55 | 2 | 53 |
| Testing | 55 | 1 | 54 |
| **Общо** | **715** | **21** | **694** |

Базовите 21 записа са сверени с PostgreSQL на 28.09.2026. Каталогът запазва имената и slugs на всички тях. Общите категории като Fundamentals, Creational и Behavioral остават заради историческите връзки. Те могат да се използват за сравнение между понятия, докато конкретните подтеми покриват отделните техники.

Трудността принадлежи на въпроса, а не на subtopic. Например Transactions позволява както основен въпрос за commit/rollback, така и труден сценарий за конкуриращи се транзакции. Сходно понятие в два topics има различен контекст: Kafka Transactions и PostgreSQL Transactions са отделни учебни области.

Data Engineering покрива общи архитектурни принципи, а технологичните topics — конкретни реализации. Design Patterns включва класически обектни, приложни и разпределени patterns. Pandas / Polars включва и специфични за отделната библиотека понятия; въпросът трябва да посочи библиотеката. При Airflow, Redis, Docker и други продукти въпросите за специфични функции трябва да уточняват версията и средата.

## Импорт

CSV съдържа само topic_slug, subtopic_slug и subtopic_name. Скриптът разрешава topic_id по slug и използва текущите колони на subtopics.

Локална проверка без PostgreSQL:

```sh
python deploy/import-subtopics-catalog.py --validate
```

На EC2 от /opt/learnikal, първо преглед, след това запис:

```sh
sudo -u postgres .venv/bin/python deploy/import-subtopics-catalog.py --dry-run
sudo -u postgres .venv/bin/python deploy/import-subtopics-catalog.py --apply
```

По подразбиране командата прави read-only preview. Използва LEARNIKAL_DATABASE_URL, когато е зададен, или локалната база learnikal като postgres. --apply добавя липсващите записи в една транзакция. При конфликт между име и slug спира преди запис. Повторно изпълнение пропуска съществуващите записи, включително неактивните. Не преименува, не реактивира, не изтрива и не променя връзки към questions/answers.

Импортът не е включен автоматично в deploy workflow. Комитването на каталога само по себе си не го зарежда в PostgreSQL.

## Справочни източници

Документацията служи за проверка на термините и обхвата. Списъкът е учебна подборка, а не копие на съдържанието на конкретен източник или гаранция, че всяка функция е налична в инсталирана версия.

- **AI:** [Източник 1](https://developers.google.com/machine-learning/crash-course), [Източник 2](https://developers.openai.com/api/docs/guides/retrieval).
- **Airflow:** [Документация](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/index.html).
- **ClickHouse:** [Документация](https://clickhouse.com/docs/reference/engines/table-engines/mergetree-family/mergetree).
- **Data Engineering:** [Източник 1](https://iceberg.apache.org/docs/latest/), [Източник 2](https://learn.microsoft.com/en-us/azure/architecture/patterns/).
- **Design Patterns:** [Източник 1](https://martinfowler.com/eaaCatalog/), [Източник 2](https://learn.microsoft.com/en-us/azure/architecture/patterns/).
- **Docker:** [Документация](https://docs.docker.com/manuals/).
- **Kafka:** [Документация](https://kafka.apache.org/41/design/design/).
- **Pandas / Polars:** [Източник 1](https://pandas.pydata.org/docs/user_guide/index.html), [Източник 2](https://docs.pola.rs/).
- **PostgreSQL:** [Документация](https://www.postgresql.org/docs/current/).
- **Python:** [Документация](https://docs.python.org/3/library/).
- **Redis:** [Документация](https://redis.io/docs/latest/develop/).
- **REST API:** [Документация](https://www.rfc-editor.org/rfc/rfc9110.html).
- **Testing:** [Документация](https://docs.pytest.org/en/stable/contents.html).
