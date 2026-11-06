---
description: Eko_CRM — prowadzi zadanie przez proces Ninefold od Issue do PR
---

# Task: $1

Wykonaj zadanie zgodnie z kanoniczną definicją procesu w
`@.claude/commands/task.md`. Najpierw przeczytaj ten plik w całości oraz
`@TEAM-CONTRACT.md`; są wiążące i mają pierwszeństwo przed tą komendą.

Argumenty użytkownika:

- Issue: `$1`
- Faza opcjonalna: `$2`
- Wszystkie argumenty: `$ARGUMENTS`

W środowisku Kilo role nie są zarejestrowanymi typami subagentów. Stosuj więc
tryb awaryjny opisany w kanonicznej komendzie: użyj agenta ogólnego, dołącz na
początku jego promptu treść odpowiedniej definicji z `agents/<rola>.md` i
wykonaj mechaniczne sprawdzenie granic zapisu wokół każdego wywołania roli.

Nie zmieniaj statusu zadania bez dowodów, nie przekraczaj bramek ludzkich i nie
wykonuj commita, push ani merge poza wyjątkami jednoznacznie dozwolonymi przez
kanoniczną definicję procesu.
