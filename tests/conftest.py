"""Testler hangi klasörden çalıştırılırsa çalıştırılsın repo kökü import yolunda olsun
(`from llm import ...`, `from stats import ...` vb. çalışsın)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
