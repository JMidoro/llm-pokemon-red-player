from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChapterGoal:
    chapter_id: str
    title: str
    objective: str
    success: bool
    evidence: tuple[str, ...]
    hints: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapterId": self.chapter_id,
            "title": self.title,
            "objective": self.objective,
            "success": self.success,
            "evidence": list(self.evidence),
            "hints": list(self.hints),
        }


def current_chapter_goal(snapshot: dict[str, Any]) -> ChapterGoal:
    position = snapshot.get("position") if isinstance(snapshot.get("position"), dict) else {}
    map_id = _int_or_default(position.get("map_id"), -1)
    x = _int_or_default(position.get("x"), -1)
    y = _int_or_default(position.get("y"), -1)
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    inventory = snapshot.get("inventory") if isinstance(snapshot.get("inventory"), list) else []
    mode = str(snapshot.get("mode", "unknown"))
    battle_type = int(snapshot.get("battle_type_raw", 0) or 0)
    poke_balls = _poke_ball_count(inventory)
    story_events = _story_event_values(snapshot)
    story_evidence = tuple(
        f"story.{key}={str(value).lower()}"
        for key, value in sorted(story_events.items())
        if key in {"got_pokedex", "got_oaks_parcel", "oak_got_parcel"}
    )

    evidence = (
        f"mode={mode}",
        f"battle_type_raw={battle_type}",
        f"map=0x{map_id:02X}",
        f"x={x}",
        f"y={y}",
        f"party_count={len(party)}",
        "inventory=" + ",".join(_item_name(item) for item in inventory[:8]),
    ) + story_evidence

    if not party and map_id == 0x00 and x == 0 and y == 0:
        return ChapterGoal(
            chapter_id="chapter_0_prologue",
            title="Complete Prologue",
            objective=(
                "Start a clean new game, advance the Oak intro, enter player and rival names, "
                "land in Red's House 2F, then hand off outside Red's house in Pallet Town."
            ),
            success=False,
            evidence=evidence,
            hints=(
                "Use complete_prologue with playerName=RED, rivalName=BLUE, and handoff=pallet_outside.",
                "The prologue skill owns title menu navigation, intro dialogue, and name keyboard entry.",
                "After the prologue handoff reaches Pallet Town outside Red's house, continue with Oak intercept.",
            ),
        )

    if not party and map_id in {0x25, 0x26}:
        return ChapterGoal(
            chapter_id="chapter_1_leave_home",
            title="Leave Red's House",
            objective="Navigate downstairs if needed, exit Red's house, and reach Pallet Town overworld.",
            success=False,
            evidence=evidence,
            hints=(
                "Use navigate_within_pallet_region target=pallet_home_1f_exit.",
                "Once outside in Pallet Town, continue to the Oak intercept chapter.",
            ),
        )

    if not _in_oaks_lab_starter_area(map_id, y) and not party:
        return ChapterGoal(
            chapter_id="chapter_2_oak_intercept",
            title="Reach Oak's starter choice",
            objective=(
                "Trigger Professor Oak at Pallet's north grass, allow the escort to Oak's Lab, "
                "and reach the starter selection surface."
            ),
            success=False,
            evidence=evidence,
            hints=(
                "If in Pallet Town and not in dialogue, navigate_within_pallet_region target=pallet_oak_trigger.",
                "If dialogue/script text is visible, advance_dialogue.",
                "If advance_dialogue is not enabled but the story appears to be waiting, use literal_button_press button=A.",
                "Do not leave Pallet for Route 1 until a starter is in the party.",
            ),
        )

    if _in_oaks_lab_starter_area(map_id, y) and not party:
        return ChapterGoal(
            chapter_id="chapter_2_choose_starter",
            title="Choose a starter",
            objective=(
                "Select one starter Pokemon from Oak's Lab. Prefer Squirtle for the current early-game path, "
                "then continue dialogue until the starter is in the party."
            ),
            success=False,
            evidence=evidence,
            hints=(
                "We do not yet have a dedicated choose_starter skill, so literal button presses may be required.",
                "From the center starter-table position, Squirtle is the right-side ball in Pokemon Red.",
                "Use navigate_within_pallet_region for lab-local positioning only if it is enabled and relevant.",
                "After interacting with a starter ball, advance_dialogue through confirmation prompts.",
            ),
        )

    if party and _rival_battle_active(map_id, mode, battle_type):
        return ChapterGoal(
            chapter_id="chapter_2_rival_battle",
            title="Win the first rival battle",
            objective="Use available battle skills to win or safely resolve the first rival battle in Oak's Lab.",
            success=False,
            evidence=evidence,
            hints=(
                "If battle dialogue is visible, use advance_battle_dialogue or resolve_battle_outcome_dialogue_bundle.",
                "If the battle action menu is available, use a damaging move from use_move moveNames.",
                "Do not use attempt_catch or flee in the rival battle.",
            ),
        )

    if _has_parcel(inventory):
        if map_id == 0x2A:
            return ChapterGoal(
                chapter_id="chapter_4_exit_mart_with_parcel",
                title="Exit Viridian Mart with Oak's Parcel",
                objective=(
                    "Oak's Parcel is in inventory. Finish the Mart clerk dialogue, exit Viridian Mart, "
                    "then return to Professor Oak in Pallet Town."
                ),
                success=False,
                evidence=evidence,
                hints=(
                    "If text is visible, use advance_dialogue until control returns to stable overworld.",
                    "When stable inside Viridian Mart, use navigate_within_pallet_region target=viridian_mart_exit to leave the building.",
                    "After exiting to Viridian City, navigate toward Pallet via Route 1.",
                ),
            )
        if map_id == 0x28:
            return ChapterGoal(
                chapter_id="chapter_4_return_parcel_in_lab",
                title="Return Oak's Parcel",
                objective=(
                    "Oak's Parcel is in inventory and the player is inside Oak's Lab. "
                    "Move to Professor Oak near the starter table, then advance the parcel handoff dialogue."
                ),
                success=False,
                evidence=evidence,
                hints=(
                    "If stable overworld in Oak's Lab and not at the starter table, use navigate_within_pallet_region target=oaks_lab_starter_table.",
                    "Once at the starter table or when dialogue is visible, use advance_dialogue one press at a time.",
                    "Continue dialogue until Oak's Parcel leaves inventory and the Pokedex/Poke Ball sequence resolves.",
                ),
            )
        return ChapterGoal(
            chapter_id="chapter_4_return_parcel",
            title="Return Oak's Parcel",
            objective="Return to Professor Oak in Pallet Town and advance dialogue until the parcel handoff resolves.",
            success=False,
            evidence=evidence,
            hints=(
                "If in Viridian City, use navigate_within_pallet_region target=route_1_south.",
                "If on Route 1, use navigate_within_pallet_region target=route_1_entrance.",
                "If in Pallet Town, use navigate_within_pallet_region target=oaks_lab_entrance.",
                "Use navigate_within_pallet_region target=oaks_lab_entrance.",
                "If already inside Oak's Lab, use navigate_within_pallet_region target=oaks_lab_starter_table.",
                "Advance dialogue in Oak's Lab until the parcel/pokedex sequence is resolved.",
            ),
        )

    has_spearow = _party_contains_species(party, "Spearow")
    has_pikachu = _party_contains_species(party, "Pikachu")
    has_boulder_badge = _has_badge(snapshot, "Boulder Badge")
    in_capsule_region = map_id in {0x01, 0x0D, 0x21, 0x29, 0x2A, 0x2F, 0x32, 0x33}
    in_capsule_return_region = map_id in {0x00, 0x0C} or in_capsule_region
    in_forest_area = map_id in {0x2F, 0x32, 0x33}
    reached_forest_exit = map_id == 0x2F or (map_id == 0x33 and y <= 0)
    in_pewter_route2 = map_id == 0x0D and y <= 12
    in_pewter_region = map_id in {0x02, 0x2F, 0x36, 0x38, 0x3A} or in_pewter_route2

    if party and has_boulder_badge:
        return ChapterGoal(
            chapter_id="chapter_7_boulder_badge_complete",
            title="Boulder Badge Complete",
            objective="Brock has been defeated and the Boulder Badge is present.",
            success=True,
            evidence=evidence + ("boulder_badge=true",),
            hints=("Stop the run and preserve the final checkpoint before Route 3.",),
        )

    if party and has_pikachu and (reached_forest_exit or in_pewter_region):
        if not _party_ready_for_brock(party):
            return _brock_leveling_goal(
                evidence=evidence,
                party=party,
                map_id=map_id,
                y=y,
                mode=mode,
                battle_type=battle_type,
            )
        if map_id == 0x36 and mode == "battle" and battle_type == 2:
            return ChapterGoal(
                chapter_id="chapter_7_defeat_brock_battle",
                title="Defeat Brock",
                objective="Win the active Pewter Gym trainer or Brock battle, then resolve post-battle dialogue until the Boulder Badge is awarded.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
                hints=(
                    "Use battle skills selected by matchup and current HP; Squirtle water moves are strong against Brock's team.",
                    "If battle dialogue is visible, use advance_battle_dialogue or resolve_battle_outcome_dialogue_bundle.",
                    "If the battle action menu is visible, use a damaging move from use_move moveNames unless healing/switching is safer.",
                    "After the battle ends, resolve dialogue until Boulder Badge appears in badge_names.",
                ),
            )
        if mode == "battle" and battle_type not in {None, 0}:
            return ChapterGoal(
                chapter_id="chapter_7_reach_pewter_city",
                title="Reach Pewter City",
                objective="Resolve the current battle safely, then continue north into Pewter City for the Brock chapter.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
                hints=(
                    "If this is a wild battle during travel, prefer safe XP or run when HP/resources are risky.",
                    "If this is a trainer battle, win it; required route battles are valid navigation waypoints.",
                    "After returning to overworld, use navigate_within_pewter_region target=pewter_city_center.",
                ),
            )
        if map_id == 0x33:
            return ChapterGoal(
                chapter_id="chapter_7_reach_pewter_city",
                title="Reach Pewter City",
                objective="Pikachu is secured. Exit Viridian Forest through the north gate, then travel through Route 2 into Pewter City.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
                hints=(
                    "Use navigate_within_viridian_forest_region target=north_gate_north to leave the forest interior.",
                    "Once in the north gate or Route 2, use navigate_within_pewter_region target=pewter_city_center.",
                    "Resolve any trainer or wild battle interruption before continuing toward Pewter.",
                ),
            )
        if map_id in {0x2F, 0x0D}:
            return ChapterGoal(
                chapter_id="chapter_7_reach_pewter_city",
                title="Reach Pewter City",
                objective="Travel from the Viridian Forest north gate / Route 2 north strip into Pewter City.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
                hints=(
                    "Use navigate_within_pewter_region target=pewter_city_center.",
                    "If route grass starts a wild battle, resolve it safely and continue north.",
                    "Once in Pewter City, prepare for Brock at the gym or heal if the party is damaged.",
                ),
            )
        if map_id == 0x3A:
            return ChapterGoal(
                chapter_id="chapter_7_prepare_for_brock",
                title="Prepare for Brock",
                objective="Heal at the Pewter PokeCenter if needed, then go to Pewter Gym and challenge Brock.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
                hints=(
                    "If the party is damaged or statused, use heal_at_pokecenter.",
                    "When healed, use navigate_within_pewter_region target=pewter_gym_brock_pre_battle.",
                    "If dialogue is active, advance it one press at a time.",
                ),
            )
        if map_id == 0x36 and _party_needs_healing(party) and mode != "battle":
            return ChapterGoal(
                chapter_id="chapter_7_prepare_for_brock",
                title="Heal Before Brock",
                objective="Leave Pewter Gym, heal at the Pewter PokeCenter, then return to challenge Brock.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false", "party_needs_healing=true"),
                hints=(
                    "Do not start a new gym battle with the current damaged party.",
                    "If dialogue is active, advance it only as needed to regain control.",
                    "When stable, use navigate_within_pewter_region target=pewter_pokecenter_counter.",
                    "At the PokeCenter counter, use heal_at_pokecenter.",
                    "After the party is fully healed, use navigate_within_pewter_region target=pewter_gym_brock_pre_battle.",
                ),
            )
        if map_id == 0x36:
            return ChapterGoal(
                chapter_id="chapter_7_defeat_brock",
                title="Defeat Brock",
                objective="Inside Pewter Gym, challenge and defeat Brock, then resolve dialogue until the Boulder Badge is awarded.",
                success=False,
                evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
                hints=(
                    "Use navigate_within_pewter_region target=pewter_gym_brock_pre_battle.",
                    "At Brock's pre-battle position (Pewter Gym map 0x36 x=5 y=1), use literal_button_press with button=left once to face Brock, then literal_button_press with button=A or advance_dialogue to start the battle.",
                    "Use battle skills to win; Squirtle's Bubble or Water Gun should be prioritized when available.",
                    "Resolve post-battle dialogue until Boulder Badge appears in badge_names.",
                ),
            )
        return ChapterGoal(
            chapter_id="chapter_7_prepare_for_brock",
            title="Prepare for Brock",
            objective="In Pewter City, heal if needed, enter Pewter Gym, defeat Brock, and obtain the Boulder Badge.",
            success=False,
            evidence=evidence + ("pikachu_caught=true", "boulder_badge=false"),
            hints=_pewter_pre_brock_hints(party),
        )

    if party and has_pikachu and in_capsule_return_region:
        return ChapterGoal(
            chapter_id="chapter_6_capsule_a_exit_forest",
            title="Exit Viridian Forest",
            objective=(
                "Pikachu is secured. Return to Viridian Forest if needed, then navigate through "
                "Viridian Forest to the north exit without blacking out."
            ),
            success=False,
            evidence=evidence + ("pikachu_caught=true",),
            hints=(
                "Do not return to Route 22; the forest traversal objective is active.",
                "Do not buy more Poke Balls unless a future explicit goal requires it; Pikachu is already secured.",
                "If in Pallet Town, use navigate_within_pallet_region target=route_1_entrance.",
                "If on Route 1, use navigate_within_pallet_region target=viridian_city_south_entrance.",
                "If in Viridian Mart or Viridian PokeCenter, close any menu/dialogue and leave toward Viridian City.",
                "Use navigate_within_viridian_forest_region target=forest_north_exit.",
                "If a trainer battle interrupts traversal, resolve it and continue toward the north exit.",
                "If a wild battle interrupts traversal, resolve or flee conservatively and continue toward the north exit.",
            ),
        )

    if party and poke_balls > 0 and battle_type == 1 and mode == "battle" and map_id in {0x21, 0x33}:
        enemy = snapshot.get("enemy") if isinstance(snapshot.get("enemy"), dict) else {}
        enemy_species = str(enemy.get("species_name", "unknown"))
        if map_id == 0x21 and not has_spearow:
            return ChapterGoal(
                chapter_id="chapter_5b_route_22_spearow_catch",
                title="Catch Route 22 Spearow",
                objective="Catch a Spearow from Route 22 before entering Viridian Forest.",
                success=False,
                evidence=evidence + (f"enemy_species={enemy_species}",),
                hints=(
                    "If the wild enemy is Spearow, use attempt_catch.",
                    "If the wild enemy is not Spearow, do not spend Poke Balls on it; either run when HP/resources are risky or take a safe XP turn.",
                    "If post-catch dialogue appears, use resolve_battle_outcome_dialogue_bundle.",
                    "If prompted for a nickname, decline unless an explicit nickname directive is present.",
                ),
            )
        if map_id == 0x33 and not has_pikachu:
            return ChapterGoal(
                chapter_id="chapter_6_capsule_a_pikachu_catch",
                title="Catch Viridian Forest Pikachu",
                objective="Catch a Pikachu in Viridian Forest. Do not spend Poke Balls on non-Pikachu encounters.",
                success=False,
                evidence=evidence + (f"enemy_species={enemy_species}",),
                hints=(
                    "If the wild enemy is Pikachu, use attempt_catch.",
                    "If the wild enemy is not Pikachu, do not spend Poke Balls on it; run or take only safe XP turns.",
                    "If post-catch dialogue appears, use resolve_battle_outcome_dialogue_bundle.",
                    "If prompted for a nickname, decline unless an explicit nickname directive is present.",
                ),
            )
        return ChapterGoal(
            chapter_id="chapter_6_capsule_a_exit_forest",
            title="Exit Viridian Forest",
            objective="Pikachu is secured. Resolve the current battle state, then navigate to the forest north exit.",
            success=False,
            evidence=evidence + ("pikachu_caught=true",),
            hints=(
                "Resolve battle dialogue or flee from nonessential wild battles.",
                "After returning to overworld, use navigate_within_viridian_forest_region target=forest_north_exit.",
            ),
        )

    if party and poke_balls >= 5 and not has_spearow and map_id in {0x28, 0x00, 0x0C, 0x01, 0x0D, 0x21, 0x2A}:
        return ChapterGoal(
            chapter_id="chapter_5b_route_22_spearow",
            title="Catch Route 22 Spearow",
            objective="After buying Poke Balls, travel to Route 22 approved grass and catch a Spearow before entering Viridian Forest.",
            success=False,
            evidence=evidence + ("route_22_spearow_caught=false",),
            hints=(
                "Poke Balls are already secured; do not return to the Viridian Mart unless inventory drops below 5 Poke Balls.",
                "If in Oak's Lab, use navigate_within_pallet_region target=oaks_lab_exit.",
                "If in Pallet Town, use navigate_within_pallet_region target=route_1_entrance.",
                "If on Route 1, use navigate_within_pallet_region target=viridian_city_south_entrance.",
                "If in Viridian Mart, close menu/dialogue first, then navigate out toward Viridian City.",
                "Use navigate_within_viridian_forest_region target=route_22_grass to reach Route 22 approved grass.",
                "If already in or near Route 22 approved grass, use enter_grass_search_loop patch=current_map.",
                "If a wild battle starts, catch it only if it is Spearow; otherwise avoid spending Poke Balls and keep searching Route 22.",
            ),
        )

    if party and poke_balls > 0 and in_forest_area and not has_pikachu:
        return ChapterGoal(
            chapter_id="chapter_6_capsule_a",
            title="Viridian Forest Pikachu",
            objective="Catch Pikachu specifically in Viridian Forest, then reach the forest north exit.",
            success=False,
            evidence=evidence + ("pikachu_caught=false",),
            hints=(
                "Route 22 is out of scope after entering Viridian Forest.",
                "Use navigate_within_viridian_forest_region target=forest_grass to reach approved Viridian Forest grass.",
                "If already in or near approved Viridian Forest grass, use enter_grass_search_loop patch=current_map.",
                "If a wild battle starts, catch it only if it is Pikachu; otherwise do not spend Poke Balls.",
                "After Pikachu is caught, use navigate_within_viridian_forest_region target=forest_north_exit.",
            ),
        )

    if party and poke_balls > 0 and has_spearow and in_capsule_region and not has_pikachu:
        return ChapterGoal(
            chapter_id="chapter_6_capsule_a",
            title="Viridian Forest Pikachu",
            objective="Route 22 Spearow is secured. Enter Viridian Forest, catch Pikachu specifically, then reach the forest north exit.",
            success=False,
            evidence=evidence,
            hints=(
                "If in Viridian Mart, close menu/dialogue and navigate out toward an approved grass destination.",
                "Use navigate_within_viridian_forest_region target=forest_grass to reach the forest grass.",
                "If already in or near approved grass, use enter_grass_search_loop patch=current_map.",
                "If a wild battle starts, catch it only if it is Pikachu; otherwise do not spend Poke Balls.",
                "After Pikachu is caught, use navigate_within_viridian_forest_region target=forest_north_exit.",
            ),
        )

    if party and poke_balls < 5 and _parcel_loop_complete(snapshot, party) and map_id in {0x28, 0x00, 0x0C, 0x01, 0x2A}:
        return ChapterGoal(
            chapter_id="chapter_5_acquire_poke_balls",
            title="Acquire first Poke Balls",
            objective=(
                "Travel to Viridian Mart and acquire at least 5 Poke Balls. Prefer buying as many Poke Balls as "
                "the current budget allows before Route 22 and Viridian Forest. If the clerk gives Oak's Parcel "
                "instead, return it to Professor Oak, then come back to buy Poke Balls."
            ),
            success=False,
            evidence=evidence,
            hints=(
                "If in Oak's Lab, navigate_within_pallet_region target=oaks_lab_exit.",
                "If in Pallet Town, navigate_within_pallet_region target=route_1_entrance.",
                "If on Route 1, navigate_within_pallet_region target=viridian_city_south_entrance.",
                "If in Viridian City, navigate_within_pallet_region target=viridian_mart_front_door.",
                "If in Viridian Mart, navigate_within_pallet_region target=viridian_mart_counter and advance dialogue.",
                "When the shop BUY item list is open, use purchase_pokemart_item item=Poke Ball quantity=99; the skill will stop at the affordable count.",
            ),
        )

    if party and map_id == 0x28:
        at_lab_exit = x == 5 and y == 11
        return ChapterGoal(
            chapter_id="chapter_2_leave_oaks_lab",
            title="Leave Oak's Lab",
            objective=(
                "Resolve remaining post-starter lab dialogue, then leave Oak's Lab. "
                "If the first rival battle has not happened yet, walking toward the exit should trigger it."
            ),
            success=False,
            evidence=evidence,
            hints=(
                "Advance dialogue while text is present.",
                (
                    "If stable overworld in Oak's Lab, use navigate_within_pallet_region target=oaks_lab_exit to leave the building."
                    if at_lab_exit
                    else "If stable overworld in Oak's Lab, navigate_within_pallet_region target=oaks_lab_exit."
                ),
                "After the rival battle begins, switch to tactical battle skills.",
            ),
        )

    if party and map_id == 0x00:
        return ChapterGoal(
            chapter_id="chapter_3_reach_route_1",
            title="Start the Viridian parcel trip",
            objective="Leave Pallet Town by navigating to the Route 1 entrance.",
            success=False,
            evidence=evidence,
            hints=(
                "Use navigate_within_pallet_region target=route_1_entrance.",
                "Recover to overworld or advance dialogue if transient UI blocks navigation.",
            ),
        )

    if party and map_id == 0x0C:
        return ChapterGoal(
            chapter_id="chapter_3_route_1_to_viridian",
            title="Travel through Route 1",
            objective="Reach Viridian City and enter the Mart to retrieve Oak's Parcel.",
            success=False,
            evidence=evidence,
            hints=(
                "Use navigate_within_pallet_region target=viridian_city_south_entrance.",
                "If already in Viridian City, use navigate_within_pallet_region target=viridian_mart_front_door.",
                "Resolve wild battles conservatively if they occur.",
            ),
        )

    if party and map_id == 0x01:
        return ChapterGoal(
            chapter_id="chapter_3_viridian_mart",
            title="Reach Viridian Mart",
            objective="Navigate to the Viridian Mart front door and enter the Mart to retrieve Oak's Parcel.",
            success=False,
            evidence=evidence,
            hints=(
                "Use navigate_within_pallet_region target=viridian_mart_front_door.",
                "If at the Mart front door, use navigate_within_pallet_region target=viridian_mart_entrance.",
                "Once inside the Mart, navigate to viridian_mart_counter and advance dialogue.",
            ),
        )

    if party and map_id == 0x2A:
        return ChapterGoal(
            chapter_id="chapter_3_retrieve_parcel",
            title="Retrieve Oak's Parcel",
            objective="Reach the Viridian Mart counter and advance dialogue to receive Oak's Parcel.",
            success=False,
            evidence=evidence,
            hints=(
                "Use navigate_within_pallet_region target=viridian_mart_counter.",
                "When at the counter or text is visible, use advance_dialogue or literal_button_press button=A.",
                "After the parcel is received, route back to Pallet and Oak's Lab.",
            ),
        )

    return ChapterGoal(
        chapter_id="chapter_3_or_5_unresolved",
        title="Continue early-game progression",
        objective=(
            "Continue the next supported early-game story step: reach Viridian, retrieve or return Oak's Parcel, "
            "or acquire Poke Balls if the parcel loop is complete."
        ),
        success=False,
        evidence=evidence,
        hints=(
            "Prefer high-level navigation and dialogue skills when enabled.",
            "Use literal button presses only for small recovery steps or unsupported story UI.",
            "Stop only if no enabled skill can make progress.",
        ),
    )


def _in_oaks_lab_starter_area(map_id: int, y: int) -> bool:
    return map_id == 0x28 and y <= 4


def _rival_battle_active(map_id: int, mode: str, battle_type: int) -> bool:
    return map_id == 0x28 and mode == "battle" and battle_type == 2


def _has_parcel(inventory: list[Any]) -> bool:
    return any(
        (isinstance(item, dict) and item.get("item_id") == 0x46)
        or "parcel" in _item_name(item).lower()
        for item in inventory
    )


def _has_poke_balls(inventory: list[Any]) -> bool:
    return _poke_ball_count(inventory) > 0


def _poke_ball_count(inventory: list[Any]) -> int:
    for item in inventory:
        if isinstance(item, dict) and _item_name(item).lower() == "poke ball":
            return int(item.get("quantity", 0) or 0)
    return 0


def _max_party_level(party: list[Any]) -> int:
    levels: list[int] = []
    for member in party:
        if isinstance(member, dict):
            levels.append(_int_or_default(member.get("level"), 0))
    return max(levels, default=0)


def _parcel_loop_complete(snapshot: dict[str, Any], party: list[Any]) -> bool:
    story_events = _story_event_values(snapshot)
    if any(key in story_events for key in ("oak_got_parcel", "got_pokedex")):
        return story_events.get("oak_got_parcel") is True or story_events.get("got_pokedex") is True
    return _max_party_level(party) >= 6


def _story_event_values(snapshot: dict[str, Any]) -> dict[str, bool]:
    raw_events = snapshot.get("story_events")
    if isinstance(raw_events, dict):
        return {
            str(key): bool(value)
            for key, value in raw_events.items()
            if isinstance(value, bool)
        }

    details = snapshot.get("story_event_details")
    if isinstance(details, list):
        values: dict[str, bool] = {}
        for detail in details:
            if not isinstance(detail, dict):
                continue
            key = detail.get("key")
            value = detail.get("value")
            if isinstance(key, str) and isinstance(value, bool):
                values[key] = value
        return values

    return {}


def _party_contains_species(party: list[Any], species_name: str) -> bool:
    target = species_name.strip().lower()
    for member in party:
        if isinstance(member, dict) and str(member.get("species_name", "")).strip().lower() == target:
            return True
    return False


def _party_needs_healing(party: list[Any]) -> bool:
    for member in party:
        if not isinstance(member, dict):
            continue
        try:
            hp = int(member.get("hp", 0) or 0)
            max_hp = int(member.get("max_hp", 0) or 0)
            status = int(member.get("status", 0) or 0)
        except (TypeError, ValueError):
            return True
        if max_hp > 0 and (hp < max_hp or status != 0):
            return True
    return False


def _party_ready_for_brock(party: list[Any]) -> bool:
    for member in party:
        if not isinstance(member, dict):
            continue
        species = str(member.get("species_name", "")).strip().lower()
        nickname = str(member.get("nickname", "")).strip().lower()
        if species not in {"squirtle", "wartortle", "blastoise"} and nickname not in {"squirtle", "wartortle", "blastoise"}:
            continue
        moves = member.get("moves") if isinstance(member.get("moves"), list) else []
        move_names = {
            str(move.get("move_name") or move.get("name") or "").strip().lower()
            for move in moves
            if isinstance(move, dict)
        }
        if {"bubble", "water gun"} & move_names:
            return True
    return False


def _brock_leveling_goal(
    *,
    evidence: tuple[str, ...],
    party: list[Any],
    map_id: int,
    y: int,
    mode: str,
    battle_type: int,
) -> ChapterGoal:
    base_evidence = evidence + (
        "pikachu_caught=true",
        "boulder_badge=false",
        "brock_ready=false",
    )
    if mode == "battle" and battle_type not in {None, 0}:
        return ChapterGoal(
            chapter_id="chapter_7_level_for_brock",
            title="Level Before Brock",
            objective="Resolve the current battle safely and gain experience before challenging Brock.",
            success=False,
            evidence=base_evidence,
            hints=(
                "Do not spend Poke Balls during Brock preparation unless an explicit future goal requires it.",
                "Use damaging moves to gain experience when safe; switch to a healthy party member if the active battler faints.",
                "If the battle becomes dangerous, resolve it conservatively and heal afterward.",
                "After returning to overworld, heal if needed, then train around pewter_route2_grass until Squirtle learns Bubble.",
            ),
        )
    if map_id == 0x33:
        forest_exit_hint = (
            "Use navigate_within_viridian_forest_region target=north_gate_north to step through the north gate."
            if mode != "battle" and y <= 0
            else "Use navigate_within_viridian_forest_region target=forest_north_exit to finish leaving Viridian Forest."
        )
        return ChapterGoal(
            chapter_id="chapter_7_level_for_brock",
            title="Level Before Brock",
            objective="Finish exiting Viridian Forest, heal if needed, then train near Pewter until Squirtle learns Bubble.",
            success=False,
            evidence=base_evidence,
            hints=(
                forest_exit_hint,
                "Once in the north gate or Route 2, use navigate_within_pewter_region target=pewter_pokecenter_counter if the party needs healing.",
                "After healing, use navigate_within_pewter_region target=pewter_route2_grass.",
                "When near or inside Route 2 grass, use enter_grass_search_loop patch=current_map to start training battles.",
            ),
        )
    if _party_needs_healing(party):
        return ChapterGoal(
            chapter_id="chapter_7_level_for_brock",
            title="Level Before Brock",
            objective="Heal the party, then train near Pewter until Squirtle learns Bubble before challenging Brock.",
            success=False,
            evidence=base_evidence + ("party_needs_healing=true",),
            hints=(
                "Use navigate_within_pewter_region target=pewter_pokecenter_counter.",
                "At the PokeCenter counter, use heal_at_pokecenter.",
                "After the party is fully healed, use navigate_within_pewter_region target=pewter_route2_grass.",
                "When near or inside Route 2 grass, use enter_grass_search_loop patch=current_map to start training battles.",
            ),
        )
    if map_id == 0x3A:
        return ChapterGoal(
            chapter_id="chapter_7_level_for_brock",
            title="Level Before Brock",
            objective="Leave the PokeCenter and train near Pewter until Squirtle learns Bubble before challenging Brock.",
            success=False,
            evidence=base_evidence,
            hints=(
                "Use navigate_within_pewter_region target=pewter_route2_grass.",
                "When near or inside Route 2 grass, use enter_grass_search_loop patch=current_map to start training battles.",
                "Fight safe wild battles for experience; heal if the party becomes damaged.",
            ),
        )
    return ChapterGoal(
        chapter_id="chapter_7_level_for_brock",
        title="Level Before Brock",
        objective="Train near Pewter until Squirtle learns Bubble before challenging Brock.",
        success=False,
        evidence=base_evidence,
        hints=(
            "Use navigate_within_pewter_region target=pewter_route2_grass.",
            "When near or inside Route 2 grass, use enter_grass_search_loop patch=current_map to start training battles.",
            "Fight safe wild battles for experience; heal at the Pewter PokeCenter if the party becomes damaged.",
            "Only enter Pewter Gym after Squirtle learns Bubble or Water Gun.",
        ),
    )


def _pewter_pre_brock_hints(party: list[Any]) -> tuple[str, ...]:
    if _party_needs_healing(party):
        return (
            "Party has damage/status; use navigate_within_pewter_region target=pewter_pokecenter_counter before going to the gym.",
            "At the PokeCenter counter, use heal_at_pokecenter.",
            "After the party is fully healed, use navigate_within_pewter_region target=pewter_gym_brock_pre_battle.",
            "If a gym trainer battle interrupts navigation after healing, win it and continue toward Brock.",
            "After Brock is defeated, resolve dialogue until Boulder Badge appears in badge_names.",
        )
    return (
        "Party appears healthy enough to proceed toward the gym.",
        "Use navigate_within_pewter_region target=pewter_gym_brock_pre_battle.",
        "If a gym trainer battle interrupts navigation, win it and continue toward Brock.",
        "After Brock is defeated, resolve dialogue until Boulder Badge appears in badge_names.",
    )


def _has_badge(snapshot: dict[str, Any], badge_name: str) -> bool:
    badges = snapshot.get("badge_names")
    if not isinstance(badges, list):
        return False
    target = badge_name.strip().lower()
    return any(str(badge).strip().lower() == target for badge in badges)


def _int_or_default(value: Any, default: int) -> int:
    return value if isinstance(value, int) else default


def _item_name(item: Any) -> str:
    if not isinstance(item, dict):
        return "unknown"
    return str(item.get("item_name") or item.get("name") or item.get("item_id") or "unknown")
