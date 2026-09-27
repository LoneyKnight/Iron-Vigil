# Iron Vigil · Vertical slice: one complete run

> Purpose: prove the **whole loop** runs end to end — spawn, explore, search, fight, find the
> relics, complete the rite, end screen. Not a content milestone: the slice is deliberately
> small, and every system in it is a placeholder for something bigger.
>
> If a decision here would be expensive to undo, it is written down. If it is cheap, it is
> left as a `TODO` in the code rather than designed in a document.

## The run, in order

| # | Step | Player does | Game does | Done when |
|---|---|---|---|---|
| 1 | **Spawn** | — | generates an 8-room chapter house, drops the knight in the entrance | the player can walk out of the first room |
| 2 | **Explore** | WASD + mouse | rooms reveal as doors open; each room is built from the room builder | ≥ 6 rooms reachable |
| 3 | **Open doors** | E near a door | door slides aside, room beyond is revealed | every door opens once |
| 4 | **Search** | E near a chest | loot appears in the HUD; one chest holds a quest relic | both relics can be found |
| 5 | **Fight** | left mouse | a cultist chases and damages; the knight swings | a cultist can be killed |
| 6 | **Collect** | E near a relic | relic goes to the HUD list | HUD shows 2 relics |
| 7 | **Complete the rite** | E at the altar with both relics | the altar lights, the run ends | end screen appears |
| 8 | **End** | — | summary: rooms explored, cultists killed, time taken | the run can be restarted |

## The fiction, in one line

A knight of the order descends into a chapter house where the brethren have turned. Two
relics — the **ritual dagger** and the **tallow of the vigil** — must be carried to the
**altar** and the rite completed before the house finishes waking.

## Scope: what this slice is NOT

Named explicitly because each of these is a real system and none of them belongs here:

- **No networking.** Single player only. The loop has to be fun alone before it is
  replicated, and replication makes every later change more expensive.
- **No inventory.** Relics are two booleans, not items in a bag.
- **No procedural room templates.** One room shape, repeated in a generated layout.
- **No sanity, no sound-as-resource, no betrayal.** Those are the identity systems and they
  need the loop underneath them to be real first.
- **No death penalty.** Health reaches zero, the run ends, that is all.

## Numbers for this slice

| Quantity | Value | Note |
|---|---|---|
| Rooms | **8** | generated as a random walk on a grid, then verified connected |
| Room size | 7 × 7 m | the framing solution; see style_spec.md §2.1 |
| Cultists | **3** | one per 2–3 rooms; wander, chase within 6 m, hit for 12 |
| Chests | **6** | 4 with mundane loot, 2 with a relic |
| Knight | 100 HP, 34 damage per swing | a cultist dies in 3 hits; the knight dies in 9 |
| Target run time | **3–5 minutes** | a full run is the unit of play; 15 minutes was too long |

## The one thing to watch

The loop must be **readable without instructions**: a player who has never seen it should
work out that doors open, chests give things, cultists hurt, and the altar wants what the
chests held. Every one of those is a prompt on screen, and the prompt is not optional
detail — Black Room shipped a polished close-up view and never once told the player how to
open a door, and that is the single cheapest mistake in this whole project to avoid.
