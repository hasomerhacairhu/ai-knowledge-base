# AI Knowledge Base — CustomGPT foglalkozástervező asszisztens

Röviden: ez a repo egy eszközkészlet nonformális ifjúsági foglalkozások tervezéséhez. Minden fő tervezési lépéshez (altéma választás, SMART célok, vázlatkészítés, feedback) készült egy CustomGPT‑instrukció draft, amelyet a madrih‑ok (ifjúsági vezetők) runtime során használhatnak.

Fájlok röviden:
- `CGPT1.md` — Phase 1: altéma‑válogató instrukciók (inputok, kimenet szerkezet, szabályok)
- `CGPT2.md` — Phase 2: SMART cél‑asszisztens instrukciók
- `CGPT3.md` — Phase 3: Foglalkozás‑vázlat asszisztens + beágyazott `Peula sablon`
- `CGPT4.md` — Phase 4: Feedback‑elemző instrukciók
- `Peula sablon.md` — a foglalkozás sablonja (részletes kitöltési útmutató)
- `TODO.md` — teendők, acceptance criteria, következő lépések
- `CGPT1.md`..`CGPT4.md` tartalmaznak prompt‑sablonokat és acceptance critera‑ket.

Használati útmutató (gyors):
1. A madrih indítja a folyamatot runtime‑ban egy CustomGPT‑felületen (vagy más UI) a megfelelő prompt‑sablon használatával.
2. A CustomGPT fájlok elvárják a kötelező mezők runtime‑os megadását (age_group, group_stage, participants_count, stb.). Hiányzó adat esetén a CGPT kérdez vissza röviden.
3. Phase 1 → Phase 2 → Phase 3 iterációk: a madrih válaszol, majd a CGPT3 iterál (2–5 kör) a vázlaton.
4. A foglalkozás megtartása után a madrih a CGPT4‑hez feltölti az observációkat és facilitator jegyzeteket; a CGPT4 akciótervet ad.

Prompt‑sablonok (másold és használd):
- Phase 1 (CGPT1):
  "monthly_theme: <helyőrző vagy a tényleges téma>, age_group: <parparim|kivsza|leviátán|mixed>, group_stage: <Alakulás|Viharzás|Normázás|Működés|Felbomlás>, participants_count: <szám>, location_and_constraints: '<pl. beltéri, nincs futás>', desired_output_detail: 'altémák' — kérlek adj 4 altémát rövid indoklással."
- Phase 2 (CGPT2):
  "monthly_theme: <helyőrző>, selected_altma: '<altéma cím>', age_group: kivsza, group_stage: Normázás, participants_count: 12, session_duration_minutes: 50, madrih_priority: 'készségfejlesztés' — adj 4 SMART célt rövid indoklással és 1 mérőeszközzel célonként."
- Phase 3 (CGPT3):
  "selected_altma: 'Empátia improvizáció', selected_goals: ['Empátia gyakorlása','Kommunikáció fejlesztése'], age_group: kivsza, group_stage: Normázás, participants_count: 12, session_duration_minutes: 50, location_and_constraints: 'beltéri, nincs futás', desired_iterations: 3 — kérlek készíts 2 vázlatvariánst és egy 30 perces kompakt alternatívát."
- Phase 4 (CGPT4):
  "session_title: 'Empátia 2025-10-24', selected_altma: 'Empátia improvizáció', selected_goals: ['Empátia gyakorlása','Kommunikáció fejlesztése'], participants_count: 12, observed_outcomes: '<rövid leírás>', facilitator_notes: '<mi ment jól, mi nem>' — kérlek adj egy 6‑pontos feedback‑összegzést és 3 akciót prioritással."

Acceptance criteria (összefoglalva):
- CGPT1: 3–5 altéma, életkor‑ és dinamikafázis‑kompatibilitás, kérdez vissza hiányzó mezőknél.
- CGPT2: 3–6 SMART cél minden SMART elemre bontva + mérőeszköz.
- CGPT3: legalább 1 teljes vázlat, preferált 2–3 variáns, időbontás egyezik a megadott session_duration‑nal, iterációs diffek.
- CGPT4: 5–8 pontból álló akcióorientált feedback, javaslatok prioritással.

Tesztelés (gyors manuális):
1. Hozz létre 2–3 tesztbemenetet markdownban a `tests/` mappában (példa: parparim, kivsza, leviátán). Minden bemenet tartalmazza a kötelező mezőket.
2. Használj a prompt‑sablonokból egyet, és ellenőrizd a kimenetet az acceptance criteria‑kkel.
3. A CGPT3 esetén futtass 2 iterációt: adj módosítást, és ellenőrizd a diff‑összegzést és a frissített vázlatot.

Javasolt következő lépések:
- Készíts `tests/` mappát 4–6 mintabemenettel és várt kimenettel.
- Automatizált validáció: egyszerű Node/Python script, ami a prompt‑sablonokkal ellenőrzi, hogy a kötelező mezők megvannak-e.
- Készíts egy `MADRIH_MESSAGE.md` fájlt (sablon), amit a madrih‑nak küldhetsz a runtime válaszok begyűjtéséhez.

Fejlesztési megjegyzés: a jelen repo a CGPT‑instrukciók tervezeti szintjét tartalmazza; a működő CustomGPT rendszert (API/GUI) a platformod beállításai szerint kell implementálni.

Licenc: README generált a projekt segítésére; nincs külön licenc fájl a repo‑ban.

Készen állok: ha jóváhagyod, létrehozom a `tests/` mappát és 4 példa bemenetet, illetve a `MADRIH_MESSAGE.md`‑t.
# ai-knowledge-base-ingest
This Python application is designed to process user-uploaded documents and ingest their content into the OpenAI API, effectively building a custom knowledge base. It streamlines the creation of a powerful information source for AI response generation.
