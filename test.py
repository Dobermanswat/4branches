import os
from dotenv import load_dotenv
from pathlib import Path

print("🔍 ПРОВЕРКА КЛЮЧА DEEPSEEK")
print("="*50)

# Текущая папка
current_dir = Path(__file__).parent.absolute()
print(f"📁 Текущая папка: {current_dir}")

# Проверяем .env файл
env_file = current_dir / '.env'
print(f"📄 Путь к .env: {env_file}")

if env_file.exists():
    print(f"✅ Файл .env существует")
    
    # Читаем файл напрямую (без load_dotenv)
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        print(f"📝 Содержимое: {content}")
else:
    print(f"❌ Файл .env НЕ НАЙДЕН!")

# Загружаем через dotenv
print("\n🔄 Загружаю через load_dotenv()...")
load_dotenv(env_file)
api_key = os.getenv("DEEPSEEK_API_KEY")

if api_key:
    print(f"✅ КЛЮЧ ЗАГРУЖЕН!")
    print(f"🔑 Первые 10 символов: {api_key[:10]}")
    print(f"🔑 Последние 5 символов: {api_key[-5:]}")
    print(f"📏 Длина ключа: {len(api_key)}")
    
    # Проверяем формат
    if api_key.startswith('sk-'):
        print(f"✅ Ключ начинается с 'sk-' (правильно)")
    else:
        print(f"❌ Ключ должен начинаться с 'sk-', а начинается с '{api_key[:3]}'")
else:
    print(f"❌ КЛЮЧ НЕ ЗАГРУЖЕН!")
    print(f"📊 Значение os.getenv: {api_key}")

print("\n" + "="*50)
print("💡 Нажмите Enter для выхода...")
input()