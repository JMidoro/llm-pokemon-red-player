# Pokemon Red Progression Chapters

Status: draft
Last updated: 2026-06-29

This document defines a chapter-shaped progression model for building scenario capsules. It is intended to support the LLM Director architecture: each chapter should eventually have a small set of valid starts, chapter-specific skills, success/failure classifiers, and story-flag/soft-lock invariants.

## Sources

- Data Crystal RAM map: https://datacrystal.tcrf.net/wiki/Pok%C3%A9mon_Red_and_Blue/RAM_map
- PRET `pokered` event constants: https://raw.githubusercontent.com/pret/pokered/master/constants/event_constants.asm
- Local state model: `src/pokemon_player/memory_map.py`
- Local capsule spec: `research/capsules/viridian_forest_catching.json`

Data Crystal is the current public anchor for broad WRAM addresses. PRET is the better anchor for symbolic event names. When a chapter depends on a PRET event constant without an already-promoted byte/bit mapping in this repo, treat it as a promotion candidate rather than a trusted runtime fact.

## Address Anchors

These are the most relevant story/progression surfaces for chapter capsules.

| Surface | Address or range | Current confidence | Notes |
| --- | --- | --- | --- |
| Party count/species/structs | `D163`, `D164-D169`, `D16B+` | promoted locally | Required for starter, party wipe, catch success, battle readiness. |
| Inventory | `D31D-D346` local, Data Crystal lists item inventory in WRAM | promoted locally | Required for parcel, Poke Ball, Potion, key-item checks. |
| Money | `D347-D349` | promoted locally | Required for mart/purchase capsules. |
| Badges | `D356` | promoted locally | Bitfield used for gym chapter success. |
| Current map / player position | `D35E`, `D361`, `D362` | promoted locally | Required for all navigation chapters. |
| Battle type | `D057` | promoted locally | Required for battle/dialogue gating. |
| Menu cursor and menu memory | `CC24-CC2D` | promoted locally for several menus | Required for cursor-aware executors. |
| Missable object flags | `D5A6-D5C5` | unpromoted for chapters | Data Crystal calls these flags for disappearing sprites and objects. Includes starter balls/object disappearance surfaces. |
| Starters back? | `D5AB` | unpromoted | Data Crystal names this directly. Use with starter/lab-state promotions. |
| Have Town Map? | `D5F3` | unpromoted | Useful optional route, not required for MVP progression. |
| Early story event flags | `D747+` local `wEventFlags` bitfield | promoted locally for starter/rival/Pokedex/parcel/Brock facts | PRET symbolic constants mapped through `wEventFlags`; preferred for chapter disambiguation. |
| Have Oak's Parcel? | `D60D` | demoted candidate | Looked relevant from Data Crystal, but local states did not distinguish holding the parcel from already-returned parcel. |
| Fought Brock? | `D755` | unpromoted | Data Crystal names this directly. Cross-check with Boulder Badge and TM34. |
| Fought Misty? | `D75E` | unpromoted | Useful for later Cerulean capsule. |
| Wild encounter table | `D887+` | unpromoted | Useful for route/capsule encounter expectations. |

## Chapter Tooling Notes

- Prologue clean boot is represented in local runner tooling with `scripts/run_local_gemma_chapter.py --fresh-start`.
- `complete_prologue` owns title menu navigation, Oak intro dialogue, player/rival name entry, and the Red's House 2F landing.
- The default prologue handoff is `pallet_outside`, which saves intermediate `red_house_2f.state` / `red_house_2f.png` evidence and then uses Pallet navigation to exit Red's house at Pallet Town `map=0x00,x=5,y=6`.
- The clean-boot WRAM snapshot is not semantically meaningful until the intro completes; use screenshots and the final handoff state as the trusted evidence.

## Chapter-Relevant Story Flags

The following are chapter-relevant symbolic flags from PRET plus directly named Data Crystal addresses where available.

### Intro and Pallet

| Story fact | Source | Trust level | Capsule use |
| --- | --- | --- | --- |
| Clean title/new-game prologue | local screenshot plus clean SRAM boot | local tooling scaffolded | Prologue starts from `--fresh-start`; no gameplay WRAM is trusted before handoff. |
| Intro/new game complete enough to control player | local mode/map/player state | promoted by state inspection | Prologue/Chapter 1 exit condition. |
| `EVENT_OAK_APPEARED_IN_PALLET` | PRET | promotion needed | Confirms the long-grass trigger has fired. |
| `EVENT_FOLLOWED_OAK_INTO_LAB` / `EVENT_FOLLOWED_OAK_INTO_LAB_2` | PRET | promotion needed | Confirms the forced Oak escort happened. |
| `EVENT_OAK_ASKED_TO_CHOOSE_MON` | PRET | promotion needed | Confirms starter choice surface is active/available. |
| `EVENT_GOT_STARTER` | PRET + local `wEventFlags` | promoted read-only | Safer if cross-checked with party count/species. |
| `D5AB` Starters Back? | Data Crystal | promotion needed | Starter object/lab visual consistency. |
| `EVENT_BATTLED_RIVAL_IN_OAKS_LAB` | PRET + local `wEventFlags` | promoted read-only | Chapter 2 battle completion. |
| `EVENT_GOT_POKEDEX` | PRET + local `wEventFlags` | promoted read-only | Chapter 4 exit condition and Chapter 5 handoff. |
| `EVENT_GOT_POKEBALLS_FROM_OAK` | PRET + local `wEventFlags` | promoted read-only | Chapter 4/5 supporting signal. |
| `EVENT_PALLET_AFTER_GETTING_POKEBALLS_2` | PRET + local `wEventFlags` | promoted read-only | Useful for post-errand Pallet state. |

### Viridian Parcel Loop

| Story fact | Source | Trust level | Capsule use |
| --- | --- | --- | --- |
| `EVENT_GOT_OAKS_PARCEL` | PRET + local `wEventFlags` | promoted read-only | Viridian Mart parcel pickup. |
| `EVENT_OAK_GOT_PARCEL` | PRET + local `wEventFlags` | promoted read-only | Parcel returned to Oak; preferred Chapter 4/5 discriminator. |
| `D60D` Have Oak's Parcel? | Data Crystal | demoted candidate | Did not cleanly separate held parcel from returned parcel in local before/after states. |
| Poke Balls purchasable in Viridian Mart | inventory/mart state + story flags | promotion needed | Chapter 5 success is best checked by inventory count after purchase. |

### Route 1, Viridian, Route 2, Forest

| Story fact | Source | Trust level | Capsule use |
| --- | --- | --- | --- |
| `EVENT_GOT_POTION_SAMPLE` | PRET | optional promotion | Route 1 NPC item pickup, not capsule-critical. |
| Viridian Forest trainer flags `EVENT_BEAT_VIRIDIAN_FOREST_TRAINER_0..2` | PRET | promotion needed | Prevents navigation planner from treating already-cleared trainer lines as blockers. |
| Encounter surface in Viridian Forest | local map/grass/wild encounter data | partially promoted | Capsule A depends on this more than story flags. |

### Pewter and Brock

| Story fact | Source | Trust level | Capsule use |
| --- | --- | --- | --- |
| `EVENT_BEAT_PEWTER_GYM_TRAINER_0` | PRET | promotion needed | Optional pre-Brock gym trainer route. |
| `EVENT_BEAT_BROCK` | PRET + local `wEventFlags` | promoted read-only | Brock battle completion; should still cross-check with badge/TM. |
| `D755` Fought Brock? | Data Crystal | supporting anchor | Same event byte family as the PRET-mapped flag; cross-check with badge/TM. |
| Boulder Badge bit in `D356` | local/Data Crystal | promoted locally | Strong chapter success signal. |
| `EVENT_GOT_TM34` | PRET | promotion needed | Good post-Brock reward consistency check. |

### Next Natural Chapters

| Story fact | Source | Trust level | Capsule use |
| --- | --- | --- | --- |
| Route 3 trainer flags `EVENT_BEAT_ROUTE_3_TRAINER_0..7` | PRET | promotion needed | Required for Route 3 traversal capsules. |
| Mt. Moon trainer/fossil flags | PRET | promotion needed | Required for Mt. Moon capsules. |
| `EVENT_GOT_DOME_FOSSIL` / `EVENT_GOT_HELIX_FOSSIL` | PRET | promotion needed | Mt. Moon exit consistency. |
| `EVENT_BEAT_MISTY`, `D75E` Fought Misty? | PRET/Data Crystal | promotion needed | Cerulean capsule success cross-check with Cascade Badge. |

## Soft-Lock and Invariant Checklist

These are not all impossible states. Many are "usable but dangerous" states where the Director must plan recovery or the capsule should reject the start.

| Risk | Detection surface | Why it matters |
| --- | --- | --- |
| No conscious Pokemon | party HP/status | Hard fail for most travel/battle capsules; blackout likely or already in progress. |
| No starter but post-starter flags set | party + `EVENT_GOT_STARTER` candidate | Breaks early-game assumptions and rival/lab flow. |
| Starter present but Oak/lab flags inconsistent | party + Pallet PRET flags | Can strand the player in lab/Pallet scripts or skip required dialogue. |
| Parcel mismatch: has parcel item/flag but Oak already received parcel | inventory + `D60D` + `EVENT_OAK_GOT_PARCEL` | Can confuse Chapter 3/4 success and Mart/Oak scripts. |
| Parcel returned but Pokedex/Poke Balls not granted | `EVENT_OAK_GOT_PARCEL` + `EVENT_GOT_POKEDEX` + inventory | Blocks normal catching progression and Chapter 5 assumptions. |
| No Poke Balls in catching capsule | inventory | Not a soft lock globally, but a Capsule A blocker unless money/mart route is in scope. |
| No money and no Poke Balls before catching objective | money + inventory | Catching objective may be impossible without alternate item pickup. |
| Outside allowed capsule region | map/position | Prevents bounded route planner from reasoning safely. |
| Trainer line-of-sight uncleared on required route | trainer flags + local trainer encounter detection | Not a failure; route planner must treat first encounter tile as a valid destination. |
| Required trainer already defeated but overworld sprite/encounter still appears | trainer flags + missable object/sprite state | Indicates story/object flag inconsistency; route behavior may be surprising. |
| Gym badge set but leader-not-fought or TM missing | `D356` + leader flag + TM flag/item | Capsule success may be falsely reported. |
| Leader fought but badge not set | leader flag + `D356` | Can break later badge gates and success checks. |
| Pokedex owned/seen mismatch for capture success | Pokedex owned + party/box | For capsule success, owned is better than party if party may be full. PC box support is a later promotion. |
| Full party catch transfers to box | party count + Pokedex owned + PC box unpromoted | Capture success should not rely only on party delta once full-party starts are in scope. |
| Stuck in menu/dialogue not covered by skills | mode/UI classifier + screenshot | Should become either `advance_dialogue`, `resolve_battle_outcome`, or literal-button recovery evidence. |
| Poisoned/low HP far from heal | party status/HP + location | Not an invalid state, but can turn travel capsules into unavoidable blackout without healing route. |
| Save-state starts mid-script | mode, sprite movement, music, dialogue classifier | Pathing and skill gating may misread transient forced movement or trainer approach. |

## Chapter Plan

Each chapter should define: valid starts, allowed maps, required skills, success flags, failure/abort conditions, and soft-lock checks. Early chapters should be narrow and heavily state-driven; later chapters can reuse shared battle/navigation/dialogue bundles.

### Chapter 1: Intro Dialogue

Objective: progress from boot/new-game intro into controllable gameplay.

Valid starts:
- Boot or intro states.
- Player naming/rival naming states once naming skills exist.

Success:
- Controllable player in Pallet Town/player's room/house.
- Map and position inspectable.

Primary skills:
- `advance_dialogue`
- naming entry skills if starting before player/rival naming is complete.

Soft-lock checks:
- Wrong text entry surface.
- New-game state cannot reach controllable mode within frame/button budget.

### Chapter 2: Leave Home, Trigger Oak, Select Starter, Complete First Rival Battle

Objective: leave home, approach long grass, be escorted to Oak's Lab, select starter, and defeat/resolve first rival battle.

Valid starts:
- Pallet house/bedroom/overworld before starter.
- Pallet overworld before Oak long-grass trigger.
- Oak's Lab before starter choice.

Success:
- Party has exactly one starter or more.
- First rival battle resolved.
- Controllable Pallet/Oak's Lab state after battle.

Candidate flags:
- `EVENT_OAK_APPEARED_IN_PALLET`
- `EVENT_FOLLOWED_OAK_INTO_LAB`
- `EVENT_OAK_ASKED_TO_CHOOSE_MON`
- `EVENT_GOT_STARTER`
- `EVENT_BATTLED_RIVAL_IN_OAKS_LAB`

Primary skills:
- local navigation in Pallet/home/lab.
- choose starter.
- battle action bundle.
- resolve battle outcome dialogue.

Soft-lock checks:
- Party has no conscious Pokemon after battle.
- Starter flags do not match party.
- Rival battle unresolved but player is outside lab.

### Chapter 3: Walk to Viridian City and Retrieve Oak's Parcel

Objective: travel from Pallet/Route 1 to Viridian Mart and receive Oak's Parcel.

Valid starts:
- Post-rival Pallet/Oak's Lab.
- Route 1.
- Viridian City before parcel.

Success:
- Oak's Parcel is present by direct key-item/flag check.
- Player remains inspectable and recoverable.

Candidate flags:
- `EVENT_GOT_OAKS_PARCEL`
- `D60D` Have Oak's Parcel?

Primary skills:
- navigate Pallet/Route 1/Viridian.
- enter Viridian Mart.
- advance dialogue.
- recover to overworld.

Soft-lock checks:
- Parcel already returned.
- No starter/conscious Pokemon.
- Route 1 wild battle handling missing for chosen start.

### Chapter 4: Return Parcel to Professor Oak

Objective: bring Oak's Parcel back to Oak and receive the Pokedex/normal post-parcel progression.

Valid starts:
- Viridian City/Mart with parcel.
- Route 1 with parcel.
- Pallet with parcel.

Success:
- Parcel no longer active.
- Oak received parcel.
- Pokedex acquired.
- Post-parcel Pallet/Lab state is stable.

Candidate flags:
- `EVENT_OAK_GOT_PARCEL`
- `EVENT_GOT_POKEDEX`
- `EVENT_GOT_POKEBALLS_FROM_OAK`
- `EVENT_PALLET_AFTER_GETTING_POKEBALLS`

Primary skills:
- route Viridian/Route 1/Pallet/Oak's Lab.
- advance dialogue.
- handle forced dialogue sequences.

Soft-lock checks:
- Parcel flag/item missing.
- Pokedex missing after parcel-return dialogue completes.
- Post-parcel flags set but inventory/story state says parcel still present.

### Chapter 5: Return to Viridian City, Purchase First Poke Balls, and Catch Route 22 Spearow

Objective: reach Viridian Mart after parcel loop, buy enough Poke Balls, then catch a Spearow on accessible Route 22 before entering Viridian Forest.

Valid starts:
- Pallet/Oak's Lab after parcel return.
- Route 1/Viridian after parcel return.

Success:
- Inventory contains Poke Balls after purchase.
- Spearow is caught from accessible Route 22.
- Player can return to overworld in Viridian City/Route 2 or continue toward Viridian Forest.

Candidate flags:
- `EVENT_GOT_POKEDEX`
- `EVENT_GOT_POKEBALLS_FROM_OAK`
- inventory Poke Ball count.
- party contains Spearow.

Primary skills:
- navigate to Viridian Mart.
- buy item.
- menu/cursor-aware quantity selection.
- recover to overworld.
- enter approved Route 22 grass/search surface.
- attempt catch.

Soft-lock checks:
- Insufficient money.
- Mart dialogue/item menu not supported.
- Inventory full.

### Chapter 6: Viridian Forest

Objective: enter Viridian Forest, catch Pikachu specifically, and navigate through the forest to the north exit.

Current capsule:
- `viridian_forest_catching`

Success for catching capsule:
- Pikachu caught.
- Viridian Forest north exit/north gate reached after Pikachu is caught.
- No blackout.
- Final state stable and inspectable.

Candidate flags:
- Viridian Forest trainer flags `EVENT_BEAT_VIRIDIAN_FOREST_TRAINER_0..2`
- Pokedex owned for caught target.
- Party delta, with PC box caveat for full party starts.

Primary skills:
- `navigate_within_viridian_forest_region`
- `enter_grass_search_loop`
- `advance_battle_dialogue`
- `use_move`
- `attempt_catch`
- `handle_nickname_prompt`
- `enter_nickname_text`
- `resolve_battle_outcome_dialogue_bundle`
- `recover_to_overworld`

Soft-lock checks:
- No Poke Balls.
- Low HP/no healing.
- Trainer encounter while pathing should be treated as a valid route event, not a failed path.
- Full party catch success needs Pokedex owned until PC box inspection is promoted.

### Chapter 7: Pewter City and Brock Fight

Objective: reach Pewter City, enter gym, defeat Brock, and end in stable post-Brock state.

Valid starts:
- Viridian Forest north exit.
- Pewter City.
- Pewter Gym before trainer/Brock.

Success:
- Boulder Badge bit set in `D356`.
- Brock defeated flag set once promoted.
- Post-battle dialogue resolved.

Candidate flags:
- `EVENT_BEAT_PEWTER_GYM_TRAINER_0`
- `EVENT_BEAT_BROCK`
- `D755` Fought Brock?
- `EVENT_GOT_TM34`
- Boulder Badge bit in `D356`

Primary skills:
- `navigate_within_pewter_region`
- battle action bundle.
- use move/switch/item.
- heal at PokeCenter.
- resolve battle outcome dialogue.

Soft-lock checks:
- Party underleveled/low HP and no healing route.
- Gym guide forced movement state.
- Badge flag and defeated flag disagree.

### Chapter 8: Route 3 and Mt. Moon Approach

Objective: leave Pewter, clear or route through Route 3, and reach the Mt. Moon PokeCenter.

Valid starts:
- Post-Brock Pewter.
- Route 3.

Success:
- Stable Mt. Moon PokeCenter or Mt. Moon entrance state.

Candidate flags:
- Route 3 trainer flags `EVENT_BEAT_ROUTE_3_TRAINER_0..7`
- `EVENT_BOUGHT_MAGIKARP` optional.

Primary skills:
- expanded route navigation.
- trainer battle handling.
- heal at PokeCenter.

Soft-lock checks:
- Trainer gauntlet cannot be bypassed without battle support.
- Low PP/HP without healing.

### Chapter 9: Mt. Moon and Fossil Choice

Objective: traverse Mt. Moon, defeat required Rocket/Super Nerd encounters, choose a fossil, and exit to Route 4.

Valid starts:
- Mt. Moon PokeCenter.
- Mt. Moon interior starts.

Success:
- Route 4 post-Mt. Moon stable state.
- One fossil acquired.

Candidate flags:
- Mt. Moon trainer flags.
- `EVENT_BEAT_MT_MOON_EXIT_SUPER_NERD`
- `EVENT_GOT_DOME_FOSSIL`
- `EVENT_GOT_HELIX_FOSSIL`

Primary skills:
- cave navigation.
- trainer battle bundle.
- item pickup/choice dialogue.

Soft-lock checks:
- Wrong fossil state or both fossil flags set.
- Escape Rope/exit assumptions if route fails.

### Chapter 10: Cerulean City and Misty

Objective: reach Cerulean, handle rival/gym prerequisites as scoped, defeat Misty.

Current capsule:
- `cerulean_misty`

Success:
- Cascade Badge bit set.
- Misty defeated flag set once promoted.

Candidate flags:
- `EVENT_BEAT_CERULEAN_RIVAL`
- `EVENT_BEAT_CERULEAN_GYM_TRAINER_0`
- `EVENT_BEAT_CERULEAN_GYM_TRAINER_1`
- `EVENT_BEAT_MISTY`
- `D75E` Fought Misty?
- `EVENT_GOT_TM11`

Primary skills:
- Cerulean navigation.
- gym navigation.
- battle action bundle.
- heal at PokeCenter.

Soft-lock checks:
- Nugget Bridge/rival gates depending on chosen capsule scope.
- Cascade Badge and defeated flag disagreement.

## Promotion Backlog

Highest priority promotions for chapter capsules:

1. Parcel contract: inventory item behavior plus promoted `EVENT_GOT_OAKS_PARCEL` / `EVENT_OAK_GOT_PARCEL`; keep `D60D` demoted unless future evidence explains it cleanly.
2. Oak Lab/starter contract: starter choice flags, starter object/missable object flags, party cross-check.
3. Pokedex/Poke Ball post-parcel contract: promoted `EVENT_GOT_POKEDEX`, `EVENT_GOT_POKEBALLS_FROM_OAK`, post-parcel Pallet flags.
4. Gym leader completion contract: badge bit + leader defeated flag + reward TM for Brock and Misty.
5. Trainer encounter completion contract: Viridian Forest, Route 3, gym trainer flags.
6. Mart purchase contract: mart UI, item selection, quantity, money delta, inventory delta.
7. Full-party capture contract: Pokedex owned + PC box contents.
