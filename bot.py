import subprocess
import sys

# Устанавливаем пакет maxgram
subprocess.check_call([sys.executable, "-m", "pip", "install", "maxgram"])

print("Пакет maxgram успешно установлен.")
