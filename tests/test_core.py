"""Tests for Driftguard."""
from src.core import Driftguard
def test_init(): assert Driftguard().get_stats()["ops"] == 0
def test_op(): c = Driftguard(); c.process(x=1); assert c.get_stats()["ops"] == 1
def test_multi(): c = Driftguard(); [c.process() for _ in range(5)]; assert c.get_stats()["ops"] == 5
def test_reset(): c = Driftguard(); c.process(); c.reset(); assert c.get_stats()["ops"] == 0
def test_service_name(): c = Driftguard(); r = c.process(); assert r["service"] == "driftguard"
