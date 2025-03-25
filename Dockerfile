FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# port 5000 expose
EXPOSE 5000

# デフォルトのコマンド
CMD ["python", "visualizer/app.py"] 