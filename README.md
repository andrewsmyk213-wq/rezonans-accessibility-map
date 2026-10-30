# rezonans-accessibility-map
Accessible city navigation and interactive accessibility map for Chernivtsi, Ukraine. Developed by Team Rezonans for Chernivtsi Open Data Hackathon 3.0.

# Резонанс · Доступні Чернівці — Public Beta

Mobile-first карта доступності міста на базі відкритих геоданих.

- Запуск локально: `python3 server.py --port 8080`, відкрити `http://localhost:8080`.
- Деплой на Render: див. **[DEPLOY.md](DEPLOY.md)**. `render.yaml` знаходиться в корені репозиторію.
- Ключ маршрутизації `ORS_API_KEY` передавайте тільки як environment variable.
- Точки у `data/places.geojson` на початку **порожні**. Додайте перевірені геодані до публікації карти як актуальної.
- Повідомлення про помилки у публічній бета-версії вимкнено, доки не налаштоване постійне сховище з модерацією.
- Ця версія не гарантує безбар'єрність маршрутів. Відкриті дані можуть бути неповними.
