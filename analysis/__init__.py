"""Analysis module for handling both demo and real implementations."""

from analysis.base import Analyzer
from analysis.demo import DemoAnalyzer
from analysis.real import RealAnalyzer

__all__ = ['Analyzer', 'DemoAnalyzer', 'RealAnalyzer']
