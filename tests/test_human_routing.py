from app.agents.supervisor import SupervisorAgent


def test_human_handoff_bypasses_retrieval_and_generation():
    assert SupervisorAgent._route_after_analysis({"intent": "contact_human_agent"}) == "human"
    assert SupervisorAgent._route_after_analysis({"intent": "settings"}) == "ok"
    assert SupervisorAgent._route_after_analysis({"error": "provider unavailable"}) == "error"
