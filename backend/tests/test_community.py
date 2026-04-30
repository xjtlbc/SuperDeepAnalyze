"""Tests for Louvain community detection."""
from app.services.retrieval.community import assign_communities


def test_community_same_group():
    entities = [
        {"id": "e1", "relations": [{"target_id": "e2", "confidence": 0.9}]},
        {"id": "e2", "relations": [{"target_id": "e1", "confidence": 0.9}]},
    ]
    result = assign_communities(entities)
    assert result["e1"] == result["e2"], f"e1({result['e1']}) != e2({result['e2']})"


def test_community_separate():
    entities = [
        {"id": "e1", "relations": []},
        {"id": "e2", "relations": []},
    ]
    result = assign_communities(entities)
    assert result["e1"] != result["e2"], "Isolated entities should have different communities"


def test_empty_entities():
    result = assign_communities([])
    assert result == {}


def test_three_entities_mixed():
    entities = [
        {"id": "e1", "relations": [{"target_id": "e2", "confidence": 0.9}]},
        {"id": "e2", "relations": [{"target_id": "e1", "confidence": 0.9}]},
        {"id": "e3", "relations": []},
    ]
    result = assign_communities(entities)
    assert result["e1"] == result["e2"], "e1 and e2 should share community"
    assert result["e3"] != result["e1"], "e3 should be separate"


if __name__ == "__main__":
    test_community_same_group()
    print("test_community_same_group PASSED")
    test_community_separate()
    print("test_community_separate PASSED")
    test_empty_entities()
    print("test_empty_entities PASSED")
    test_three_entities_mixed()
    print("test_three_entities_mixed PASSED")
    print("All community tests PASSED")
