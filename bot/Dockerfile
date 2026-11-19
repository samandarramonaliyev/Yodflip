FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY main.py texts.py ./
RUN useradd --create-home --uid 10001 bot
USER bot
EXPOSE 8080
CMD ["python", "main.py"]
