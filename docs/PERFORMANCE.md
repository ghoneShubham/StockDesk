# Performance

Filled in on Day 10 once the demo dataset (Section 7.1) exists and
django-debug-toolbar is wired up. Will contain:

- Before/after query counts per page (target: ≤ 15 queries/page)
- Before/after response times for each report (target: < 500ms)
- `EXPLAIN ANALYZE` plans for the three slowest report queries, before and
  after adding indexes
- List of indexes added and the reasoning for each
- N+1 query fixes (`select_related` / `prefetch_related`) with before/after
