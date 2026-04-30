"""Tests for InformationTracker: entity extraction improvements."""
import pytest
from app.services.agent.information_tracker import InformationTracker


class TestEntityExtraction:
    """Test the improved entity extraction with CJK stopword filtering."""

    def test_json_entity_extraction(self):
        """Entities should be extracted from structured JSON results."""
        tracker = InformationTracker()
        result = '[{"name": "张伟", "type": "人物"}, {"name": "华信理财", "type": "组织"}]'
        entities = tracker._extract_entities(result)
        assert "张伟" in entities
        assert "华信理财" in entities

    def test_stopwords_filtered_out(self):
        """Common Chinese function words should NOT be extracted as entities."""
        tracker = InformationTracker()
        # Text that would previously match [一-鿿]{2,4} but is not an entity
        result = "这是因为了一个是的可以已经将会他们的之后之前同时然后以及及其或者还是"
        entities = tracker._text_extract_entities(result)
        # All of these should be filtered out by stopwords
        for word in ["这是因为", "了一个", "是的", "可以", "已经", "将会", "他们的",
                     "之后", "之前", "同时", "然后", "以及", "及其", "或者", "还是"]:
            assert word not in entities

    def test_real_entities_preserved(self):
        """Real entity names should be preserved after stopword filtering."""
        tracker = InformationTracker()
        # Use space-separated names so each matches individually
        result = "张伟 刘强 华信理财 王芳"
        entities = tracker._text_extract_entities(result)
        # These proper names should NOT be filtered
        assert "张伟" in entities
        assert "刘强" in entities

    def test_particle_only_sequences_filtered(self):
        """Sequences of only common particles should be filtered."""
        tracker = InformationTracker()
        result = "的了是在和与或就着过们这那"
        entities = tracker._text_extract_entities(result)
        # This should produce no entities
        assert len(entities) == 0


class TestInformationTrackerSaturation:
    """Test saturation detection."""

    def test_not_saturated_with_few_calls(self):
        """Should not report saturation before minimum calls."""
        tracker = InformationTracker(min_recent_calls=5)
        tracker.record_gain("test", "张伟 华信理财")
        tracker.record_gain("test", "刘强 王芳")
        tracker.record_gain("test", "赵刚 孙丽")
        assert tracker.is_saturated() == False

    def test_saturated_when_no_new_entities(self):
        """Should report saturation when recent calls find no new entities."""
        tracker = InformationTracker(min_recent_calls=3)
        tracker.record_gain("test", "nothing here")
        tracker.record_gain("test", "nothing here")
        tracker.record_gain("test", "nothing here")
        assert tracker.is_saturated() == True

    def test_not_saturated_with_new_findings(self):
        """Should NOT report saturation when new entities are still being found."""
        tracker = InformationTracker(min_recent_calls=3)
        tracker.record_gain("test", "张伟")
        tracker.record_gain("test", "刘强")
        tracker.record_gain("test", "王芳")
        assert tracker.is_saturated() == False

    def test_stats_return(self):
        """Stats should return correct counts."""
        tracker = InformationTracker()
        tracker.record_gain("test", '[{"name": "张伟"}]')
        tracker.record_gain("test", '[{"name": "刘强"}]')
        stats = tracker.get_stats()
        assert stats["total_entities"] >= 2
        assert "recent_gains" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
