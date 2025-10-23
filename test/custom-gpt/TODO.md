# TODO — ai-knowledge-base-ingest

Projekt cél: minden lépéshez CustomGPT‑ket készíteni, amelyek segítik az ifjúsági vezetőt (madrih) a nonformális foglalkozások tervezésében.

Jelen állapot: Phase‑1 (altéma kiválasztó) draft elkészült a `CGPT1.md` fájlban. Havi téma helyőrzőt használunk addig, amíg a madrih be nem szolgáltatja a tényleges témát.

Fő feladatok (sorrendben):
1. Phase 1 — interjú és finalizálás
   - [x] Draft elkészítése
   - [ ] Madrih megkérdezése: participants_count, age_group, group_stage, location_and_constraints
   - [ ] CGPT1.md finomítása a kapott adatok alapján
   - [ ] Példa outputok készítése (3 példa foglalkozási altéma több korcsoporttal)
   - [ ] Egyszerű validációs teszt: egy példa bemenettel ellenőrizni, hogy a CGPT1 kimenete megfelel-e a minőségcéloknak

   Acceptance criteria (Phase 1):
   - CGPT1 képes 3–5 altémát generálni a megadott mezők alapján.
   - Minden altéma tartalmazza: cím, 1 mondatos indoklás, kulcs_cél, módszer, eszköz, időbecslés.
   - Hiányzó mező esetén a CGPT1 kérdez vissza rövid, célzott kérdéssel.

2. Phase 2 — Célok (CustomGPT és interjú)
   - [ ] Interjú kérdések összeállítása (SMART célokra fókuszálva)
   - [ ] CGPT2.md létrehozása (céljavaslat‑asszisztens)

   Subtasks (Phase 2):
   - Írjunk 6 kérdést, amelyek segítenek SMART célokat kialakítani (megvalósíthatóság, mérhetőség, időhorizont).
   - Készítsünk 3 példát SMART célra különböző korcsoportokhoz.
   - Acceptance criteria: CGPT2 javaslatokat ad, amelyek közül a madrih 1–3‑at kiválaszthat, és azok SMART elemekre bontva is visszakérdezhetők.

3. Phase 3 — Vázlatok / módszertan (CustomGPT és interakció)
   - [ ] Interjú kérdések a bevezető/törzs/lezárás tervezéséhez
   - [ ] Iterációs munkafolyamat definiálása (2–5 iteráció)
   - [ ] CGPT3.md létrehozása (foglalkozás‑vázlat asszisztens)

   Subtasks (Phase 3):
   - Tervezzünk 3 vázlatot minden célra: rövid (45–60 perc), kompakt (30 perc), alternatív (mozgás nélküli változat).
   - Készítsünk iterációs checklistet: megjegyzések gyűjtése, változtatások javaslata, véglegesítés.
   - Acceptance criteria: CGPT3 képes generálni teljes foglalkozás‑vázlatot a `Peula sablon.md` struktúrájára építve.

4. Phase 4 — Feedback (CustomGPT és sablon)
   - [ ] Interjú kérdések a feedback struktúrához
   - [ ] CGPT4.md létrehozása (feedback‑elemző asszisztens)

   Subtasks (Phase 4):
   - Definiáljuk a feedback mezőket (résztvevői élmény, célelérés, logisztika, javaslatok).
   - Készítsünk 2 példa feedback riportot (jó gyakorlat, fejlesztendő pontok).
   - Acceptance criteria: CGPT4 képes összegző visszajelzést adni 5–8 pontban és javaslatot tenni javításokra.

5. Összefűzés és példaanyagok
   - [ ] Összes CGPT‑instrukció exportálása (README + használati példák)
   - [ ] Kész példa foglalkozástervezet a `Peula sablon.md` alapján
   - [ ] Sample feedback riport

   Subtasks (Wrap up):
   - README.md frissítése: hogyan használjuk a CGPT‑ket (gyorsstart és prompt sablonok).
   - Tesztcsomag: 1‑2 input/expected output pár minden CGPT‑hez (markdown formátumban).

Proaktív extra (opcionális):
- [ ] Egy kis automata prompt‑generátor sablon (madrih UI‑hoz)
- [ ] Egyszerű tesztesetek / validációs checklist minden CGPT‑hez

Kérdések a madrih felé (másold ki és küldd el neki):
- Hány résztvevő lesz? (pontos szám vagy tartomány)
- Melyik korcsoport? (parparim / kivsza / leviátán / mixed)
- Milyen csoportdinamika fázisban van a csapat most? (Alakulás / Viharzás / Normázás / Működés / Felbomlás)
- Helyszín és korlátozások (beltéri/szabadtéri, eszközkorlátozások)
- Megadja-e a havi témát most, vagy marad a placeholder?

Fontos megjegyzés: te nem vagy a madrih; a fenti kérdéseket a madrih‑nak kell megválaszolnia. Két lehetőség:
- Te továbbítod a kérdéseket a madrih‑nak, és visszatöltöd ide a válaszokat; vagy
- Megadod itt te a madrih által jóváhagyott válaszokat (én ezt használom a CGPT1 finomításához).

Következő lépés tőlem: megvárom a madrih válaszait a TODO listában szereplő kérdésekre, majd frissítem a `CGPT1.md`‑t és kipipálom a Phase‑1 elemeit.

Megjegyzés: a madrih válaszai alapértelmezés szerint a CustomGPT használatakor (runtime) érkeznek be; a CGPT‑ket úgy tervezzük, hogy hiányzó mező esetén a rendszer/közvetlen interakció során kérdezzenek vissza.

Időbecslés összesen (prototípus szint): 4–6 óra munkával a legfontosabb CGPT‑ek v1‑ének elkészítése (feltételezve gyors visszajelzést a madrih‑tól).

Tesztelési javaslat (gyors):
- Készítsünk egy `tests/` mappát markdown példákkal: `cgpt1_example1.md`, `cgpt1_example2.md` stb. (opcionális)
- Manual run: használd a Prompt‑sablont a `CGPT1.md`‑ből, és ellenőrizd a kimenetet a minőségcélokkal.

