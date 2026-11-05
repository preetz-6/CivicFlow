FROM python:3.11-slim
WORKDIR /sim
COPY sim.py .
ENV PYTHONUNBUFFERED=1
# Standard library only: no pip install needed.
CMD ["python", "sim.py", "--once"]
