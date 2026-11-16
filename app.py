# -*- coding: utf-8 -*-
#
# Планувальник подорожей на основі Gemini API.
# PoC-проєкт для семінару з курсу «Хмарні обчислення».
#
# Користувач вводить місто, кількість днів і свої вподобання,
# а Gemini генерує детальний маршрут по днях.
#
# Запуск:  streamlit run app.py
#
import os
import time

import streamlit as st
from google import genai
from google.genai import errors

# Моделі безкоштовного тарифу Gemini API, від найкращої для демо до запасних.
# Flash-Lite: 15 запитів/хв і 500 запитів/день; Flash: 5 запитів/хв і 20 запитів/день.
MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
]
RETRIES = 3          # скільки разів пробувати одну модель, якщо вона перевантажена
BUSY_CODES = (429, 500, 503, 504)   # тимчасові помилки: є сенс почекати й повторити


def generate_with_fallback(client, prompt, models):
    """Надсилає запит у першу модель зі списку.

    Якщо модель тимчасово перевантажена (503) або вичерпано ліміт (429),
    чекає й повторює. Якщо модель недоступна або так і не відповіла,
    переходить до наступної. Повертає (текст відповіді, назва моделі).
    """
    last_error = None
    for model in models:
        for attempt in range(RETRIES):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                return response.text, model
            except errors.APIError as e:
                last_error = e
                if e.code in (401, 403):
                    raise                          # неправильний ключ: інші моделі не допоможуть
                if e.code in BUSY_CODES and attempt < RETRIES - 1:
                    time.sleep(2 * (attempt + 1))  # 2 с, потім 4 с
                    continue
                break                              # 404 / 400 або спроби скінчилися: наступна модель
    raise last_error


# ---- Налаштування сторінки ----
st.set_page_config(page_title="Планувальник подорожей", page_icon="🗺️")
st.title("🗺️ Планувальник подорожей")
st.caption("Складає маршрут по днях за допомогою Gemini API")

# ---- API-ключ ----
# Ключ береться безкоштовно в Google AI Studio (aistudio.google.com/apikey).
# Можна задати через змінну середовища GEMINI_API_KEY або ввести у полі ліворуч.
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API key", type="password",
                                    help="Отримати: aistudio.google.com/apikey")

# ---- Вибір моделі ----
# Обрана модель пробується першою, решта списку залишається запасними.
first = st.sidebar.selectbox("Модель Gemini", MODELS, index=0)
models = [first] + [m for m in MODELS if m != first]

# ---- Форма введення ----
col1, col2 = st.columns(2)
city = col1.text_input("Куди їдемо?", placeholder="напр. Львів, Рим, Токіо")
days = col2.number_input("Скільки днів?", min_value=1, max_value=14, value=3)

interests = st.multiselect(
    "Що тобі цікаво?",
    ["Історія та архітектура", "Музеї та мистецтво", "Їжа та ресторани",
     "Природа та парки", "Нічне життя", "Шопінг", "Для дітей", "Бюджетно"],
    default=["Історія та архітектура", "Їжа та ресторани"],
)
pace = st.radio("Темп подорожі", ["Розслаблений", "Помірний", "Насичений"],
                index=1, horizontal=True)

# ---- Генерація маршруту ----
if st.button("Скласти маршрут", type="primary"):
    if not api_key:
        st.error("Спочатку введи Gemini API key (ліворуч у бічній панелі).")
    elif not city:
        st.error("Вкажи, куди їдемо.")
    else:
        prompt = (
            "Ти досвідчений гід. Склади детальний маршрут подорожі українською мовою.\n"
            "Місто/напрямок: %s\n"
            "Кількість днів: %d\n"
            "Інтереси: %s\n"
            "Темп: %s\n\n"
            "Формат відповіді: для кожного дня окремий заголовок (## День N), "
            "а всередині пункти Ранок / День / Вечір з конкретними місцями "
            "і короткою порадою (що спробувати з їжі, коли краще йти). "
            "В кінці додай блок «Поради» (3-4 практичні підказки)."
            % (city, days, ", ".join(interests) if interests else "будь-що", pace)
        )

        with st.spinner("Gemini складає маршрут..."):
            try:
                client = genai.Client(api_key=api_key)
                text, used_model = generate_with_fallback(client, prompt, models)
                st.caption("Відповіла модель: %s" % used_model)
                st.markdown(text)
                st.download_button("⬇️ Зберегти маршрут (.md)",
                                   text, file_name="marshrut.md")
            except errors.APIError as e:
                if e.code in (401, 403):
                    st.error("Ключ API не підходить. Перевір його в aistudio.google.com/apikey.")
                elif e.code == 429:
                    st.error("Вичерпано безкоштовний ліміт запитів. Спробуй за хвилину "
                             "або завтра (денний ліміт оновлюється опівночі за тихоокеанським часом).")
                else:
                    st.error("Усі моделі зараз недоступні (код %s). Спробуй ще раз за хвилину." % e.code)
            except Exception as e:
                st.error("Помилка запиту до Gemini API: %s" % e)
