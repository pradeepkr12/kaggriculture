"""sol8 entry: graduated-throttle planner + Hungarian labor assignment
(farmlib_ph.py mechanics + planner.py hooks). This is the canonical sol8 agent."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import planner


def build_agent(verbose=False):
    return planner.build_agent(verbose=verbose, use_sell=True, use_plan=True, hungarian=True)
