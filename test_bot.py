import os
import time
import pyautogui
import requests
import base64
from dotenv import load_dotenv
from pathlib import Path

# Загружаем ключ
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("❌ КЛЮЧ НЕ НАЙДЕН!")
    exit()

print(f"✅ Ключ загружен: {OPENROUTER_API_KEY[:10]}...")

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def test_ai_vision():
    print("🎯 Подготовка... Сверни лишние окна, у тебя есть 3 секунды!")
    time.sleep(3)
    
    screenshot_path = Path(__file__).parent / "debug_screen.png"
    
    try:
        # Скриншот
        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_path)
        print(f"✅ Скриншот сохранен! Размер: {os.path.getsize(screenshot_path)} байт")
        
        # Кодируем изображение
        base64_image = encode_image(screenshot_path)
        
        # OpenRouter API
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Sniper Bot"
        }
        
        # ТОЛЬКО ОДНА МОДЕЛЬ - arcee-ai/trinity-large-preview:free
        model_name = "arcee-ai/trinity-large-preview:free"
        
        print(f"\n🤖 Использую модель: {model_name}")
        
        # Для текстовой модели - отправляем описание
        content = f"Какой навык лучше выбрать из трех, какой сильней будет в игре?: {os.path.getsize(screenshot_path)} байт"
        
        data = {
            "model": model_name,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 500
        }
        
        try:
            print("⏳ Отправляю запрос...")
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                print("\n" + "="*60)
                print(f"✅ ОТВЕТ ОТ {model_name}:")
                print("="*60)
                print(result['choices'][0]['message']['content'])
                print("="*60)
            else:
                print(f"❌ Ошибка {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"❌ Исключение: {e}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    finally:
        print("\n💡 Нажмите Enter для выхода...")
        input()

if __name__ == "__main__":
    test_ai_vision()