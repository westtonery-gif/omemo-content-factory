"""Application layer — orchestration over the domain aggregates.

This layer coordinates the domain (it depends on ``omemo_content_factory.domain`` and on
nothing else: no providers, adapters, queues, Skills, Tools or infrastructure — PROJECT.md
§7, ARCHITECTURE.md §15). The full Content Director / Workflow Engine (ROADMAP Stage 3) will
live here; for now it holds only the minimal vertical slice that proves the domain can execute
a single Task inside a Run (``task_execution``).
"""
