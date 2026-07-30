# SQL — Reports (ORM vs. Raw SQL)

Filled in on Days 11–12. Each of the 13 required reports (PRD Section 8) will
be documented here with:

1. The Django ORM implementation and its generated SQL (`str(queryset.query)`)
2. A hand-written raw SQL implementation (`connection.cursor()`)
3. A short note on which one would ship to production and why
