# Declaration → NOS → PC → task traceability map — CON/Q0602 v4.0, match-rules@r2

The human-readable form of the machine-readable mapping in
`packs/ae-con-q0602/mapping/links.json`. Every row is one
`declaration item → NOS → PC` link; `tools/pack_validate.py`'s `[match]`
check and `tools/audit_qp_traceability.py`'s `[refs]`/`[decl]` checks
enforce this mechanically (every card/tool links to ≥1 real PC; every
scored NOS has ≥1 linked card/tool) — this file is derived from, not a
separate source for, that data. Regenerate the table below with:

```
python3 -c "
import json
links = json.load(open('packs/ae-con-q0602/mapping/links.json'))
tasks = json.load(open('packs/ae-con-q0602/tasks.json'))
thresholds = json.load(open('packs/ae-con-q0602/mapping/thresholds.json'))
nos_task = {t['nos']: t['id'] for t in tasks['tasks']}
scored = {e['nos'] for e in thresholds['practical_nos_for_matching']}
decl_only = {e['nos'] for e in thresholds['declaration_only_nos']}
for group, reason in (('cards','DECLARED_EXPERIENCE'), ('tools','DECLARED_TOOL_USE')):
    for item in links[group]:
        for link in item['links']:
            nos = link['nos']; task = nos_task.get(nos, '—')
            scope = 'SCORED' if nos in scored else 'DECLARATION_ONLY' if nos in decl_only else 'UNSCORED'
            print(item['id'], item['label'], nos, link['pc'], task, link['weight'], reason, scope)
"
```

**Reason codes:** `DECLARED_EXPERIENCE` (a picture/behaviour card the worker
taps often/sometimes/never) and `DECLARED_TOOL_USE` (an item in the tool
grid). Both feed the same `effective_claim(pc) = answer_strength × weight`
formula (`matcher.py`).

**Scope:** `SCORED` — the item's NOS is in `thresholds.json`'s
`practical_nos_for_matching` and moves `overall_coverage`/`match_result`.
`DECLARATION_ONLY` — the item's NOS (CON/N8001 teamwork, CON/N8002 plan &
organise) is in `declaration_only_nos`: linked and surfaced to the worker
and assessor, but never scored (see `matcher.py`'s `declaration_only_signals`
and `test_matcher.py::test_declaration_only_signals_never_move_the_score`).

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
  task evidence at assessment time.

## Full map (104 links, 51 declaration items)

| Declaration item | NOS | PC | Task | Weight | Reason code | Scope |
|---|---|---|---|---:|---|---|
| `C01` Fixed a loose wire or switch at home/site | CON/N0602 | PC2 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C01` Fixed a loose wire or switch at home/site | CON/N0602 | PC6 | T2 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C01` Fixed a loose wire or switch at home/site | CON/N0604 | PC9 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0602 | PC8 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0602 | PC10 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0603 | PC13 | T4 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C02` Used a tester or multimeter to check if a wire has power | CON/N0604 | PC10 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C03` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC3 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C03` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC4 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C03` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC5 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C03` Laid or ran a wire/conduit through a wall or ceiling | CON/N0604 | PC6 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C03` Laid or ran a wire/conduit through a wall or ceiling | CON/N0603 | PC2 | T4 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C04` Fitted a new light point or tube light | CON/N0603 | PC1 | T4 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C04` Fitted a new light point or tube light | CON/N0603 | PC3 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C04` Fitted a new light point or tube light | CON/N0603 | PC4 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C05` Connected a switch and socket | CON/N0604 | PC1 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C05` Connected a switch and socket | CON/N0604 | PC2 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C05` Connected a switch and socket | CON/N0604 | PC8 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C05` Connected a switch and socket | CON/N0604 | PC9 | T3 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C06` Fixed an MCB or fuse that had tripped/blown | CON/N0605 | PC14 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C06` Fixed an MCB or fuse that had tripped/blown | CON/N0603 | PC15 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C07` Assembled or wired a small distribution board / meter board | CON/N0605 | PC1 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C07` Assembled or wired a small distribution board / meter board | CON/N0605 | PC2 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C07` Assembled or wired a small distribution board / meter board | CON/N0605 | PC4 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C07` Assembled or wired a small distribution board / meter board | CON/N0605 | PC6 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C08` Connected an earth wire | CON/N0605 | PC7 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C08` Connected an earth wire | CON/N0604 | PC11 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C09` Found and fixed a short circuit or no-power fault | CON/N0602 | PC3 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C09` Found and fixed a short circuit or no-power fault | CON/N0603 | PC13 | T4 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C09` Found and fixed a short circuit or no-power fault | CON/N0605 | PC12 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C10` Replaced a damaged cable or wire | CON/N0603 | PC14 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C10` Replaced a damaged cable or wire | CON/N0605 | PC14 | T5 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C11` Joined/spliced two wires together | CON/N0602 | PC6 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C11` Joined/spliced two wires together | CON/N0603 | PC5 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C12` Used hand tools (pliers, screwdriver, wire stripper) for wiring work | CON/N0602 | PC2 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C12` Used hand tools (pliers, screwdriver, wire stripper) for wiring work | CON/N0602 | PC5 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C12` Used hand tools (pliers, screwdriver, wire stripper) for wiring work | CON/N0602 | PC7 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C13` Used a power tool (drill) for electrical work | CON/N0602 | PC1 | T2 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C13` Used a power tool (drill) for electrical work | CON/N0604 | PC7 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C14` Read a wiring diagram or connection chart | CON/N0604 | PC2 | T3 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C14` Read a wiring diagram or connection chart | CON/N0605 | PC1 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C15` Measured and cut wire/conduit to a required length | CON/N0602 | PC4 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C15` Measured and cut wire/conduit to a required length | CON/N0602 | PC5 | T2 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C15` Measured and cut wire/conduit to a required length | CON/N0604 | PC3 | T3 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C16` Shifted or moved a temporary light/board to another spot | CON/N0603 | PC10 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C16` Shifted or moved a temporary light/board to another spot | CON/N0605 | PC16 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C17` Tagged or marked a live wire/panel as a warning | CON/N0603 | PC9 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C17` Tagged or marked a live wire/panel as a warning | CON/N0605 | PC8 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C18` Cleaned/serviced tools after use | CON/N0602 | PC11 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C18` Cleaned/serviced tools after use | CON/N0603 | PC8 | T4 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C18` Cleaned/serviced tools after use | CON/N9001 | PC8 | T1 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C19` Worked with isolated/switched-off power before touching wires | CON/N0603 | PC7 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C19` Worked with isolated/switched-off power before touching wires | CON/N0605 | PC3 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C19` Worked with isolated/switched-off power before touching wires | CON/N0605 | PC10 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C20` Inspected a panel/board for damage or wear | CON/N0605 | PC9 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C20` Inspected a panel/board for damage or wear | CON/N0605 | PC11 | T5 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `C21` Selected an MCB/breaker of the right rating for a circuit | CON/N0602 | PC9 | T2 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C21` Selected an MCB/breaker of the right rating for a circuit | CON/N0605 | PC2 | T5 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C22` Terminated/connected the ends of an LV cable to a switch, socket or fitting | CON/N0603 | PC6 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C22` Terminated/connected the ends of an LV cable to a switch, socket or fitting | CON/N0604 | PC9 | T3 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `C23` Replaced a burnt-out bulb/tube or light fixture | CON/N0603 | PC12 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C24` Repaired or replaced a damaged light fitting/fixture | CON/N0603 | PC11 | T4 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C25` Mounted/secured a distribution board so it's protected from water, dust or damage | CON/N0605 | PC5 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C26` Told a supervisor/site in-charge before switching off or opening a panel for repair | CON/N0605 | PC13 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `C27` Kept a written note/log of a repair or maintenance job done | CON/N0605 | PC15 | T5 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S01` Wore full PPE (helmet, gloves, goggles, safety shoes) for the job | CON/N9001 | PC7 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S02` Reported a hazard, unsafe condition or near-miss to a supervisor | CON/N9001 | PC1 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S02` Reported a hazard, unsafe condition or near-miss to a supervisor | CON/N9001 | PC6 | T1 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `S03` Took part in a safety briefing or Tool Box Talk before starting work | CON/N9001 | PC4 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S04` Knew the evacuation/emergency procedure for fire or accident at the site | CON/N9001 | PC2 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S05` Used or checked a fire extinguisher | CON/N9001 | PC5 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S06` Segregated and disposed of waste or hazardous material correctly | CON/N9001 | PC9 | T1 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `S06` Segregated and disposed of waste or hazardous material correctly | CON/N9001 | PC13 | T1 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `S07` Followed hygiene/sanitation practice at the workplace (handwashing, clean tools) | CON/N9001 | PC15 | T1 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `S07` Followed hygiene/sanitation practice at the workplace (handwashing, clean tools) | CON/N9001 | PC16 | T1 | 0.8 | DECLARED_EXPERIENCE | SCORED |
| `S08` Checked safety equipment (first-aid box, barricades, fire point) before starting work | CON/N9001 | PC10 | T1 | 1.0 | DECLARED_EXPERIENCE | SCORED |
| `S08` Checked safety equipment (first-aid box, barricades, fire point) before starting work | CON/N9001 | PC11 | T1 | 0.6 | DECLARED_EXPERIENCE | SCORED |
| `TM01` Passed on work instructions or site updates clearly to co-workers | CON/N8001 | PC1 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM01` Passed on work instructions or site updates clearly to co-workers | CON/N8001 | PC5 | — | 0.6 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM02` Told a supervisor about a problem or delay instead of hiding it | CON/N8001 | PC2 | — | 0.8 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM02` Told a supervisor about a problem or delay instead of hiding it | CON/N8001 | PC3 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM03` Worked together with co-workers to finish a task on time | CON/N8001 | PC8 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM03` Worked together with co-workers to finish a task on time | CON/N8001 | PC7 | — | 0.6 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM04` Asked a senior worker or supervisor when unsure how to do something | CON/N8001 | PC4 | — | 0.8 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TM04` Asked a senior worker or supervisor when unsure how to do something | CON/N8001 | PC6 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL01` Checked the day's targets or instructions before starting work | CON/N8002 | PC1 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL01` Checked the day's targets or instructions before starting work | CON/N8002 | PC2 | — | 0.8 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL02` Arranged the tools/materials needed for a task before starting | CON/N8002 | PC7 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL02` Arranged the tools/materials needed for a task before starting | CON/N8002 | PC9 | — | 0.6 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL03` Planned a task so it could be finished within the given time | CON/N8002 | PC3 | — | 0.8 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL03` Planned a task so it could be finished within the given time | CON/N8002 | PC14 | — | 0.8 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL04` Cleaned and organised the work area after finishing a task | CON/N8002 | PC15 | — | 1.0 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `PL04` Cleaned and organised the work area after finishing a task | CON/N8002 | PC11 | — | 0.6 | DECLARED_EXPERIENCE | DECLARATION_ONLY |
| `TL01` Multimeter | CON/N0602 | PC8 | T2 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL01` Multimeter | CON/N0602 | PC10 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL02` Line tester / voltage tester | CON/N0602 | PC8 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL02` Line tester / voltage tester | CON/N0603 | PC13 | T4 | 0.6 | DECLARED_TOOL_USE | SCORED |
| `TL03` Wire stripper/cutter | CON/N0602 | PC6 | T2 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL04` Combination pliers | CON/N0602 | PC2 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL05` Insulated screwdriver set | CON/N0602 | PC2 | T2 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL06` Hand/power drill | CON/N0604 | PC7 | T3 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL07` Conduit bender | CON/N0604 | PC3 | T3 | 0.8 | DECLARED_TOOL_USE | SCORED |
| `TL08` Megger / earth tester | CON/N0602 | PC10 | T2 | 1.0 | DECLARED_TOOL_USE | SCORED |
| `TL08` Megger / earth tester | CON/N0605 | PC7 | T5 | 0.6 | DECLARED_TOOL_USE | SCORED |

104 declaration->NOS/PC links total across 51 declaration items.
