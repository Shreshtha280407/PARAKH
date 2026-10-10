# Declaration → NOS → PC → task traceability map — CON/Q0602 v4.0, match-rules@r3

The human-readable form of the machine-readable mapping in
`packs/ae-con-q0602/mapping/links.json`. Every row is one
`declaration item → NOS → PC` link; `tools/pack_validate.py`'s `[match]`
check and `tools/audit_qp_traceability.py`'s `[refs]`/`[decl]`/`[contract]`
checks enforce this mechanically (every card/tool links to ≥1 real PC;
every scored NOS has ≥1 linked card/tool; exactly 20 cards + 6 tools, no
link to CON/N8001/CON/N8002) — this file is derived from, not a separate
source for, that data. Regenerate the table below with:

```
python3 -c "
import json
links = json.load(open('packs/ae-con-q0602/mapping/links.json'))
tasks = json.load(open('packs/ae-con-q0602/tasks.json'))
thresholds = json.load(open('packs/ae-con-q0602/mapping/thresholds.json'))
nos_task = {t['nos']: t['id'] for t in tasks['tasks']}
scored = {e['nos'] for e in thresholds['practical_nos_for_matching']}
for group, reason in (('cards','DECLARED_EXPERIENCE'), ('tools','DECLARED_TOOL_USE')):
    for item in links[group]:
        for link in item['links']:
            nos = link['nos']; task = nos_task.get(nos, '—')
            scope = 'SCORED' if nos in scored else 'UNSCORED'
            print(item['id'], item['label'], nos, link['pc'], task, link['weight'], reason, scope)
"
```

**Reason codes:** `DECLARED_EXPERIENCE` (a picture/behaviour card the worker
taps often/sometimes/never) and `DECLARED_TOOL_USE` (an item in the 6-tool
grid). Both feed the same `effective_claim(pc) = answer_strength × weight`
formula (`matcher.py`).

**Scope:** `SCORED` — the item's NOS is in `thresholds.json`'s
`practical_nos_for_matching` and moves `overall_coverage`/`match_result`.
At r3 every one of the 20 cards + 6 tools links only to a `SCORED` NOS by
design — `[contract]` in `tools/audit_qp_traceability.py` fails the build
if any link ever reaches CON/N8001 (teamwork) or CON/N8002 (plan &
organise) again. Those two NOS, and the `declaration_only_nos`/
`declaration_only_signals` mechanism that used to surface them
informationally at r2, were removed entirely in the r2→r3 reduction — they
have no declaration representation of any kind at r3 (see
`docs/gates/Q1.md`'s r2→r3 section). The worker-facing, explicitly
**non-scored** work-setting/prior-training fields in the Android app
(`docs/gates/P3.md`) are a UI-only replacement, never read by the matcher
and never linked to a PC.

## Coverage guarantee

- Every practical, task-evidenced NOS that needs worker-declaration evidence
  (CON/N0602, CON/N0603, CON/N0604, CON/N0605, CON/N9001) has ≥1 linked
  declaration item — mechanically enforced by `[decl]` in
  `tools/audit_qp_traceability.py`.
- Every declaration item links to ≥1 real PC — mechanically enforced by
  `[match]` in `tools/pack_validate.py` and `[refs]` in
  `tools/audit_qp_traceability.py`.
- Every task T1-T5 maps to ≥1 PC (and therefore ≥1 NOS) — `tasks.json`'s
  `linked_pcs`; `[links]` in `tools/pack_validate.py` additionally requires
  every practical PC be evidenced by ≥1 task.
- PCs not linked by any declaration item are listed, with a reason, in
  `links.json.known_gaps` — never silently treated as "no experience"; they
  are simply unprobed by self-declaration and can only be judged from T1-T5
  task evidence at assessment time. The r2→r3 reduction (51 items → 20
  cards + 6 tools) necessarily leaves more PCs unprobed than r2 did; this
  is the accepted trade-off of a short, worker-friendly declaration, not an
  oversight — every scored NOS still has multiple linked cards.

## Old-id → new-id mapping (r2 → r3)

The 20 surviving cards and the first 4 surviving tools are carried forward
from r2's 51-item set under new ids (safety cards folded in, teamwork/
plan-and-organise cards dropped entirely, several tools/duplicative cards
dropped). `TL06` (tong tester / clamp meter) is new at r3, with no r2
predecessor.

| r3 id | r2 id | Label |
|---|---|---|
| `C01` | `C01` | Fixed a loose wire or switch at home/site |
| `C02` | `C02` | Used a tester or multimeter to check if a wire has power |
| `C03` | `C12` | Used hand tools (pliers, screwdriver, wire stripper) for wiring work |
| `C04` | `C09` | Found and fixed a short circuit or no-power fault |
| `C05` | `C21` | Selected an MCB/breaker of the right rating for a circuit |
| `C06` | `C04` | Fitted a new light point or tube light |
| `C07` | `C06` | Fixed an MCB or fuse that had tripped/blown |
| `C08` | `C16` | Shifted or moved a temporary light/board to another spot |
| `C09` | `C19` | Worked with isolated/switched-off power before touching wires |
| `C10` | `C03` | Laid or ran a wire/conduit through a wall or ceiling |
| `C11` | `C05` | Connected a switch and socket |
| `C12` | `C08` | Connected an earth wire |
| `C13` | `C14` | Read a wiring diagram or connection chart |
| `C14` | `C07` | Assembled or wired a small distribution board / meter board |
| `C15` | `C20` | Inspected a panel/board for damage or wear |
| `C16` | `C25` | Mounted/secured a distribution board so it's protected from water, dust or damage |
| `C17` | `S01` | Wore full PPE (helmet, gloves, goggles, safety shoes) for the job |
| `C18` | `S03` | Took part in a safety briefing or Tool Box Talk before starting work |
| `C19` | `S04` | Knew the evacuation/emergency procedure for fire or accident at the site |
| `C20` | `S08` | Checked safety equipment (first-aid box, barricades, fire point) before starting work |
| `TL01` | `TL01` | Multimeter |
| `TL02` | `TL02` | Line tester / voltage tester |
| `TL03` | `TL03` | Wire stripper/cutter |
| `TL04` | `TL04` | Combination pliers |
| `TL05` | `TL06` | Hand/power drill |
| `TL06` | *(new)* | Tong tester (clamp meter) |

Dropped entirely at r3 (no successor): r2 cards `C10`, `C11`, `C13`, `C15`,
`C17`, `C18`, `C22`-`C27`, all of `S02`, `S05`-`S07`, all of `TM01`-`TM04`
and `PL01`-`PL04`; r2 tools `TL05` (insulated screwdriver), `TL07` (conduit
bender), `TL08` (megger/earth tester).

## Full map (59 links, 26 declaration items — 20 cards + 6 tools)

| Declaration item | NOS | PC | Task | Weight | Reason code | Scope |
|---|---|---|---|---:|---|---|
| `C01` Fixed a loose wire or switch at home/site | CON/N0602 | PC2 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C01` Fixed a loose wire or switch at home/site | CON/N0602 | PC6 | T2 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C01` Fixed a loose wire or switch at home/site | CON/N0604 | PC9 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0602 | PC8 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0602 | PC10 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0603 | PC13 | T4 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0604 | PC10 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C03` Used hand tools (pliers, screwdriver, wire stripper) for wiring work | CON/N0602 | PC2 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C03` Used hand tools (pliers, screwdriver, wire stripper) for wiring work | CON/N0602 | PC5 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C03` Used hand tools (pliers, screwdriver, wire stripper) for wiring work | CON/N0602 | PC7 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C04` Found and fixed a short circuit or no-power fault | CON/N0602 | PC3 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C04` Found and fixed a short circuit or no-power fault | CON/N0603 | PC13 | T4 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C04` Found and fixed a short circuit or no-power fault | CON/N0605 | PC12 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C05` Selected an MCB/breaker of the right rating for a circuit | CON/N0602 | PC9 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C05` Selected an MCB/breaker of the right rating for a circuit | CON/N0605 | PC2 | T5 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C06` Fitted a new light point or tube light | CON/N0603 | PC1 | T4 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C06` Fitted a new light point or tube light | CON/N0603 | PC3 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C06` Fitted a new light point or tube light | CON/N0603 | PC4 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C07` Fixed an MCB or fuse that had tripped/blown | CON/N0605 | PC14 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C07` Fixed an MCB or fuse that had tripped/blown | CON/N0603 | PC15 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C08` Shifted or moved a temporary light/board to another spot | CON/N0603 | PC10 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C08` Shifted or moved a temporary light/board to another spot | CON/N0605 | PC16 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C09` Worked with isolated/switched-off power before touching wires | CON/N0603 | PC7 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C09` Worked with isolated/switched-off power before touching wires | CON/N0605 | PC3 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C09` Worked with isolated/switched-off power before touching wires | CON/N0605 | PC10 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C10` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC3 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C10` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC4 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C10` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC5 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C10` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC6 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C10` Laid or ran a wire/conduit through a wall or ceiling | CON/N0603 | PC2 | T4 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C11` Connected a switch and socket | CON/N0604 | PC1 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C11` Connected a switch and socket | CON/N0604 | PC2 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C11` Connected a switch and socket | CON/N0604 | PC8 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C11` Connected a switch and socket | CON/N0604 | PC9 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C12` Connected an earth wire | CON/N0605 | PC7 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C12` Connected an earth wire | CON/N0604 | PC11 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C13` Read a wiring diagram or connection chart | CON/N0604 | PC2 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C13` Read a wiring diagram or connection chart | CON/N0605 | PC1 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C14` Assembled or wired a small distribution board / meter board | CON/N0605 | PC1 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C14` Assembled or wired a small distribution board / meter board | CON/N0605 | PC2 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C14` Assembled or wired a small distribution board / meter board | CON/N0605 | PC4 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C14` Assembled or wired a small distribution board / meter board | CON/N0605 | PC6 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C15` Inspected a panel/board for damage or wear | CON/N0605 | PC9 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C15` Inspected a panel/board for damage or wear | CON/N0605 | PC11 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C16` Mounted/secured a distribution board so it's protected from water, dust or damage | CON/N0605 | PC5 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C17` Wore full PPE (helmet, gloves, goggles, safety shoes) for the job | CON/N9001 | PC7 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C18` Took part in a safety briefing or Tool Box Talk before starting work | CON/N9001 | PC4 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C19` Knew the evacuation/emergency procedure for fire or accident at the site | CON/N9001 | PC2 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C20` Checked safety equipment (first-aid box, barricades, fire point) before starting work | CON/N9001 | PC10 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C20` Checked safety equipment (first-aid box, barricades, fire point) before starting work | CON/N9001 | PC11 | T1 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `TL01` Multimeter | CON/N0602 | PC8 | T2 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL01` Multimeter | CON/N0602 | PC10 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL02` Line tester / voltage tester | CON/N0602 | PC8 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL02` Line tester / voltage tester | CON/N0603 | PC13 | T4 | 0.6 | DECLARED_TOOL_USE | SCORED |
| `TL03` Wire stripper/cutter | CON/N0602 | PC6 | T2 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL04` Combination pliers | CON/N0602 | PC2 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL05` Hand/power drill | CON/N0604 | PC7 | T3 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL06` Tong tester (clamp meter) | CON/N0602 | PC8 | T2 | 0.6 | DECLARED_TOOL_USE | SCORED |
| `TL06` Tong tester (clamp meter) | CON/N0602 | PC10 | T2 | 0.6 | DECLARED_TOOL_USE | SCORED |

59 declaration→NOS/PC links total across 26 declaration items (20 cards +
6 tools), all `SCORED` — no `UNSCORED`/`DECLARATION_ONLY` rows exist at r3.
