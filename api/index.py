import requests
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Коефіцієнти з вашого оригінального HTML-файлу
COEFFICIENTS = {
    "dcCollected": 1.40,
    "storeCollected": 2.80,
    "dcMoved": 3.45,
    "placed": 1.59,
    "weightPlacement": 0.14,
    "packingOrder": 0.28
}


def get_silpo_stats(api_url, bearer_token, from_date, to_date, point_id):
    """
    Робить запит до API "Сільпо" для отримання статистики.
    """
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }

    # Тіло запиту, яке ви знайшли у вкладці "Payload"
    payload = {
        "from": from_date,
        "pointId": point_id,
        "to": to_date
    }

    # Робимо POST-запит
    response = requests.post(api_url, json=payload, headers=headers)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401 or response.status_code == 403:
        raise Exception("Помилка авторизації (401/403). Схоже, що ваш BEARER_TOKEN застарів.")
    else:
        raise Exception(f"Помилка API 'Сільпо': {response.status_code} - {response.text}")


def process_data(api_data):
    """
    Обробляє дані з API "Сільпо" та розраховує результати.
    """
    users_list = []
    statistics = {}

    for item in api_data.get("items", []):
        user_info = item.get("user", {})
        user_id = user_info.get("id")
        full_name = user_info.get("fullName")

        if not user_id or not full_name:
            continue

        # 1. Додаємо користувача до загального списку
        users_list.append({
            "id": user_id,
            "fullName": full_name
        })

        # 2. Отримуємо "сирі" дані
        raw_stats = {
            "dcCollected": item.get("collectedDs", 0),
            "storeCollected": item.get("collectedShop", 0),
            "dcMoved": item.get("transferDs", 0),
            "placed": item.get("placement", 0),
            "weightPlacement": item.get("placementWeight", 0),
            "packingOrder": item.get("packedItemCount", 0)
        }

        # 3. Розраховуємо результати
        dc_collected_result = raw_stats["dcCollected"] * COEFFICIENTS["dcCollected"]
        store_collected_result = raw_stats["storeCollected"] * COEFFICIENTS["storeCollected"]
        dc_moved_result = raw_stats["dcMoved"] * COEFFICIENTS["dcMoved"]
        placed_result = raw_stats["placed"] * COEFFICIENTS["placed"]
        weight_placement_result = raw_stats["weightPlacement"] * COEFFICIENTS["weightPlacement"]
        packing_order_result = raw_stats["packingOrder"] * COEFFICIENTS["packingOrder"]

        total_result = (
                dc_collected_result +
                store_collected_result +
                dc_moved_result +
                placed_result +
                weight_placement_result +
                packing_order_result
        )

        # 4. Зберігаємо все у фінальну структуру
        statistics[user_id] = {
            "fullName": full_name,
            "raw": raw_stats,
            "calculated": {
                "dcCollected": dc_collected_result,
                "storeCollected": store_collected_result,
                "dcMoved": dc_moved_result,
                "placed": placed_result,
                "weightPlacement": weight_placement_result,
                "packingOrder": packing_order_result
            },
            "totalResult": total_result
        }

    # Сортуємо список користувачів за алфавітом
    users_list.sort(key=lambda x: x['fullName'])

    return {"usersList": users_list, "statistics": statistics}


class handler(BaseHTTPRequestHandler):

    def send_cors_headers(self):
        """Надсилає заголовки CORS для дозволу запитів з GitHub Pages."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        """Обробляє pre-flight запити (потрібно для CORS)."""
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Обробляє POST-запити від вашого frontend-у."""
        try:
            # 1. Отримуємо дані від frontend-у (дату та ID магазину)
            content_len = int(self.headers.get('content-length', 0))
            body = self.rfile.read(content_len)
            frontend_data = json.loads(body)

            from_date = frontend_data.get("from")
            to_date = frontend_data.get("to")
            point_id = frontend_data.get("pointId")

            if not from_date or not to_date or not point_id:
                raise Exception("Відсутні параметри 'from', 'to' або 'pointId'")

            # 2. Беремо наш СЕКРЕТНИЙ токен з Vercel
            BEARER_TOKEN = os.environ.get('BEARER_TOKEN')
            if not BEARER_TOKEN:
                raise Exception("BEARER_TOKEN не налаштовано у Vercel Environment Variables")

            # 3. Робимо запит до API "Сільпо"
            api_url = "https://dams-core-api.silpo.ua/v1/statistics/by-point"
            api_data = get_silpo_stats(api_url, BEARER_TOKEN, from_date, to_date, point_id)

            # 4. Обробляємо дані та розраховуємо результати
            processed_data = process_data(api_data)

            # 5. Відправляємо готові дані на наш frontend
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(processed_data).encode('utf-8'))

        except Exception as e:
            # Обробка будь-яких помилок
            error_message = {"error": str(e)}
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(error_message).encode('utf-8'))

    def do_GET(self):
        """Простий GET-обробник, щоб перевірити, чи сервер працює."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        response = {"message": "Сервер статистики працює! Використовуйте POST-запит для отримання даних."}
        self.wfile.write(json.dumps(response).encode('utf-8'))