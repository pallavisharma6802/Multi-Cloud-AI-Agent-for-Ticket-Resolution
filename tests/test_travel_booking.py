"""Tests for the travel_booking package.

Covers the pieces that are pure logic and genuinely testable without network
access: the 4 verification checks, the bandit preference aggregator, password
hashing/sessions, and the persistence layer. Deliberately does NOT test the
live search path -- that needs real SerpApi/Bedrock calls, which belong in
travel_booking/eval/battery.py, not a unit test suite.

Several of these tests exist because the audit found real bugs in exactly
these places (bidirectional duplicate friendships, trip length derived from
the availability window, the RL reward loop breaking on restart).
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Point the whole travel_booking persistence layer at a throwaway SQLite
    file so tests never touch a real user's travel.db."""
    import travel_booking.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


# ---------------------------------------------------------------------------
# Verification agent -- the project's core differentiator
# ---------------------------------------------------------------------------

def _constraints(**overrides):
    from travel_booking.agents.schemas import ResolvedConstraints

    base = dict(
        destination_code="AUS", destination_raw="Austin", party_size=2, nights=3,
        nights_defaulted=False, date_range_start="2026-10-05", date_range_end="2026-10-08",
        dates_defaulted=False, budget_amount=2000.0, budget_scope="total_trip",
        required_amenities=[], raw_request="test", assumptions=[],
    )
    base.update(overrides)
    return ResolvedConstraints(**base)


def _hotel(**overrides):
    base = dict(
        id="H1", name="Test Hotel", destination="AUS", destination_name="Austin, TX",
        price_per_night=100, resort_fee_per_night=0, check_in_time="15:00",
        front_desk_24hr=True, front_desk_closes=None, check_out_time="11:00",
        max_occupancy=4, amenities=["wifi", "pool"], amenity_notes={},
    )
    base.update(overrides)
    return base


def _flight(**overrides):
    base = dict(
        id="F1", origin="ORD", destination="AUS", date="2026-10-05", airline="Test Air",
        flight_number="TA1", departure_time="08:00", arrival_time="10:45",
        arrives_next_day=False, price=200,
    )
    base.update(overrides)
    return base


def test_all_four_checks_pass_on_a_clean_combination():
    from travel_booking.agents.verification_agent import VerificationAgent

    result = VerificationAgent().verify(_hotel(), _flight(), _constraints(required_amenities=["pool"]))
    assert result.passed
    assert {c.name for c in result.checks} == {"arrival_vs_checkin", "budget", "amenities", "capacity"}
    # flight 200 x 2 people + hotel 100 x 3 nights
    assert result.total_cost == pytest.approx(700.0)


def test_amenity_tagged_but_unavailable_is_caught():
    """The dataset's signature trap: the tag is present, a note says it isn't."""
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(amenity_notes={"pool": "Pool closed for renovation."})
    result = VerificationAgent().verify(hotel, _flight(), _constraints(required_amenities=["pool"]))
    assert not result.passed
    failed = [c.name for c in result.failed_checks()]
    assert failed == ["amenities"]


def test_mandatory_resort_fee_counts_against_a_per_night_budget():
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(price_per_night=189, resort_fee_per_night=35)
    c = _constraints(budget_amount=200.0, budget_scope="per_night_hotel")
    result = VerificationAgent().verify(hotel, _flight(), c)
    assert not result.passed
    assert [x.name for x in result.failed_checks()] == ["budget"]


def test_late_arrival_against_a_desk_that_closes_is_caught():
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(front_desk_24hr=False, front_desk_closes="22:00")
    flight = _flight(arrival_time="23:55")
    result = VerificationAgent().verify(hotel, flight, _constraints())
    assert [x.name for x in result.failed_checks()] == ["arrival_vs_checkin"]


def test_next_day_arrival_fails_even_if_clock_time_looks_early():
    """00:05 is numerically before 22:00 -- only the +1 day flag makes it wrong."""
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(front_desk_24hr=False, front_desk_closes="22:00")
    flight = _flight(arrival_time="00:05", arrives_next_day=True)
    result = VerificationAgent().verify(hotel, flight, _constraints())
    assert [x.name for x in result.failed_checks()] == ["arrival_vs_checkin"]


def test_capacity_trap_is_caught():
    from travel_booking.agents.verification_agent import VerificationAgent

    result = VerificationAgent().verify(_hotel(max_occupancy=2), _flight(), _constraints(party_size=4))
    assert [x.name for x in result.failed_checks()] == ["capacity"]


def test_missing_real_world_fields_are_flagged_unverifiable_not_passed():
    """Real Google Hotels data has no front-desk hours or occupancy. Those
    checks must report data_available=False, never a silent green pass."""
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(front_desk_24hr=None, front_desk_closes=None, max_occupancy=None)
    result = VerificationAgent().verify(hotel, _flight(), _constraints())
    by_name = {c.name: c for c in result.checks}
    assert by_name["arrival_vs_checkin"].data_available is False
    assert by_name["capacity"].data_available is False
    assert by_name["budget"].data_available is True


def test_real_world_free_text_amenities_match_fuzzily():
    """SerpApi returns 'Outdoor pool' / 'Free Wi-Fi', not the dataset's exact tags."""
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(amenities=["Outdoor pool", "Free Wi-Fi", "Fitness center"])
    c = _constraints(required_amenities=["pool", "wifi", "gym"])
    result = VerificationAgent().verify(hotel, _flight(), c)
    assert result.passed


def test_none_resort_fee_does_not_crash_budget_math():
    """Regression: dict.get(k, 0) doesn't help when the key exists and is None."""
    from travel_booking.agents.verification_agent import compute_total_cost

    hotel = _hotel(resort_fee_per_night=None)
    assert compute_total_cost(hotel, _flight(), _constraints()) == pytest.approx(700.0)


# ---------------------------------------------------------------------------
# Explanation layer
# ---------------------------------------------------------------------------

def test_headline_does_not_claim_full_verification_when_data_was_missing():
    from travel_booking.agents.explanation import build_explanation_for_option
    from travel_booking.agents.verification_agent import VerificationAgent

    hotel = _hotel(front_desk_24hr=None, front_desk_closes=None, max_occupancy=None)
    result = VerificationAgent().verify(hotel, _flight(), _constraints())
    exp = build_explanation_for_option(result)
    assert "couldn't be confirmed" in exp["headline"]


# ---------------------------------------------------------------------------
# Preference aggregator (the bandit)
# ---------------------------------------------------------------------------

def _member(**overrides):
    from travel_booking.agents.preference_aggregator import MemberPreference

    base = dict(
        date_range_start="2026-10-01", date_range_end="2026-10-20", party_size=1,
        budget_amount=200.0, budget_scope="per_night_hotel", required_amenities=["wifi"], nights=3,
    )
    base.update(overrides)
    return MemberPreference(**base)


@pytest.mark.parametrize("strategy,expected_budget,expected_nights", [
    ("conservative", 100.0, 2),   # min of both
    ("generous", 300.0, 6),       # max of both
    ("balanced", 200.0, 4),       # mean of both
])
def test_each_strategy_combines_budget_and_nights_as_documented(tmp_db, monkeypatch, strategy, expected_budget, expected_nights):
    import travel_booking.agents.preference_aggregator as agg_mod
    importlib.reload(agg_mod)
    monkeypatch.setattr(agg_mod, "get_connection", tmp_db.get_connection)
    monkeypatch.setattr(agg_mod, "_select_arm", lambda: strategy)

    # 2 and 6 chosen so the mean is a whole number -- avoids depending on
    # Python's banker's rounding at .5, which isn't what this test is about.
    members = [_member(budget_amount=100.0, nights=2), _member(budget_amount=300.0, nights=6)]
    out = agg_mod.aggregate(members)
    assert out["strategy"] == strategy
    assert out["budget_amount"] == pytest.approx(expected_budget)
    assert out["nights"] == expected_nights


def test_trip_length_is_independent_of_the_availability_window(tmp_db, monkeypatch):
    """Regression: nights used to be derived from the date window, so everyone
    free on one day became a 1-night trip and disjoint windows became 24."""
    import travel_booking.agents.preference_aggregator as agg_mod
    importlib.reload(agg_mod)
    monkeypatch.setattr(agg_mod, "get_connection", tmp_db.get_connection)
    monkeypatch.setattr(agg_mod, "_select_arm", lambda: "generous")

    same_day = [_member(date_range_start="2026-10-05", date_range_end="2026-10-05", nights=4)]
    assert agg_mod.aggregate(same_day)["nights"] == 4


def test_party_sizes_sum_across_members(tmp_db, monkeypatch):
    import travel_booking.agents.preference_aggregator as agg_mod
    importlib.reload(agg_mod)
    monkeypatch.setattr(agg_mod, "get_connection", tmp_db.get_connection)
    monkeypatch.setattr(agg_mod, "_select_arm", lambda: "balanced")

    out = agg_mod.aggregate([_member(party_size=2), _member(party_size=1)])
    assert out["party_size"] == 3


def test_amenities_intersect_for_conservative_and_union_for_generous(tmp_db, monkeypatch):
    import travel_booking.agents.preference_aggregator as agg_mod
    importlib.reload(agg_mod)
    monkeypatch.setattr(agg_mod, "get_connection", tmp_db.get_connection)

    members = [_member(required_amenities=["wifi", "pool"]), _member(required_amenities=["wifi", "gym"])]

    monkeypatch.setattr(agg_mod, "_select_arm", lambda: "conservative")
    assert agg_mod.aggregate(members)["required_amenities"] == ["wifi"]

    monkeypatch.setattr(agg_mod, "_select_arm", lambda: "generous")
    assert set(agg_mod.aggregate(members)["required_amenities"]) == {"wifi", "pool", "gym"}


def test_non_overlapping_dates_produce_a_visible_warning(tmp_db, monkeypatch):
    """Regression: this used to silently search a window nobody agreed on."""
    import travel_booking.agents.preference_aggregator as agg_mod
    importlib.reload(agg_mod)
    monkeypatch.setattr(agg_mod, "get_connection", tmp_db.get_connection)
    monkeypatch.setattr(agg_mod, "_select_arm", lambda: "balanced")

    members = [
        _member(date_range_start="2026-10-01", date_range_end="2026-10-05"),
        _member(date_range_start="2026-10-20", date_range_end="2026-10-25"),
    ]
    out = agg_mod.aggregate(members)
    assert any("don't actually overlap" in w for w in out["warnings"])


def test_bandit_reward_rate_drives_arm_selection(tmp_db, monkeypatch):
    """With exploration disabled, the arm with the better observed reward wins."""
    import travel_booking.agents.preference_aggregator as agg_mod
    importlib.reload(agg_mod)
    monkeypatch.setattr(agg_mod, "get_connection", tmp_db.get_connection)
    monkeypatch.setattr(agg_mod, "EPSILON", 0.0)
    monkeypatch.setattr(agg_mod.random, "random", lambda: 1.0)  # never explore

    conn = tmp_db.get_connection()
    conn.execute("INSERT INTO bandit_arm_stats VALUES ('conservative', 10, 9)")
    conn.execute("INSERT INTO bandit_arm_stats VALUES ('balanced', 10, 1)")
    conn.execute("INSERT INTO bandit_arm_stats VALUES ('generous', 10, 0)")
    conn.commit()
    conn.close()

    assert agg_mod._select_arm() == "conservative"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_password_is_salted_and_verifies(tmp_db, monkeypatch):
    import travel_booking.auth as auth
    monkeypatch.setattr(auth, "get_connection", tmp_db.get_connection)

    h1, s1 = auth.hash_password("hunter2000")
    h2, s2 = auth.hash_password("hunter2000")
    assert s1 != s2 and h1 != h2, "identical passwords must not share a hash"
    assert auth.verify_password("hunter2000", h1, s1)
    assert not auth.verify_password("wrong-password", h1, s1)


def test_signup_login_and_session_roundtrip(tmp_db, monkeypatch):
    import travel_booking.auth as auth
    monkeypatch.setattr(auth, "get_connection", tmp_db.get_connection)

    user = auth.create_user("alice", "password123", "Alice")
    assert auth.authenticate("alice", "password123")["id"] == user["id"]
    assert auth.authenticate("alice", "nope") is None

    token = auth.create_session(user["id"])
    assert auth.get_user_from_session(token)["username"] == "alice"
    auth.delete_session(token)
    assert auth.get_user_from_session(token) is None


def test_duplicate_username_is_rejected(tmp_db, monkeypatch):
    import travel_booking.auth as auth
    monkeypatch.setattr(auth, "get_connection", tmp_db.get_connection)

    auth.create_user("alice", "password123", "Alice")
    with pytest.raises(ValueError):
        auth.create_user("alice", "password123", "Other Alice")


def test_expired_session_is_rejected_and_purgeable(tmp_db, monkeypatch):
    import travel_booking.auth as auth
    monkeypatch.setattr(auth, "get_connection", tmp_db.get_connection)

    user = auth.create_user("alice", "password123", "Alice")
    token = auth.create_session(user["id"])
    conn = tmp_db.get_connection()
    conn.execute("UPDATE sessions SET expires_at = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()

    assert auth.get_user_from_session(token) is None
    assert tmp_db.purge_expired_sessions() == 1


def test_unknown_or_empty_session_token_is_rejected(tmp_db, monkeypatch):
    import travel_booking.auth as auth
    monkeypatch.setattr(auth, "get_connection", tmp_db.get_connection)

    assert auth.get_user_from_session(None) is None
    assert auth.get_user_from_session("") is None
    assert auth.get_user_from_session("not-a-real-token") is None


# ---------------------------------------------------------------------------
# Persistence layer
# ---------------------------------------------------------------------------

def test_schema_creates_every_expected_table(tmp_db):
    conn = tmp_db.get_connection()
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {
        "users", "sessions", "friendships", "saved_trips",
        "trip_groups", "trip_group_members", "trip_group_preferences", "bandit_arm_stats",
    } <= names


def test_trip_groups_has_last_strategy_so_reward_survives_restart(tmp_db):
    """Regression: the strategy lived only in an in-memory dict, so every
    restart silently broke the RL reward loop."""
    conn = tmp_db.get_connection()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(trip_groups)")}
    conn.close()
    assert "last_strategy" in cols


def test_migration_adds_last_strategy_to_an_older_database(tmp_path, monkeypatch):
    """An existing local DB must gain the column in place, not require deletion
    (which would throw away real accounts and saved trips)."""
    import sqlite3
    import travel_booking.db as db

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE trip_groups (id INTEGER PRIMARY KEY, name TEXT, owner_id INTEGER,
           destination_code TEXT, join_code TEXT, status TEXT, created_at REAL)"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()

    conn = db.get_connection()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(trip_groups)")}
    conn.close()
    assert "last_strategy" in cols
