from __future__ import annotations

from dataclasses import replace

from pokemon_player.battle_menu_env import (
    ACTION_NAMES,
    BattleMenuFacts,
    BattleMenuEnvConfig,
    BattleMenuThrowEnv,
    BattleMenuRewardConfig,
    FACT_VECTOR_LEN,
    best_ball_inventory_index,
    expert_action_for,
    facts_are_stagnant,
    inventory_prefix,
    normalize_bag_cursor_index,
    score_transition,
    selected_inventory_item,
    structured_state_vector,
    terminal_reason,
    valid_action_mask_for,
    valid_action_names_for,
)


def facts(
    *,
    mode: str = "battle",
    balls: int = 5,
    party_count: int = 2,
    party_hp: int = 30,
    enemy_hp: int = 12,
    ui_kind: str = "action_menu",
    ui_cursor: str = "fight",
) -> BattleMenuFacts:
    return BattleMenuFacts(
        mode=mode,
        battle_type_raw=1 if mode == "battle" else 0,
        poke_balls=balls,
        all_balls=balls,
        party_count=party_count,
        party_hp=party_hp,
        enemy_hp=enemy_hp,
        enemy_max_hp=12,
        ui_kind=ui_kind,
        ui_cursor=ui_cursor,
    )


def test_reward_terminates_when_ball_count_decreases() -> None:
    reward, parts, terminated = score_transition(
        initial=facts(balls=5),
        previous=facts(balls=5),
        current=facts(balls=4),
        config=BattleMenuRewardConfig(),
    )

    assert terminated
    assert parts["ball_decreased"] > 0
    assert reward > 0


def test_reward_penalizes_enemy_hp_drop_without_terminal_success() -> None:
    reward, parts, terminated = score_transition(
        initial=facts(enemy_hp=12),
        previous=facts(enemy_hp=12),
        current=facts(enemy_hp=8),
        config=BattleMenuRewardConfig(),
    )

    assert terminated
    assert parts["enemy_hp_decreased"] < 0
    assert reward < 0
    assert (
        terminal_reason(facts(enemy_hp=12), facts(enemy_hp=8), previous=facts(enemy_hp=12))
        == "enemy_hp_decreased"
    )


def test_reward_penalizes_battle_end_without_throw() -> None:
    reward, parts, terminated = score_transition(
        initial=facts(balls=5),
        previous=facts(balls=5),
        current=facts(mode="overworld", balls=5),
        config=BattleMenuRewardConfig(),
    )

    assert terminated
    assert parts["battle_ended_without_throw"] < 0
    assert reward < 0
    assert terminal_reason(facts(balls=5), facts(mode="overworld", balls=5)) == "battle_ended"


def test_reward_shapes_progress_toward_item_menu() -> None:
    reward, parts, terminated = score_transition(
        initial=facts(ui_kind="action_menu", ui_cursor="fight"),
        previous=facts(ui_kind="action_menu", ui_cursor="fight"),
        current=facts(ui_kind="item_menu", ui_cursor="unknown"),
        config=BattleMenuRewardConfig(),
    )

    assert not terminated
    assert parts["ui_progress_delta"] > 0
    assert reward > 0


def test_expert_action_hints_menu_route() -> None:
    assert expert_action_for(facts(ui_kind="dialogue", ui_cursor="unknown")) == "a"
    assert expert_action_for(facts(ui_kind="action_menu", ui_cursor="fight")) == "down"
    assert expert_action_for(facts(ui_kind="action_menu", ui_cursor="item")) == "a"
    assert expert_action_for(facts(ui_kind="item_menu", ui_cursor="unknown")) == "down"
    assert expert_action_for(facts(ui_kind="item_menu", ui_cursor="unknown"), item_menu_steps=1) == "a"
    assert expert_action_for(facts(ui_kind="unknown", ui_cursor="unknown"), in_item_flow=True) == "a"


def test_valid_action_mask_encodes_skill_route() -> None:
    assert valid_action_names_for(facts(ui_kind="action_menu", ui_cursor="fight")) == ("down",)
    assert valid_action_names_for(facts(ui_kind="action_menu", ui_cursor="item")) == ("a",)
    assert valid_action_names_for(facts(ui_kind="action_menu", ui_cursor="run")) == ("left",)
    assert valid_action_names_for(facts(ui_kind="unknown", ui_cursor="unknown")) == ("b",)
    assert valid_action_names_for(
        facts(ui_kind="unknown", ui_cursor="unknown"),
        in_item_flow=True,
    ) == ("a",)
    assert valid_action_names_for(facts(ui_kind="move_menu", ui_cursor="move_1")) == ("a",)
    assert valid_action_names_for(facts(ui_kind="move_menu", ui_cursor="move_2")) == ("up",)

    mask = valid_action_mask_for(facts(ui_kind="action_menu", ui_cursor="item"))

    assert [ACTION_NAMES[index] for index, valid in enumerate(mask) if valid] == ["a"]


def test_valid_action_uses_inventory_context_in_item_menu() -> None:
    item_menu = replace(
        facts(ui_kind="item_menu", ui_cursor="unknown"),
        bag_cursor_index=0,
        selected_item_id=0x05,
        selected_item_quantity=1,
        best_ball_index=2,
    )

    assert valid_action_names_for(item_menu) == ("down",)
    assert valid_action_names_for(replace(item_menu, bag_cursor_index=3)) == ("up",)
    assert valid_action_names_for(
        replace(
            item_menu,
            bag_cursor_index=2,
            selected_item_id=0x04,
            selected_item_quantity=5,
        )
    ) == ("a",)


def test_bag_cursor_normalizer_includes_cancel_row() -> None:
    assert normalize_bag_cursor_index(0, 4) == 0
    assert normalize_bag_cursor_index(4, 4) == 4
    assert normalize_bag_cursor_index(5, 4) == 0


def test_stagnant_facts_detect_repeated_noop() -> None:
    assert facts_are_stagnant(facts(), facts())
    assert not facts_are_stagnant(facts(), facts(ui_cursor="item"))


def test_inventory_helpers_expose_selected_item_and_ball_index() -> None:
    inventory = [
        {"item_id": 0x05, "quantity": 1},
        {"item_id": 0x04, "quantity": 5},
        {"item_id": 0x0B, "quantity": 3},
    ]

    assert selected_inventory_item(inventory, 1) == (0x04, 5)
    assert best_ball_inventory_index(inventory) == 1
    assert inventory_prefix(inventory, 4) == ((0x05, 0x04, 0x0B, 0), (1, 5, 3, 0))


def test_structured_state_vector_includes_ui_and_item_context() -> None:
    vector = structured_state_vector(
        BattleMenuFacts(
            mode="battle",
            battle_type_raw=1,
            poke_balls=5,
            all_balls=5,
            party_count=4,
            party_hp=100,
            enemy_hp=15,
            enemy_max_hp=15,
            ui_kind="item_menu",
            ui_cursor="unknown",
            bag_cursor_index=1,
            selected_item_id=0x04,
            selected_item_quantity=5,
            first_item_ids=(0x05, 0x04, 0x0B, 0, 0, 0),
            first_item_quantities=(1, 5, 3, 0, 0, 0),
            best_ball_index=1,
            in_item_flow=True,
            throw_initiated=False,
        ),
        step_count=3,
    )

    assert len(vector) == FACT_VECTOR_LEN
    assert vector[8] == 2
    assert vector[10] == 1
    assert vector[11] == 0x04
    assert vector[12] == 5
    assert vector[-1] == 1


class FakeBattleMenuEnv(BattleMenuThrowEnv):
    def __init__(self, facts_sequence: list[BattleMenuFacts]) -> None:
        self._facts_sequence = facts_sequence
        self.config = BattleMenuEnvConfig(rom_path=__file__, state_paths=())
        self.initial_facts = facts_sequence[0]
        self.previous_facts = facts_sequence[0]
        self.trace = []
        self.step_count = 0
        self._item_menu_steps = 0
        self._in_item_flow = True
        self._item_flow_a_presses = 0
        self._throw_initiated = False
        self._bag_cursor_index = facts_sequence[0].bag_cursor_index

    def _run_action(self, action_name: str) -> None:
        self._last_action_name = action_name

    def _facts(self) -> BattleMenuFacts:
        return self._facts_sequence[min(self.step_count, len(self._facts_sequence) - 1)]

    def _observation(self) -> dict:
        return {}


def test_invalid_non_ball_item_use_terminates_without_throw_credit() -> None:
    env = FakeBattleMenuEnv(
        [
            facts(ui_kind="item_menu", ui_cursor="unknown"),
            facts(ui_kind="dialogue", ui_cursor="unknown"),
        ]
    )
    env.previous_facts = replace(
        env.previous_facts,
        selected_item_id=0x05,
        selected_item_quantity=1,
    )

    _, reward, terminated, _, info = env.step(ACTION_NAMES.index("a"))

    assert terminated
    assert reward < -10
    assert info["terminated_reason"] == "invalid_item_used"
    assert not info["throw_initiated"]


def test_action_menu_item_cursor_a_gets_small_reward() -> None:
    env = FakeBattleMenuEnv(
        [
            facts(ui_kind="action_menu", ui_cursor="item"),
            facts(ui_kind="item_menu", ui_cursor="unknown"),
        ]
    )
    env._in_item_flow = False

    _, reward, terminated, _, info = env.step(ACTION_NAMES.index("a"))

    assert not terminated
    assert reward > 0
    assert info["reward_parts"]["action_menu_item_selected"] > 0


def test_action_menu_a_on_fight_is_terminally_unsafe() -> None:
    env = FakeBattleMenuEnv(
        [
            facts(ui_kind="action_menu", ui_cursor="fight"),
            facts(ui_kind="unknown", ui_cursor="unknown"),
        ]
    )
    env._in_item_flow = False

    _, reward, terminated, _, info = env.step(ACTION_NAMES.index("a"))

    assert terminated
    assert reward < -10
    assert info["terminated_reason"] == "unsafe_battle_menu_select"


def test_backing_out_of_item_menu_is_terminal_backtrack() -> None:
    env = FakeBattleMenuEnv(
        [
            facts(ui_kind="item_menu", ui_cursor="unknown"),
            facts(ui_kind="action_menu", ui_cursor="item"),
        ]
    )
    env.previous_facts = replace(
        env.previous_facts,
        selected_item_id=0x04,
        selected_item_quantity=5,
    )

    _, reward, terminated, _, info = env.step(ACTION_NAMES.index("b"))

    assert terminated
    assert reward < -5
    assert info["terminated_reason"] == "item_menu_backtrack"


def test_ball_item_a_gets_significant_reward() -> None:
    env = FakeBattleMenuEnv(
        [
            facts(ui_kind="item_menu", ui_cursor="unknown"),
            facts(ui_kind="unknown", ui_cursor="unknown"),
        ]
    )
    env.previous_facts = replace(
        env.previous_facts,
        selected_item_id=0x04,
        selected_item_quantity=5,
    )

    _, reward, terminated, _, info = env.step(ACTION_NAMES.index("a"))

    assert terminated
    assert reward > 3
    assert info["reward_parts"]["ball_item_selected"] > 0
    assert info["throw_initiated"]
    assert info["terminated_reason"] == "throw_initiated"


def test_stale_action_menu_item_after_opening_bag_can_mark_throw_initiated() -> None:
    stale_action_menu_with_ball = replace(
        facts(ui_kind="action_menu", ui_cursor="item"),
        selected_item_id=0x04,
        selected_item_quantity=5,
    )
    env = FakeBattleMenuEnv(
        [
            stale_action_menu_with_ball,
            stale_action_menu_with_ball,
        ]
    )
    env._in_item_flow = False

    _, _, first_terminated, _, first_info = env.step(ACTION_NAMES.index("a"))
    _, reward, second_terminated, _, second_info = env.step(ACTION_NAMES.index("a"))

    assert not first_terminated
    assert first_info["reward_parts"]["action_menu_item_selected"] > 0
    assert second_terminated
    assert reward > 10
    assert second_info["throw_initiated"]
    assert second_info["terminated_reason"] == "throw_initiated"


def test_stale_action_menu_item_flow_moves_from_non_ball_to_ball() -> None:
    stale_town_map_selection = replace(
        facts(ui_kind="action_menu", ui_cursor="item"),
        bag_cursor_index=0,
        best_ball_index=1,
        selected_item_id=0x05,
        selected_item_quantity=1,
        first_item_ids=(0x05, 0x04, 0x0B, 0x14, 0, 0),
        first_item_quantities=(1, 10, 3, 1, 0, 0),
    )

    assert valid_action_names_for(stale_town_map_selection, in_item_flow=True) == ("down",)


def test_ball_item_confirmation_can_mark_throw_initiated() -> None:
    env = FakeBattleMenuEnv(
        [
            facts(ui_kind="item_menu", ui_cursor="unknown"),
            facts(ui_kind="unknown", ui_cursor="unknown"),
        ]
    )
    env.previous_facts = replace(
        env.previous_facts,
        selected_item_id=0x04,
        selected_item_quantity=5,
    )
    env._item_flow_a_presses = 1

    _, reward, terminated, _, info = env.step(ACTION_NAMES.index("a"))

    assert terminated
    assert reward > 10
    assert info["throw_initiated"]
    assert info["terminated_reason"] == "throw_initiated"
