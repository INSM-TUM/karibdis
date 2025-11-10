
# filepath: c:\Users\wwwdu\Desktop\___BPM_Hiwi\karibdis\src\tests\conftest.py
import sys
from pathlib import Path

# ensure the project 'src' directory is on sys.path for test collection
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))