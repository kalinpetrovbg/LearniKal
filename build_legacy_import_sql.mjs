import fs from "node:fs/promises";
import path from "node:path";

const root = "C:/Users/kalin/Documents/ChatGPT/Learnikal";
const audit = JSON.parse(await fs.readFile(path.join(root, "tmp", "legacy-review-audit.json"), "utf8"));
const output = path.join(root, "outputs", "import-legacy-md-ratings.sql");

const quote = (value) => `'${String(value).replaceAll("'", "''")}'`;
const topics = [...new Set(audit.questions.map((q) => q.topic))].sort();
const subtopicRows = new Map();
for (const question of audit.questions) {
  const key = `${question.topic}\0${question.subtopic}`;
  if (!subtopicRows.has(key)) {
    const name = question.subtopic.split("_").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
    subtopicRows.set(key, { topic: question.topic, slug: question.subtopic, name });
  }
}
const answered = audit.interactions.filter((row) => row.reviewStatus === "review");

const statements = [
  "-- Imports questions and inferred numeric ratings from LEARNING_HISTORY.md.",
  "-- Answer prose/evidence is deliberately not written to PostgreSQL.",
  "-- Questions are inactive until explicitly reviewed and activated.",
  "-- Safe to rerun: existing topics/subtopics/questions and question-linked answers are retained.",
  "BEGIN;",
  "",
  "-- Add only the broad subtopic categories used by this import.",
  "INSERT INTO subtopics (topic_id, slug, name, is_active)",
  "SELECT t.id, v.slug, v.name, true",
  `FROM (VALUES\n${[...subtopicRows.values()].map((r) => `    (${quote(r.topic)}, ${quote(r.slug)}, ${quote(r.name)})`).join(",\n")}\n) AS v(topic_slug, slug, name)`,
  "JOIN topics t ON t.slug = v.topic_slug",
  "ON CONFLICT (topic_id, slug) DO NOTHING;",
  "",
  "-- Add all 87 historical questions as inactive legacy questions.",
  "INSERT INTO questions (topic_id, subtopic_id, text, difficulty, is_active)",
  "SELECT t.id, s.id, v.question_text, v.difficulty, false",
  `FROM (VALUES\n${audit.questions.map((q) => `    (${quote(q.topic)}, ${quote(q.subtopic)}, ${quote(q.text)}, ${q.difficulty})`).join(",\n")}\n) AS v(topic_slug, subtopic_slug, question_text, difficulty)`,
  "JOIN topics t ON t.slug = v.topic_slug",
  "JOIN subtopics s ON s.topic_id = t.id AND s.slug = v.subtopic_slug",
  "WHERE NOT EXISTS (",
  "    SELECT 1 FROM questions existing",
  "    WHERE existing.subtopic_id = s.id AND lower(existing.text) = lower(v.question_text)",
  ");",
  "",
  `-- Add ${answered.length} rating rows for recorded responses; the one explicitly unanswered prompt is excluded.`,
  "-- The source files contain no reliable response timestamps, so created_at uses its database default.",
  "INSERT INTO answers (",
  "    user_id, topic_id, subtopic_id, question_id, score, difficulty,",
  "    independence_score, clarity_score, completeness_score",
  ")",
  "SELECT u.id, t.id, s.id, q.id, v.score, v.difficulty,",
  "       v.independence_score, v.clarity_score, v.completeness_score",
  `FROM (VALUES\n${answered.map((a) => `    (${quote(a.topic)}, ${quote(a.subtopic)}, ${quote(a.question)}, ${a.score}, ${a.difficulty}, ${a.independence}, ${a.clarity}, ${a.completeness})`).join(",\n")}\n) AS v(topic_slug, subtopic_slug, question_text, score, difficulty, independence_score, clarity_score, completeness_score)`,
  "JOIN users u ON u.username = 'kalin'",
  "JOIN topics t ON t.slug = v.topic_slug",
  "JOIN subtopics s ON s.topic_id = t.id AND s.slug = v.subtopic_slug",
  "JOIN questions q ON q.topic_id = t.id AND q.subtopic_id = s.id AND lower(q.text) = lower(v.question_text)",
  "WHERE NOT EXISTS (",
  "    SELECT 1 FROM answers existing",
  "    WHERE existing.user_id = u.id AND existing.question_id = q.id",
  ");",
  "",
  "COMMIT;",
  "",
  "-- Validation after import:",
  "-- SELECT t.slug, count(*) FROM answers a JOIN topics t ON t.id = a.topic_id",
  "-- JOIN questions q ON q.id = a.question_id GROUP BY t.slug ORDER BY t.slug;",
  "-- SELECT count(*) FROM questions WHERE is_active = false;",
  "",
];

await fs.writeFile(output, statements.join("\n"), "utf8");
console.log(JSON.stringify({ output, questions: audit.questions.length, answers: answered.length, unanswered: audit.interactions.length - answered.length, subtopics: subtopicRows.size, topics: topics.length }));
