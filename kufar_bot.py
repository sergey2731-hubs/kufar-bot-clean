# kufar_bot.py - ОБНОВЛЕННАЯ ВЕРСИЯ БЕЗ PILLOW
import os
import re
import json
import base64
import csv
from datetime import datetime
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from openai import OpenAI

# 🔑 API КЛЮЧИ
BOT_TOKEN = os.environ.get('BOT_TOKEN', "8521153944:AAEMBg2JGMM6fNleRBIOmLSrKOWqBeWoGP0")
HF_TOKEN = os.environ.get('HF_TOKEN', "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")

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
        print("✅ Система управления с ИИ запущена!")

    def setup_hf_client(self):
        """Настраивает HF клиент"""
        try:
            if HF_TOKEN:
                client = OpenAI(
                    base_url="https://router.huggingface.co/hf-inference/v1",
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
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
            print(f"✅ Создан файл {filename}")

    def get_last_order_id(self):
        """Получает последний ID заказа"""
        try:
            if os.path.exists(self.orders_file):
                with open(self.orders_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if rows:
                        return max(int(row['ID']) for row in rows if row['ID'].isdigit())
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
        }
        
        if query.data in handlers:
            await handlers[query.data](update, context)

    # === ОБРАБОТКА СКРИНШОТОВ ===
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает скриншоты - просим прислать текст"""
        try:
            await update.message.reply_text(
                "📸 **Скриншот получен!**\n\n"
                "📝 **Пришли текст из скриншота сообщением** - я его проанализирую и создам заказ автоматически!\n\n"
                "💡 *Просто выдели и скопируй текст из чата Kufar*"
            )
            
            # Помечаем что ждем текст от пользователя
            context.user_data['awaiting_screenshot_text'] = True
            
        except Exception as e:
            await update.message.reply_text("❌ Ошибка обработки фото")

    # === АНАЛИЗ ТЕКСТА С OPENAI ===
    async def analyze_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Анализирует текстовые сообщения с данными заказа"""
        try:
            is_from_screenshot = context.user_data.get('awaiting_screenshot_text', False)
            
            if is_from_screenshot:
                del context.user_data['awaiting_screenshot_text']
                await update.message.reply_text("🔄 Анализирую текст из скриншота через ИИ...")
            else:
                await update.message.reply_text("🔄 Анализирую текст через ИИ...")
            
            # 🔥 ИСПОЛЬЗУЕМ OPENAI ДЛЯ АНАЛИЗА ТЕКСТА
            parsed_data = await self.analyze_text_with_openai(text)
            
            if parsed_data and self.validate_extracted_data(parsed_data):
                await update.message.reply_text("✅ Данные распознаны! Создаю заказ...")
                
                # Создаем заказ
                order_data = await self.process_order_data(parsed_data, "")
                order_saved = self.save_order_to_db(order_data)
                
                # Обновляем базы
                self.update_products_db(order_data['Товар'], order_data['Сумма'])
                self.update_customers_db(order_data)
                
                response = self.format_order_response(order_data, order_saved)
                await update.message.reply_text(response)
                
            else:
                # Если ИИ не справился, пробуем обычный парсинг
                parsed_data = self.parse_text_data(text)
                
                if self.validate_extracted_data(parsed_data):
                    await update.message.reply_text("✅ Данные распознаны! Создаю заказ...")
                    
                    order_data = await self.process_order_data(parsed_data, "")
                    order_saved = self.save_order_to_db(order_data)
                    self.update_products_db(order_data['Товар'], order_data['Сумма'])
                    self.update_customers_db(order_data)
                    
                    response = self.format_order_response(order_data, order_saved)
                    await update.message.reply_text(response)
                else:
                    await update.message.reply_text(
                        "❌ Не удалось распознать данные автоматически.\n\n"
                        "📋 **Отправь данные вручную в формате:**\n"
                        "```\n"
                        "ФИО: Иванов Иван Иванович\n"
                        "Телефон: +375291234567\n"
                        "Адрес: г.Минск, ул.Ленина 1\n"
                        "Товар: Подстаканник Golf 4\n"
                        "Сумма: 35 р.\n"
                        "```\n"
                        "Или используй кнопку '✍️ Ручной ввод заказа' в меню"
                    )
                    
        except Exception as e:
            print(f"❌ Ошибка анализа текста: {e}")
            await update.message.reply_text("❌ Ошибка анализа. Попробуй еще раз или используй ручной ввод.")

    async def analyze_text_with_openai(self, text):
        """Анализирует текст через OpenAI"""
        if not self.hf_client:
            print("❌ HF клиент не настроен")
            return None
            
        try:
            prompt = f"""Проанализируй этот текст из чата Kufar и извлеки информацию:

{text}

Извлеки следующие данные:
- ФИО клиента (полное имя)
- Номер телефона
- Адрес доставки  
- Название товара
- Сумма заказа
- Никнейм (если есть)

Если какие-то данные отсутствуют, напиши "null".

Верни ТОЛЬКО JSON формат:
{{"name": "...", "phone": "...", "address": "...", "product": "...", "amount": "...", "username": "..."}}"""

            completion = self.hf_client.chat.completions.create(
                model="HuggingFaceH4/zephyr-7b-beta",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.1
            )
            
            response_text = completion.choices[0].message.content
            print(f"📨 Ответ от ИИ: {response_text}")
            
            # Парсим JSON из ответа
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                print(f"✅ Успешно распарсено")
                return result
                
            return None
                
        except Exception as e:
            print(f"❌ Ошибка анализа ИИ: {e}")
            return None

    async def process_order_data(self, result, caption):
        """Обрабатывает данные заказа"""
        # Коррекция ошибок
        result = self.correct_common_errors(result)
        
        # Создание данных заказа
        self.last_order_id += 1
        order_data = {
            'ID': self.last_order_id,
            'Номер_заказа': f"ORD{self.last_order_id:04d}",
            'Дата_заказа': datetime.now().strftime('%Y-%m-%d'),
            'ФИО': result.get('name', ''),
            'Телефон': result.get('phone', ''),
            'Адрес': result.get('address', ''),
            'Тип_доставки': self.detect_delivery_type(result, ""),
            'Товар': result.get('product', ''),
            'Сумма': result.get('amount', ''),
            'Примечание': '',
            'Никнейм': result.get('username', ''),
            'Статус': 'Новый',
            'Цена_из_подписи': 'Нет',
            'Трек_номер': ''
        }
        
        return order_data

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

    def save_order_to_db(self, order_data):
        """Сохраняет заказ в базу"""
        try:
            file_exists = os.path.exists(self.orders_file)
            
            with open(self.orders_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ID', 'Номер_заказа', 'Дата_заказа', 'ФИО', 'Телефон', 'Адрес',
                    'Тип_доставки', 'Товар', 'Сумма', 'Примечание', 'Никнейм',
                    'Статус', 'Цена_из_подписи', 'Трек_номер'
                ])
                
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(order_data)
            
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
                
            products = []
            file_exists = os.path.exists(self.products_file)
            
            if file_exists:
                with open(self.products_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    products = list(reader)
            
            product_found = False
            for product in products:
                if product['Название'] == product_name:
                    current_qty = int(product['Количество']) if product['Количество'].isdigit() else 0
                    if current_qty > 0:
                        product['Количество'] = str(current_qty - 1)
                    product['Количество_продаж'] = str(int(product['Количество_продаж']) + 1)
                    product['Последняя_цена'] = price
                    product_found = True
                    break
            
            if not product_found:
                new_id = max([int(p['ID']) for p in products]) + 1 if products else 1
                new_product = {
                    'ID': str(new_id),
                    'Название': product_name,
                    'Количество': '0',
                    'Последняя_цена': price,
                    'Количество_продаж': '1'
                }
                products.append(new_product)
            
            with open(self.products_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['ID', 'Название', 'Количество', 'Последняя_цена', 'Количество_продаж'])
                writer.writeheader()
                writer.writerows(products)
            
            print(f"✅ База товаров обновлена: {product_name}")
            
        except Exception as e:
            print(f"❌ Ошибка обновления базы товаров: {e}")

    def update_customers_db(self, order_data):
        """Обновляет базу клиентов"""
        try:
            customers = []
            file_exists = os.path.exists(self.customers_file)
            
            if file_exists:
                with open(self.customers_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    customers = list(reader)
            
            phone = order_data['Телефон']
            if not phone or phone == 'null':
                return
                
            amount = 0
            if order_data['Сумма']:
                numbers = re.findall(r'\d+', str(order_data['Сумма']))
                if numbers:
                    amount = int(numbers[0])
            
            customer_found = False
            for customer in customers:
                if customer['Телефон'] == phone:
                    customer['Количество_заказов'] = str(int(customer['Количество_заказов']) + 1)
                    customer['Общая_сумма'] = str(int(customer['Общая_сумма']) + amount)
                    customer['Последний_заказ'] = order_data['Дата_заказа']
                    customer_found = True
                    break
            
            if not customer_found:
                new_customer = {
                    'Телефон': phone,
                    'ФИО': order_data['ФИО'],
                    'Количество_заказов': '1',
                    'Общая_сумма': str(amount),
                    'Последний_заказ': order_data['Дата_заказа']
                }
                customers.append(new_customer)
            
            with open(self.customers_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['Телефон', 'ФИО', 'Количество_заказов', 'Общая_сумма', 'Последний_заказ'])
                writer.writeheader()
                writer.writerows(customers)
            
            print(f"✅ База клиентов обновлена: {order_data['ФИО']}")
            
        except Exception as e:
            print(f"❌ Ошибка обновления базы клиентов: {e}")

    def format_order_response(self, order_data, order_saved):
        """Форматирует ответ о заказе"""
        response = f"""✅ **ЗАКАЗ #{order_data['Номер_заказа']} СОЗДАН**

👤 **ФИО:** {order_data['ФИО']}
📞 **Телефон:** {order_data['Телефон']}
📍 **Адрес:** {order_data['Адрес']}
🚚 **Доставка:** {order_data['Тип_доставки']}
📦 **Товар:** {order_data['Товар']}
💰 **Сумма:** {order_data['Сумма']}
👥 **Никнейм:** {order_data['Никнейм']}"""

        if order_saved:
            response += f"\n\n💾 **Сохранено в базу**"
        
        return response

    def parse_text_data(self, text):
        """Парсит текст и извлекает данные"""
        parsed = {
            'name': '',
            'phone': '',
            'address': '',
            'product': '',
            'amount': '',
            'username': ''
        }
        
        lines = text.split('\n')
        
        # Поиск телефона
        phone_pattern = r'[\+]?[375]{3}[\s\-]?[\(]?\d{2}[\)]?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        for line in lines:
            phone_match = re.search(phone_pattern, line)
            if phone_match:
                parsed['phone'] = phone_match.group()
                break
        
        # Поиск цены
        price_pattern = r'(\d+)[\s]*[рр]'
        for line in lines:
            price_match = re.search(price_pattern, line)
            if price_match:
                parsed['amount'] = f"{price_match.group(1)} р."
                break
        
        # Поиск ФИО
        for line in lines:
            line_clean = line.strip()
            words = line_clean.split()
            if 2 <= len(words) <= 3:
                if all(word and word[0].isupper() for word in words):
                    excluded_words = ['отделение', 'европочта', 'почта', 'принял', 'отправка', 'г.', 'ул.']
                    if not any(excl in line_clean.lower() for excl in excluded_words):
                        if not any(word.isdigit() for word in words):
                            parsed['name'] = line_clean
                            break
        
        # Поиск адреса
        address_indicators = ['г.', 'ул.', 'отделение', 'область', 'район']
        for line in lines:
            line_lower = line.lower()
            if any(indicator in line_lower for indicator in address_indicators):
                if len(line) > 10:
                    parsed['address'] = line.strip()
                    break
        
        return parsed

    # === ДРУГИЕ ФУНКЦИИ ===
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

            orders = []
            with open(self.orders_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                orders = list(reader)
            
            if not orders:
                await update.message.reply_text("📊 База заказов пуста")
                return

            results = []
            for order in orders:
                if (search_query.lower() in order['ФИО'].lower() or
                    search_query in order['Телефон'] or
                    search_query.upper() in order['Номер_заказа'] or
                    search_query.lower() in order['Товар'].lower()):
                    results.append(order)
            
            if not results:
                await update.message.reply_text("❌ Заказы не найдены")
                return

            response = f"🔍 **НАЙДЕНО ЗАКАЗОВ:** {len(results)}\n\n"
            
            for order in results[:10]:
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
                with open(self.products_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    products = list(reader)
                
                if products:
                    response = "📦 **ТОВАРЫ В НАЛИЧИИ:**\n\n"
                    for product in products[:15]:
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
                with open(self.orders_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    orders = list(reader)
                    stats['total_orders'] = len(orders)
                    
                    total_revenue = 0
                    for order in orders:
                        if order['Сумма']:
                            numbers = re.findall(r'\d+', str(order['Сумма']))
                            if numbers:
                                total_revenue += int(numbers[0])
                    stats['total_revenue'] = total_revenue
            
            if os.path.exists(self.customers_file):
                with open(self.customers_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    customers = list(reader)
                    stats['unique_customers'] = len(customers)
            
            if os.path.exists(self.products_file):
                with open(self.products_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    products = list(reader)
                    stats['total_products'] = len(products)
                    
                    if products:
                        sorted_products = sorted(products, key=lambda x: int(x['Количество_продаж']), reverse=True)
                        top_products = sorted_products[:3]
                        stats['top_products'] = '\n'.join(
                            [f"• {p['Название']}: {p['Количество_продаж']} продаж" for p in top_products]
                        )
                    
        except Exception as e:
            print(f"❌ Ошибка расчета статистики: {e}")
            
        return stats

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
            # Анализируем текст как данные заказа
            await self.analyze_text_message(update, context, text)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 **SKUFAR PARSER** запущен!\n\n"
            "📸 Отправь скриншот чата Kufar - я подскажу как извлечь текст\n"
            "📝 Или просто пришли текст из чата - я его проанализирую!\n\n"
            "💡 *Бот использует ИИ для автоматического распознавания данных*"
        )
        await self.show_main_menu(update, context)

# ЗАПУСК БОТА
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    bot_manager = KufarSalesManager()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", bot_manager.start_command))
    application.add_handler(CommandHandler("menu", bot_manager.show_main_menu))
    application.add_handler(CallbackQueryHandler(bot_manager.handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, bot_manager.handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_manager.handle_text))
    
    print("🚀 Бот запускается...")
    print("🤖 ИИ система активна!")
    print("📊 Все функции готовы")
    print("🔍 Ожидаю команды...")
    
    application.run_polling()

if __name__ == "__main__":
    main()