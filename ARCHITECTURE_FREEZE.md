# ARCHITECTURE_FREEZE.md — Заморозка архитектуры (baseline)

> **Место в иерархии документации (PROJECT.md, раздел 17).**
> `PROJECT.md` → `ARCHITECTURE.md` → `ROADMAP.md` → `DOMAIN_MODEL.md` → `*_SPEC` / `*_ACCEPTANCE` →
> `ADR` → **`ARCHITECTURE_FREEZE.md`** (отметка состояния) → `Implementation (Code)`.
>
> Этот документ **фиксирует фактически реализованное состояние** системы как стабильную
> архитектурную границу (baseline). Он не вводит новой функциональности — только отмечает текущее
> состояние. Источник истины остаётся прежним: `PROJECT.md` → `ARCHITECTURE.md`. Любое расхождение
> исправляется в пользу вышестоящих документов.

**Версия документа:** 1.1 (Revision 2 — **post-3A re-freeze**)
**Статус:** Принят (архитектурный baseline — заморозка)
**Дата:** 2026-06-28
**Состояние системы:** **System is in a stable architecture state (post-3A baseline).**

> **Журнал ревизий.**
> - **1.0** — минимальное ядро (Run / Task / Output / Artifact / Human Review, Schema,
>   observability-слой).
> - **1.1 (Revision 2)** — re-freeze после внедрения декларативного и wiring-слоёв и сущности-
>   дескрипторов: добавлены **Workflow** (ADR-0009), **Agent/Prompt** (ADR-0010/0011),
>   **Composition Root** (ADR-0012) и **Execution Topology + Authority** (ADR-0013); зафиксирован
>   Schema-resolution map (3A, построен, **не подключён** к исполнению). Инварианты переформулированы
>   под новую архитектуру. Поведение исполнения не изменено (transitional enforcement сохранён).

---

## 0. Назначение и сфера заморозки

- **Назначение.** Зафиксировать текущую систему как стабильную архитектурную точку; всё, что **не**
  реализовано, вводится только через `ADR → SPEC/ACCEPTANCE → реализация` (раздел 3).
- **Что входит в baseline (реализовано).** Доменное ядро (Run / Task / Output / Artifact /
  Human Review), **Schema**, **Workflow / Workflow Step** (декларация), **Agent / Prompt**
  (дескрипторы), **Composition Root** (build-time wiring), валидирующий wiring и observability-слой.
- **Чего документ НЕ делает.** Не меняет поведение, не добавляет код/сущности, не меняет ADR. Это
  **отметка состояния**.

---

## 1. Слои системы (зафиксированы, post-3A)

```
   Composition Root (build-time)    — pure dumb graph compiler (собирает граф из статических контрактов)
        │ конструирует и инъектирует (на build-time)
        ▼
   Application                      — оркестрация (CD = mapping/selection/trigger) + wiring валидации
        │
   Domain                          — единственный носитель бизнес-истины (state machine у Run)
        ▲
        │ (зависимости направлены внутрь)
   Infrastructure (LLM only)        — единственный внешний поставщик за портом TaskExecutor
   Observability (log-only)         — пассивный след решений Schema.validate
```

### 1.1 Domain layer (ядро, источник истины)
- **Модули:** `domain/run.py`, `task.py`, `output.py`, `artifact.py`, `human_review.py`,
  `schema.py`, `workflow.py`, `agent.py`, `prompt.py`.
- **Ответственность.** **Run** — агрегат-корень исполнения, **владеющий своей state machine** и
  дочерними (Task / Output / Artifact / Human Review). **Schema** — самостоятельный корень-authority
  контракта. **Workflow / Workflow Step** — неизменяемая декларация (порядок = список; `depends_on`
  инертен). **Agent / Prompt** — неизменяемые пассивные дескрипторы (`agent_ref → prompt_id`; Prompt
  = текст + ссылка на Schema). Домен ни от чего не зависит.

### 1.2 Application layer (оркестрация и wiring)
- **Модули:** `application/content_director.py`, `task_execution.py`, `schema_validation.py`,
  `schema_observability.py`.
- **Ответственность.** `ContentDirector` — **mapping** (`Workflow.steps → Task` в порядке списка),
  **selection** executor по `agent_ref`, **trigger** жизненного цикла Run (запрашивает переходы,
  машиной не владеет). `execute_task` — исполнение одного Task через корень Run. `schema_validation`
  — валидирующий wiring (opt-in). Творческих/доменных решений не принимает.

### 1.3 Composition Root (build-time wiring — outermost)
- **Модуль:** `composition.py`.
- **Ответственность.** Pure **dumb build-time graph compiler** (ADR-0012): резолвит
  `agent_ref → Agent → prompt_ref → Prompt`, конструирует `agent_ref → TaskExecutor` (инъекция
  Prompt на construction), и (3A) `agent_ref → Schema` map; structural existence checks (build-time)
  — без policy/semantics, без runtime-логики. Outermost-слой: импортирует domain/application/
  infrastructure; на него никто не зависит.

### 1.4 Infrastructure layer (только LLM)
- **Модуль:** `infrastructure/llm.py` (`LLMClient` / `AnthropicLLMClient` / `LLMTaskExecutor`).
- **Ответственность.** Единственная точка выхода во внешний мир — вызов модели за портом
  `TaskExecutor` (execution-only). Провайдер заменяем; домен/оркестратор о нём не знают.

### 1.5 Observability layer (только лог)
- **Модуль:** `application/schema_observability.py`.
- **Ответственность.** Пассивная фиксация **факта** решения `Schema.validate` (VALID/INVALID) как
  структурированного события (без сырых значений; best-effort). **Наблюдает, не управляет.**

---

## 2. Инварианты (зафиксированы, post-3A)

Переформулировка уже действующих правил; новых не вводится.

1. **Run — источник истины исполнения и владелец state machine.** Таблица переходов, guard,
   мутация статуса, события, инварианты — **внутри Run**; изменения только через корень. *(ADR-0013
   §8, Variant A.)*
2. **ContentDirector — trigger/orchestrator, не владелец машины.** Только политика
   (`steps → Task`, selection по `agent_ref`, запрос переходов); state machine в CD нет.
3. **Единый runtime-вход, без альтернатив.** Lifecycle триггерится только через CD
   (`execute_workflow`); никто не ведёт Run в обход корня.
4. **Schema = authority над execution-контрактом** (ADR-0008): определяет и валидирует;
   детерминирована, без внешних зависимостей; валидация только против `ACTIVE`-версии.
5. **Prompt = passive artifact** (ADR-0011): неизменяемый текст + `schema_ref` как **ссылка** на
   Schema (не authority). **Agent = passive descriptor** (`agent_ref → prompt_id`).
6. **Composition Root = pure dumb build-time compiler** (ADR-0012): детерминированная сборка,
   только structural existence checks; resolution `agent_ref`/`prompt_ref` — **только здесь**;
   никаких runtime-решений/policy.
7. **Workflow = декларация** (ADR-0009): порядок исполнения = порядок `steps`; `depends_on` инертен.
8. **Output = неизменяемая запись результата**; рождается терминально, не мутирует; новая попытка —
   новый Output.
9. **Observability НЕ влияет на исполнение** (opt-in, best-effort).
10. **Зависимости направлены внутрь.** Infrastructure/Application/Composition зависят от Domain;
    домен — ни от кого. Schema/Workflow/Agent/Prompt-модули ядро не импортируют наружу.

---

## 3. Границы запрета расширения (freeze boundaries)

Следующее **намеренно отсутствует** и вводится **только через ADR**:

- **No event sourcing.** События — след в журнале Run; реконструкция состояния из событий — через ADR.
- **No analytics pipeline.** Observability — только лог факта; агрегация/метрики/аналитический агент
  (отложенный `Analytics Record`, DOMAIN_MODEL §2.15) — через ADR.
- **No feedback loop.** Автоматическая реакция на накопленные данные — через ADR.
- **No schema evolution engine.** Миграции/совместимость версий/авто-эволюция контрактов — через ADR.
- **No new domain entities без процесса.** **Реализованы:** Run/Task/Output/Artifact/Human Review,
  Schema, Workflow/Workflow Step, Agent/Prompt. **Ещё не реализованы** (каждая — ADR→SPEC→tests):
  **Evaluation/QA**, **Content Brief**, **Content Type**, **Analytics Record**.

> **Отложенные пункты в силе:** конвергенция двух путей записи Output в единый валидирующий
> `record_output` (ADR-0008 target — **Slice 3 в работе**), доменное событие/маршрутизация INVALID,
> fail-fast в оркестрации (F1), флаг **G-1** (рантайм-актор каталога Schema). Все — через ADR/
> запланированные слайсы, не «по ходу».

---

## 4. Post-3A заметки о состоянии (re-freeze)

- **Schema-resolution map построен, но НЕ подключён.** `composition.build_schema_map` создаёт
  `agent_ref → Schema`, но **не используется** ни в одном пути исполнения (orphan capability) —
  **нулевой эффект на runtime**. Подключение — Slice 3D.
- **Transitional enforcement сохранён.** Default-путь фиксирует Output `VALID` через legacy
  `record_output` (без `Schema.validate`); целевая модель — единый валидирующий путь (ADR-0008),
  достигается конвергенцией **Slice 3 (3C/3D)**. До конвергенции — это санкционированное переходное
  состояние, не дрейф.
- **Скрытых эффектов от Schema-слоя нет** (подтверждено integration stabilization pass): детерминизм
  CD→executor→Run сохранён; executor-map и schema-map независимы (referential consistency, не
  coupling); `build_schema_map` — pure build-time (модель не вызывает, Run не создаёт).

---

## 5. Статус системы

> **System is in a stable architecture state (post-3A baseline).**

- Реализованы и зелены по гейту: ядро (Run/Task/Output/Artifact/Human Review), Schema, Workflow,
  Agent/Prompt, Composition Root, валидирующий wiring, observability.
- Любое **новое** расширение (Evaluation/QA, Content Brief/Type, Analytics, event sourcing,
  schema-evolution, feedback) пересекает раздел 3 и требует `ADR → SPEC/ACCEPTANCE → реализация`.
- Дальнейшая конвергенция enforcement идёт **запланированными слайсами** (Slice 3), а не дрейфом.

---

## Приложение A. Трассируемость

| Элемент baseline | Опора |
|---|---|
| Слои и направление зависимостей | `ARCHITECTURE.md` §15; `PROJECT.md` §7 |
| Run как корень + state machine | `DOMAIN_MODEL.md` §9.1; `ADR-0003`; `ADR-0013` §8 (Variant A) |
| Task / Output / Artifact / Human Review | `ADR-0004` / `0005` / `0006` / `0007` |
| Schema (authority, жизненный цикл, валидация) | `ADR-0008`; `SCHEMA_SPEC.md` / `SCHEMA_ACCEPTANCE.md` |
| Workflow / Workflow Step (декларация) | `ADR-0009`; `WORKFLOW_SPEC.md` / `WORKFLOW_ACCEPTANCE.md` |
| Agent boundary / Agent+Prompt (дескрипторы) | `ADR-0010` / `ADR-0011`; `AGENT_SPEC.md` |
| Composition Root (dumb build-time wiring) | `ADR-0012`; `composition.py` |
| Execution Topology + Authority (single entry) | `ADR-0013` |
| Два пути записи Output (legacy + validated) | `ADR-0008` (Migration); `application/schema_validation.py` |
| Observability (log-only) | `application/schema_observability.py` |
| Schema-resolution map (3A, не подключён) | `composition.build_schema_map` |

> Документ фиксирует состояние и не имеет приоритета над `PROJECT.md` / `ARCHITECTURE.md`. При любом
> расхождении — источник истины вышестоящий (PROJECT.md, раздел 17).
