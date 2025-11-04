# kufar_bot.py - ПОЛНАЯ ВЕРСИЯ ДЛЯ ПК
import os
import re
import json
import base64
import pandas as pd
from datetime import datetime
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# 🔑 НАСТРОЙКИ ИЗ ФАЙЛА .env
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_TOKEN = os.environ.get('HF_TOKEN')

nest_asyncio.apply()

class KufarSalesManager:
    def __init__(self):
        self.hf_client = self.setup_hf_client()
        self.common_mistakes = {
            'аблюк': 'абибок', 'абибог': 'абибок', 'абибак': 'абибок',
        }
        
        # Файлы базы данных
        self.orders_file = "kufar_orders.csv"
        self.products_file = "products.csv" 
        self.customers_file = "customers.csv"
        self.last_order_id = 0
        
        self.initialize_database()
        print("✅ Система управления с ИИ запущена на ПК!")

    def setup_hf_client(self):
        """Настраивает HF клиент"""
        try:
            if HF_TOKEN:
                client = OpenAI(
                    base_url="https://router.huggingface.co/v1",
                    api_key=HF_TOKEN,
                )
                print("✅ HF API подключен")
                return client
            else:
                print("❌ HF_TOKEN не настроен")
                return None
        except Exception as e:
            print(f"⚠️ Ошибка HF API: {e}")
            return None

    def initialize_database(self):
        """Инициализирует все файлы базы данных"""
        # Orders CSV
        orders_columns = [
            'ID', 'Номер_заказа', 'Дата_заказа', 'ФИО', 'Телефон', 'Адрес', 
            'Тип_доставки', 'Товар', 'Сумма', 'Примечание', 'Никнейм', 
            'Статус', 'Цена_из_подписи', 'Трек_номер'
        ]
        self.init_csv(self.orders_file, orders_columns)
        
        # Products CSV
        products_columns = ['ID', 'Название', 'Количество', 'Последняя_цена', 'Количество_продаж']
        self.init_csv(self.products_file, products_columns)
        
        # Customers CSV
        customers_columns = ['Телефон', 'ФИО', 'Количество_заказов', 'Общая_сумма', 'Последний_заказ']
        self.init_csv(self.customers_file, customers_columns)
        
        # Узнаем последний ID заказа
        self.last_order_id = self.get_last_order_id()

    def init_csv(self, filename, columns):
        """Инициализирует CSV файл если его нет"""
        if not os.path.exists(filename):
            df = pd.DataFrame(columns=columns)
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"✅ Создан файл {filename}")

    def get_last_order_id(self):
        """Получает последний ID заказа"""
        try:
            if os.path.exists(self.orders_file):
                df = pd.read_csv(self.orders_file)
                if not df.empty and 'ID' in df.columns:
                    return df['ID'].max()
            return 0
        except Exception as e:
            print(f"❌ Ошибка получения последнего ID: {e}")
            return 0

    # === ОСНОВНОЕ МЕНЮ ===
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает главное меню"""
        keyboard = [
            [InlineKeyboardButton("📤 Выгрузить заказы", callback_data="export_orders")],
            [InlineKeyboardButton("✍️ Ручной ввод заказа", callback_data="manual_order")],
            [InlineKeyboardButton("🔍 Найти заказ", callback_data="search_order")],
            [InlineKeyboardButton("📦 Управление остатками", callback_data="manage_stock")],
            [InlineKeyboardButton("📈 Статистика", callback_data="show_stats")],
            [InlineKeyboardButton("🤖 Тест ИИ", callback_data="test_ai")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.message.reply_text("🤖 SKUFAR PARSER - ГЛАВНОЕ МЕНЮ:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("🤖 SKUFAR PARSER - ГЛАВНОЕ МЕНЮ:", reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия кнопок меню"""
        query = update.callback_query
        await query.answer()
        
        handlers = {
            "export_orders": self.export_orders,
            "manual_order": self.start_manual_order,
            "search_order": self.start_search_order,
            "manage_stock": self.show_stock_management,
            "show_stats": self.show_statistics,
            "test_ai": self.test_ai,
        }
        
        if query.data in handlers:
            await handlers[query.data](update, context)

    # === ОБРАБОТКА СКРИНШОТОВ С ИИ ===
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает скриншоты через ИИ"""
        try:
            print("📸 Получен новый скриншот")
            await update.message.reply_text("🔄 Анализирую скриншот через ИИ...")
            
            photo_file = await update.message.photo[-1].get_file()
            image_data = await photo_file.download_as_bytearray()
            caption = update.message.caption or ""
            
            print(f"📝 Подпись к фото: {caption}")
            
            # Анализ скриншота через ИИ
            result = await self.analyze_with_ai(bytes(image_data))
            
            print(f"🎯 Результат анализа: {result}")
            
            if result and self.validate_extracted_data(result):
                print("✅ Анализ успешен, обрабатываю заказ...")
                
                # Обработка заказа
                order_data = await self.process_order_data(result, caption)
                
                # Сохранение заказа
                order_saved = self.save_order_to_db(order_data)
                
                # Обновление баз
                self.update_products_db(order_data['Товар'], order_data['Сумма'])
                self.update_customers_db(order_data)
                
                # Формирование ответа
                response = self.format_order_response(order_data, order_saved)
                await update.message.reply_text(response)
                
            else:
                print("❌ Анализ не удался")
                await update.message.reply_text(
                    "❌ Не удалось извлечь данные из скриншота.\n\n"
                    "✅ Используй ручной ввод заказа через меню!"
                )
            
        except Exception as e:
            print(f"💥 Ошибка обработки: {e}")
            await update.message.reply_text(f"❌ Ошибка обработки: {str(e)}")

    async def analyze_with_ai(self, image_data):
        """Анализирует изображение через ИИ"""
        if not self.hf_client:
            print("❌ HF клиент не настроен")
            return None
            
        try:
            base64_image = base64.b64encode(image_data).decode('utf-8')
            print("🖼️ Изображение закодировано в base64")
            
            prompt = """Проанализируй скриншот чата Kufar и извлеки данные:
- ФИО покупателя
- Телефон 
- Адрес доставки
- Название товара
- Сумму заказа
- Никнейм пользователя

Если данных нет - пиши "null"

Верни JSON: {"name": "...", "phone": "...", "address": "...", "product": "...", "amount": "...", "username": "..."}"""

            completion = self.hf_client.chat.completions.create(
                model="meta-llama/Meta-Llama-3.1-8B-Instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            response_text = completion.choices[0].message.content
            print(f"📨 Ответ от ИИ: {response_text}")
            
            # Парсим JSON из ответа
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                print("❌ Не удалось найти JSON в ответе")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка анализа ИИ: {e}")
            return None

    async def process_order_data(self, result, caption):
        """Обрабатывает данные заказа"""
        # Коррекция ошибок
        result = self.correct_common_errors(result)
        
        # Определение цены (приоритет у подписи)
        final_amount = self.extract_price_from_caption(caption) or result.get('amount', '')
        
        # Создание данных заказа
        self.last_order_id += 1
        order_data = {
            'ID': self.last_order_id,
            'Номер_заказа': f"ORD{self.last_order_id:04d}",
            'Дата_заказа': datetime.now().strftime('%Y-%m-%d'),
            'ФИО': result.get('name', ''),
            'Телефон': result.get('phone', ''),
            'Адрес': result.get('address', ''),
            'Тип_доставки': self.detect_delivery_type(result, caption),
            'Товар': result.get('product', ''),
            'Сумма': final_amount,
            'Примечание': self.process_notes(caption, result),
            'Никнейм': result.get('username', ''),
            'Статус': 'Новый',
            'Цена_из_подписи': 'Да' if self.extract_price_from_caption(caption) else 'Нет',
            'Трек_номер': ''
        }
        
        return order_data

    def extract_price_from_caption(self, caption):
        """Извлекает цену из подписи к фото"""
        if not caption:
            return None
            
        price_pattern = r'(\d+)[\s]*[рр]'
        match = re.search(price_pattern, caption)
        
        if match:
            return f"{match.group(1)} р."
        
        return None

    def correct_common_errors(self, extracted_data):
        """Исправляет частые ошибки распознавания в ФИО"""
        if not extracted_data or not extracted_data.get('name'):
            return extracted_data
        
        original_name = extracted_data['name']
        name = original_name.lower()
        
        for wrong, correct in self.common_mistakes.items():
            if wrong in name:
                name = name.replace(wrong, correct)
        
        if name != original_name.lower():
            name = ' '.join(word.capitalize() for word in name.split())
            extracted_data['name'] = name
        
        return extracted_data

    def validate_extracted_data(self, data):
        """Проверяет качество распознанных данных"""
        if not data:
            return False
        
        validation_score = 0
        required_fields = ['name', 'phone', 'address']
        
        for field in required_fields:
            value = data.get(field)
            if value and value != "null" and len(str(value).strip()) > 2:
                validation_score += 1
        
        return validation_score >= 2

    def detect_delivery_type(self, data, caption=""):
        """Определяет тип доставки"""
        full_text = ""
        if data.get('address'): 
            full_text += " " + data['address'].lower()
        if caption: 
            full_text += " " + caption.lower()
        
        euro_keywords = ['евро', 'отд.', 'отд ', 'отделение', 'европочт']
        if any(keyword in full_text for keyword in euro_keywords): 
            return "ЕвроПочта"
        if 'почта' in full_text: 
            return "Белпочта"
        return "Не указан"

    def process_notes(self, caption, result):
        """Обрабатывает примечания"""
        notes = []
        if caption:
            delivery_terms = ['бесплатно', 'за мой счет', 'отправка за мой счет']
            for term in delivery_terms:
                if term in caption.lower(): 
                    notes.append(term)
        
        return '; '.join(notes) if notes else ''

    def save_order_to_db(self, order_data):
        """Сохраняет заказ в базу"""
        try:
            if os.path.exists(self.orders_file):
                df = pd.read_csv(self.orders_file)
            else:
                df = pd.DataFrame(columns=[
                    'ID', 'Номер_заказа', 'Дата_заказа', 'ФИО', 'Телефон', 'Адрес',
                    'Тип_доставки', 'Товар', 'Сумма', 'Примечание', 'Никнейм',
                    'Статус', 'Цена_из_подписи', 'Трек_номер'
                ])
            
            df = pd.concat([df, pd.DataFrame([order_data])], ignore_index=True)
            df.to_csv(self.orders_file, index=False, encoding='utf-8-sig')
            
            print(f"✅ Заказ #{order_data['Номер_заказа']} сохранен в базу")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка сохранения заказа: {e}")
            return False

    def update_products_db(self, product_name, price):
        """Обновляет базу товаров"""
        try:
            if not product_name or product_name == 'null':
                return
                
            if os.path.exists(self.products_file):
                df = pd.read_csv(self.products_file)
            else:
                df = pd.DataFrame(columns=['ID', 'Название', 'Количество', 'Последняя_цена', 'Количество_продаж'])
            
            if not df.empty and product_name in df['Название'].values:
                idx = df[df['Название'] == product_name].index[0]
                current_qty = df.at[idx, 'Количество']
                if pd.notna(current_qty) and current_qty > 0:
                    df.at[idx, 'Количество'] = current_qty - 1
                df.at[idx, 'Количество_продаж'] += 1
                df.at[idx, 'Последняя_цена'] = price
            else:
                new_id = df['ID'].max() + 1 if not df.empty else 1
                new_product = {
                    'ID': new_id,
                    'Название': product_name,
                    'Количество': 0,
                    'Последняя_цена': price,
                    'Количество_продаж': 1
                }
                df = pd.concat([df, pd.DataFrame([new_product])], ignore_index=True)
            
            df.to_csv(self.products_file, index=False, encoding='utf-8-sig')
            print(f"✅ База товаров обновлена: {product_name}")
            
        except Exception as e:
            print(f"❌ Ошибка обновления базы товаров: {e}")

    def update_customers_db(self, order_data):
        """Обновляет базу клиентов"""
        try:
            if os.path.exists(self.customers_file):
                df = pd.read_csv(self.customers_file)
            else:
                df = pd.DataFrame(columns=['Телефон', 'ФИО', 'Количество_заказов', 'Общая_сумма', 'Последний_заказ'])
            
            phone = order_data['Телефон']
            if not phone or phone == 'null':
                return
                
            amount = 0
            if order_data['Сумма']:
                numbers = re.findall(r'\d+', str(order_data['Сумма']))
                if numbers:
                    amount = int(numbers[0])
            
            if not df.empty and phone in df['Телефон'].values:
                idx = df[df['Телефон'] == phone].index[0]
                df.at[idx, 'Количество_заказов'] += 1
                df.at[idx, 'Общая_сумма'] += amount
                df.at[idx, 'Последний_заказ'] = order_data['Дата_заказа']
            else:
                new_customer = {
                    'Телефон': phone,
                    'ФИО': order_data['ФИО'],
                    'Количество_заказов': 1,
                    'Общая_сумма': amount,
                    'Последний_заказ': order_data['Дата_заказа']
                }
                df = pd.concat([df, pd.DataFrame([new_customer])], ignore_index=True)
            
            df.to_csv(self.customers_file, index=False, encoding='utf-8-sig')
            print(f"✅ База клиентов обновлена: {order_data['ФИО']}")
            
        except Exception as e:
            print(f"❌ Ошибка обновления базы клиентов: {e}")

    def format_order_response(self, order_data, order_saved):
        """Форматирует ответ о заказе"""
        response = f"""✅ **ЗАКАЗ #{order_data['Номер_заказа']} СОЗДАН ИИ**

👤 **ФИО:** {order_data['ФИО']}
📞 **Телефон:** {order_data['Телефон']}
📍 **Адрес:** {order_data['Адрес']}
🚚 **Доставка:** {order_data['Тип_доставки']}
📦 **Товар:** {order_data['Товар']}
💰 **Сумма:** {order_data['Сумма']}
👥 **Никнейм:** {order_data['Никнейм']}
📝 **Примечание:** {order_data['Примечание']}"""

        if order_saved:
            response += f"\n\n💾 **Сохранено в базу**"
        
        return response

    # === ДРУГИЕ ФУНКЦИИ (экспорт, поиск, статистика и т.д.) ===
    async def export_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выгружает заказы в файл"""
        try:
            if os.path.exists(self.orders_file):
                await update.callback_query.message.reply_document(
                    document=open(self.orders_file, 'rb'),
                    filename="kufar_orders.csv"
                )
                await update.callback_query.message.reply_text("✅ Файл отправлен")
            else:
                await update.callback_query.message.reply_text("📊 Файл заказов пуст")
        except Exception as e:
            await update.callback_query.message.reply_text(f"❌ Ошибка: {e}")

    async def start_manual_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс ручного ввода заказа"""
        await update.callback_query.message.reply_text(
            "✍️ **РУЧНОЙ ВВОД ЗАКАЗА**\n\n"
            "Введи данные заказа в формате:\n"
            "ФИО=Иванов Иван Иванович\n"
            "Телефон=+375291234567\n" 
            "Адрес=г.Минск, ул.Ленина 1\n"
            "Товар=Подстаканник Golf 4\n"
            "Сумма=35 р.\n\n"
            "Или /cancel для отмены"
        )
        context.user_data['awaiting_manual_order'] = True

    async def process_manual_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_text: str):
        """Обрабатывает ручной ввод заказа"""
        try:
            order_data = {}
            for line in order_text.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    order_data[key] = value

            self.last_order_id += 1
            new_order = {
                'ID': self.last_order_id,
                'Номер_заказа': f"ORD{self.last_order_id:04d}",
                'Дата_заказа': datetime.now().strftime('%Y-%m-%d'),
                'ФИО': order_data.get('ФИО', ''),
                'Телефон': order_data.get('Телефон', ''),
                'Адрес': order_data.get('Адрес', ''),
                'Тип_доставки': self.detect_delivery_type({'address': order_data.get('Адрес', '')}, ''),
                'Товар': order_data.get('Товар', ''),
                'Сумма': order_data.get('Сумма', ''),
                'Примечание': '',
                'Никнейм': '',
                'Статус': 'Новый',
                'Цена_из_подписи': 'Нет',
                'Трек_номер': ''
            }

            order_saved = self.save_order_to_db(new_order)
            self.update_products_db(new_order['Товар'], new_order['Сумма'])
            self.update_customers_db(new_order)

            response = f"""✅ **ЗАКАЗ #{new_order['Номер_заказа']} СОЗДАН**

👤 **ФИО:** {new_order['ФИО']}
📞 **Телефон:** {new_order['Телефон']}
📍 **Адрес:** {new_order['Адрес']}
🚚 **Доставка:** {new_order['Тип_доставки']}
📦 **Товар:** {new_order['Товар']}
💰 **Сумма:** {new_order['Сумма']}"""

            await update.message.reply_text(response)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка создания заказа: {e}")

    async def start_search_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс поиска заказа"""
        await update.callback_query.message.reply_text(
            "🔍 **ПОИСК ЗАКАЗА**\n\n"
            "Введи для поиска:\n"
            "• ФИО (полностью или часть)\n" 
            "• Номер заказа (ORD0001)\n"
            "• Телефон (полностью или часть)\n"
            "• Товар\n\n"
            "Или /cancel для отмены"
        )
        context.user_data['awaiting_search'] = True

    async def perform_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, search_query: str):
        """Выполняет поиск заказов"""
        try:
            if not os.path.exists(self.orders_file):
                await update.message.reply_text("📊 База заказов пуста")
                return

            df = pd.read_csv(self.orders_file)
            if df.empty:
                await update.message.reply_text("📊 База заказов пуста")
                return

            mask = (
                df['ФИО'].str.contains(search_query, case=False, na=False) |
                df['Телефон'].str.contains(search_query, case=False, na=False) |
                df['Номер_заказа'].str.contains(search_query.upper(), case=False, na=False) |
                df['Товар'].str.contains(search_query, case=False, na=False)
            )
            
            results = df[mask]
            
            if results.empty:
                await update.message.reply_text("❌ Заказы не найдены")
                return

            response = f"🔍 **НАЙДЕНО ЗАКАЗОВ:** {len(results)}\n\n"
            
            for _, order in results.iterrows():
                response += f"""📦 **#{order['Номер_заказа']}** | {order['Дата_заказа']}
👤 {order['ФИО']} | 📞 {order['Телефон']}
📦 {order['Товар']} | 💰 {order['Сумма']}
📍 {order['Адрес']}
────────────────────
"""
            
            await update.message.reply_text(response)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка поиска: {e}")

    async def show_stock_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает управление остатками"""
        try:
            if os.path.exists(self.products_file):
                df = pd.read_csv(self.products_file)
                if not df.empty:
                    response = "📦 **ТОВАРЫ В НАЛИЧИИ:**\n\n"
                    for _, product in df.iterrows():
                        response += f"• {product['Название']}: {product['Количество']} шт. ({product['Количество_продаж']} продаж)\n"
                    await update.callback_query.message.reply_text(response)
                else:
                    await update.callback_query.message.reply_text("📦 База товаров пуста")
            else:
                await update.callback_query.message.reply_text("📦 База товаров не создана")
        except Exception as e:
            await update.callback_query.message.reply_text(f"❌ Ошибка: {e}")

    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает статистику"""
        try:
            stats = self.calculate_statistics()
            response = f"""📈 **СТАТИСТИКА ПРОДАЖ:**

📊 Всего заказов: {stats['total_orders']}
💰 Общая сумма: {stats['total_revenue']} р.
👥 Уникальных клиентов: {stats['unique_customers']}
📦 Товаров в базе: {stats['total_products']}

🔥 **Популярные товары:**
{stats['top_products']}"""
            
            await update.callback_query.message.reply_text(response)
            
        except Exception as e:
            await update.callback_query.message.reply_text(f"❌ Ошибка: {e}")

    def calculate_statistics(self):
        """Рассчитывает статистику"""
        stats = {
            'total_orders': 0,
            'total_revenue': 0,
            'unique_customers': 0,
            'total_products': 0,
            'top_products': 'Нет данных'
        }
        
        try:
            if os.path.exists(self.orders_file):
                df = pd.read_csv(self.orders_file)
                if not df.empty:
                    stats['total_orders'] = len(df)
                    total_revenue = 0
                    for amount in df['Сумма']:
                        if pd.notna(amount) and amount:
                            numbers = re.findall(r'\d+', str(amount))
                            if numbers:
                                total_revenue += int(numbers[0])
                    stats['total_revenue'] = total_revenue
            
            if os.path.exists(self.customers_file):
                df = pd.read_csv(self.customers_file)
                if not df.empty:
                    stats['unique_customers'] = len(df)
            
            if os.path.exists(self.products_file):
                df = pd.read_csv(self.products_file)
                if not df.empty:
                    stats['total_products'] = len(df)
                    top_products = df.nlargest(3, 'Количество_продаж')
                    if not top_products.empty:
                        stats['top_products'] = '\n'.join(
                            [f"• {row['Название']}: {row['Количество_продаж']} продаж" 
                             for _, row in top_products.iterrows()]
                        )
                    
        except:
            pass
            
        return stats

    async def test_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Тестирует ИИ"""
        await update.callback_query.message.reply_text(
            "🤖 **ИИ СИСТЕМА АКТИВНА**\n\n"
            "Отправь скриншот чата Kufar для автоматического анализа:\n"
            "• ФИО покупателя\n"
            "• Телефон\n" 
            "• Адрес доставки\n"
            "• Товар\n"
            "• Сумму заказа\n\n"
            "ИИ работает на полную мощность! 🚀"
        )

    # === ОБРАБОТКА ТЕКСТА ===
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текстовые сообщения"""
        text = update.message.text.strip()
        
        if text.lower() == '/cancel':
            for key in [k for k in context.user_data.keys() if k.startswith('awaiting')]:
                del context.user_data[key]
            await update.message.reply_text("❌ Действие отменено")
            return

        if context.user_data.get('awaiting_search'):
            del context.user_data['awaiting_search']
            await self.perform_search(update, context, text)
        elif context.user_data.get('awaiting_manual_order'):
            del context.user_data['awaiting_manual_order']
            await self.process_manual_order(update, context, text)
        elif text == '/menu':
            await self.show_main_menu(update, context)
        elif text == '/start':
            await self.start_command(update, context)
        else:
            await update.message.reply_text("Отправь скриншот или /menu для меню")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 **SKUFAR PARSER** запущен на ПК!\n\nПолный доступ к ИИ анализу скриншотов! 🚀")
        await self.show_main_menu(update, context)

# ЗАПУСК БОТА
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    bot_manager = KufarSalesManager()
    
    application.add_handler(MessageHandler(filters.COMMAND & filters.Regex("start"), bot_manager.start_command))
    application.add_handler(MessageHandler(filters.COMMAND & filters.Regex("menu"), bot_manager.start_command))
    application.add_handler(MessageHandler(filters.COMMAND & filters.Regex("cancel"), bot_manager.handle_text))
    application.add_handler(CallbackQueryHandler(bot_manager.handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, bot_manager.handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_manager.handle_text))
    
    print("🚀 Бот запускается на ПК...")
    print("🤖 Полный доступ к ИИ API!")
    print("📊 Все функции активны")
    print("🔍 Ожидаю команды /start в Telegram...")
    
    application.run_polling()

if __name__ == "__main__":
    main()